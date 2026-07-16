import os
import sqlite3
from contextlib import contextmanager

DB_FILE = os.environ.get("HR_DB_FILE", os.path.join(os.path.dirname(__file__), "..", "..", "hr_system.db"))
DB_FILE = os.path.abspath(DB_FILE)

# Create the parent directory if needed so HR_DB_FILE can point at a freshly
# mounted volume (e.g. Railway's /data/hr_system.db) that doesn't exist yet.
os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)


@contextmanager
def db():
    # timeout=30 makes a writer wait (up to 30s) for a competing write to finish
    # instead of failing immediately with "database is locked" when several
    # writes land at once.
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def lock(conn) -> None:
    """Serialize a read-modify-write (quota / escalation / last-manager checks).

    Call this as the FIRST statement in a ``db()`` block, before the read: it
    takes the write lock up front so a concurrent request can't slip a stale
    check-then-write through the gap. Released on commit/rollback by ``db()``.

    On SQLite this escalates the transaction to a write lock (BEGIN IMMEDIATE),
    which is DB-wide but correct. (When the PostgreSQL backend lands, this will
    take a per-key advisory lock instead.)
    """
    conn.execute("BEGIN IMMEDIATE")


def init_db() -> None:
    raw = sqlite3.connect(DB_FILE)
    try:
        # WAL lets readers and a writer proceed concurrently (readers no longer
        # block the writer and vice-versa). It's a persistent property of the DB
        # file, so setting it once at init is enough.
        raw.execute("PRAGMA journal_mode=WAL")
        raw.executescript(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    UNIQUE NOT NULL,
                email         TEXT    NOT NULL,
                department    TEXT    DEFAULT '',
                manager_email TEXT    DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS violations (
                id              INTEGER  PRIMARY KEY AUTOINCREMENT,
                employee_name   TEXT     NOT NULL,
                category        TEXT     NOT NULL,
                incident        TEXT     NOT NULL,
                penalty_color   TEXT     NOT NULL,
                penalty_label   TEXT     NOT NULL,
                deduction_hours REAL     DEFAULT 0.0,
                deduction_days  REAL     DEFAULT 0.0,
                freeze_months   INTEGER  DEFAULT 0,
                comment         TEXT     DEFAULT '',
                submitted_by    TEXT     NOT NULL DEFAULT '',
                proof_image     TEXT     NOT NULL DEFAULT '',
                created_at      DATETIME NOT NULL
            );

            -- Indexes for the escalation lookup and report filters.
            CREATE INDEX IF NOT EXISTS idx_violations_emp_inc_date
                ON violations (employee_name, incident, created_at);
            CREATE INDEX IF NOT EXISTS idx_violations_created
                ON violations (created_at);
            CREATE INDEX IF NOT EXISTS idx_violations_penalty
                ON violations (penalty_color);

            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER  PRIMARY KEY AUTOINCREMENT,
                email           TEXT     UNIQUE NOT NULL,
                name            TEXT     NOT NULL,
                role            TEXT     NOT NULL CHECK (role IN ('hr_manager','hr_officer','dept_head','employee')),
                department      TEXT     NOT NULL DEFAULT '',
                password_hash   TEXT     NOT NULL,
                is_active       INTEGER  NOT NULL DEFAULT 1,
                failed_attempts INTEGER  NOT NULL DEFAULT 0,
                locked_until    TEXT,
                created_at      TEXT     NOT NULL
            );

            -- Server-side sessions: the cookie holds a random token; only its
            -- SHA-256 is stored so a DB leak doesn't yield usable sessions.
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT    PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf_token TEXT    NOT NULL,
                expires_at TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);

            CREATE TABLE IF NOT EXISTS password_resets (
                token_hash TEXT    PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT    NOT NULL,
                used       INTEGER NOT NULL DEFAULT 0
            );

            -- Early-leave permissions (استئذان): each employee gets a small
            -- monthly quota. month_key (YYYY-MM) drives the per-month allowance;
            -- attachment (base64) holds the supporting paper and is HR-manager
            -- only. One row per granted permission.
            CREATE TABLE IF NOT EXISTS permissions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_name   TEXT    NOT NULL,
                permission_date TEXT    NOT NULL,
                month_key       TEXT    NOT NULL,
                note            TEXT    NOT NULL DEFAULT '',
                attachment      TEXT    NOT NULL DEFAULT '',
                attachment_name TEXT    NOT NULL DEFAULT '',
                attachment_mime TEXT    NOT NULL DEFAULT '',
                created_by      TEXT    NOT NULL DEFAULT '',
                created_at      TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_permissions_emp_month
                ON permissions (employee_name, month_key);

            -- Expiry-tracked documents: one generic table backs every kind of
            -- dated paperwork (employee residence permits / contracts, branch &
            -- housing rents, vehicle insurance, and open-ended licenses). Each
            -- row has a start/end date and an optional base64 attachment; the
            -- traffic-light status (green/yellow/red/expired) is computed from
            -- end_date at read time, not stored.
            --   category : 'iqama' | 'contract' | 'rent' | 'vehicle' | 'license'
            --   owner    : employee name (iqama/contract) or asset key
            --              (rent branch: 'rawda'|'hamra'|'housing'); free for
            --              vehicle/license.
            --   title    : human-friendly label (esp. licenses & vehicles).
            CREATE TABLE IF NOT EXISTS documents (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                category        TEXT    NOT NULL,
                owner           TEXT    NOT NULL DEFAULT '',
                title           TEXT    NOT NULL DEFAULT '',
                start_date      TEXT    NOT NULL,
                end_date        TEXT    NOT NULL,
                note            TEXT    NOT NULL DEFAULT '',
                attachment      TEXT    NOT NULL DEFAULT '',
                attachment_name TEXT    NOT NULL DEFAULT '',
                attachment_mime TEXT    NOT NULL DEFAULT '',
                created_by      TEXT    NOT NULL DEFAULT '',
                created_at      TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_documents_cat_end
                ON documents (category, end_date);
            -- "Slot" documents hold exactly one active record per owner: each
            -- employee has one iqama + one contract, each rent branch one lease.
            -- Renewals edit the row in place (PATCH). Vehicles & licenses are
            -- open lists, so they're intentionally excluded from this constraint.
            CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_slot_unique
                ON documents (owner, category)
                WHERE category IN ('iqama', 'contract', 'rent');

            -- Small key/value store for operator-editable settings that don't
            -- belong in env vars (e.g. the document-expiry reminder recipients
            -- and per-category alert thresholds), so they can be changed from
            -- the UI without a redeploy.
            CREATE TABLE IF NOT EXISTS app_settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );

            -- Renewal history: one row per date change to a document (see the
            -- PATCH handler in routers/documents.py), so the audit trail of past
            -- iqama/contract/rent/etc. validity periods is preserved.
            CREATE TABLE IF NOT EXISTS document_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                old_start   TEXT    NOT NULL DEFAULT '',
                old_end     TEXT    NOT NULL DEFAULT '',
                new_start   TEXT    NOT NULL DEFAULT '',
                new_end     TEXT    NOT NULL DEFAULT '',
                changed_by  TEXT    NOT NULL DEFAULT '',
                changed_at  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_document_history_doc
                ON document_history (document_id, id);

            -- The attendance feature (clock in/out, geofencing, WebAuthn
            -- fingerprints) was removed; drop its tables from existing DBs.
            DROP TABLE IF EXISTS attendance;
            DROP TABLE IF EXISTS office_locations;
            DROP TABLE IF EXISTS office_networks;
            DROP TABLE IF EXISTS webauthn_credentials;
            DROP TABLE IF EXISTS webauthn_challenges;
            """
        )
        raw.commit()
    finally:
        raw.close()
