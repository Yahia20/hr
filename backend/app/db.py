import os
import sqlite3
from contextlib import contextmanager

DB_FILE = os.environ.get("HR_DB_FILE", os.path.join(os.path.dirname(__file__), "..", "..", "hr_system.db"))
DB_FILE = os.path.abspath(DB_FILE)


@contextmanager
def db():
    # timeout=30 makes a writer wait (up to 30s) for a competing write to finish
    # instead of failing immediately with "database is locked" — important during
    # the morning attendance clock-in spike when many writes land at once.
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

            -- Geofence anchors for attendance: clocking in/out must happen
            -- within radius_m of one of these (when geofencing is enabled).
            CREATE TABLE IF NOT EXISTS office_locations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL,
                lat        REAL    NOT NULL,
                lng        REAL    NOT NULL,
                radius_m   INTEGER NOT NULL DEFAULT 150,
                created_at TEXT    NOT NULL
            );

            -- One row per user per work day (first clock-in / last clock-out).
            -- Times are stored in UTC; work_date is the local business day.
            CREATE TABLE IF NOT EXISTS attendance (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                work_date           TEXT    NOT NULL,
                clock_in_at         TEXT    NOT NULL,
                clock_in_lat        REAL,
                clock_in_lng        REAL,
                clock_in_accuracy   REAL,
                clock_in_office     TEXT    NOT NULL DEFAULT '',
                clock_in_distance_m REAL,
                clock_in_verified   INTEGER NOT NULL DEFAULT 0,
                clock_out_at        TEXT,
                clock_out_lat       REAL,
                clock_out_lng       REAL,
                clock_out_accuracy  REAL,
                clock_out_office    TEXT    NOT NULL DEFAULT '',
                clock_out_distance_m REAL,
                clock_out_verified  INTEGER NOT NULL DEFAULT 0,
                UNIQUE (user_id, work_date)
            );
            CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance (work_date);

            -- WebAuthn (device fingerprint/biometric) credentials; binary parts
            -- are stored base64url-encoded.
            CREATE TABLE IF NOT EXISTS webauthn_credentials (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                credential_id TEXT    UNIQUE NOT NULL,
                public_key    TEXT    NOT NULL,
                sign_count    INTEGER NOT NULL DEFAULT 0,
                transports    TEXT    NOT NULL DEFAULT '',
                device_label  TEXT    NOT NULL DEFAULT '',
                created_at    TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_webauthn_user ON webauthn_credentials (user_id);

            -- Short-lived WebAuthn challenges (one active per user per purpose).
            CREATE TABLE IF NOT EXISTS webauthn_challenges (
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                purpose    TEXT    NOT NULL CHECK (purpose IN ('register','clock')),
                challenge  TEXT    NOT NULL,
                expires_at TEXT    NOT NULL,
                PRIMARY KEY (user_id, purpose)
            );
            """
        )
    finally:
        raw.close()
