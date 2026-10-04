"""Database access layer.

Backs onto SQLite by default (single-file, zero-config) or PostgreSQL when
``DATABASE_URL`` is set. The rest of the app is written against a small SQL
subset that works on both; the only backend-specific bits — placeholder style,
row access, autoincrement, locking, and PRAGMA/DDL — are absorbed here, so
routers keep using ``conn.execute("... ?", params)`` and ``row["col"]``.
"""
import os
import sqlite3
from contextlib import contextmanager

try:  # psycopg is only needed when DATABASE_URL points at PostgreSQL.
    import psycopg
    _HAS_PG = True
except ImportError:  # pragma: no cover - SQLite-only installs
    psycopg = None
    _HAS_PG = False


def _normalize_pg_url(url: str) -> str:
    # Railway/Heroku hand out the legacy postgres:// scheme; psycopg wants postgresql://.
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


DATABASE_URL = _normalize_pg_url(os.environ.get("DATABASE_URL", "").strip())
USING_PG = DATABASE_URL.startswith("postgresql://")

if USING_PG and not _HAS_PG:  # fail loudly rather than silently falling back
    raise RuntimeError("DATABASE_URL is set to PostgreSQL but psycopg is not installed")

# SQLite lives in a file; only compute/create that when we're actually on SQLite.
DB_FILE = os.path.abspath(
    os.environ.get("HR_DB_FILE", os.path.join(os.path.dirname(__file__), "..", "..", "hr_system.db"))
)
if not USING_PG:
    # Create the parent dir so HR_DB_FILE can point at a freshly mounted volume.
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)

# Exceptions callers can catch regardless of backend (routers guarding unique
# conflicts). A tuple works anywhere an ``except`` expects an exception type.
if _HAS_PG:
    DBError = (sqlite3.Error, psycopg.Error)
    IntegrityError = (sqlite3.IntegrityError, psycopg.errors.IntegrityError)
else:
    DBError = (sqlite3.Error,)
    IntegrityError = (sqlite3.IntegrityError,)

# Fixed key for the PostgreSQL advisory lock (see lock()). SQLite uses a
# whole-database write transaction instead, so the value is irrelevant there.
_PG_LOCK_KEY = 4242


# ── PostgreSQL compatibility shim ────────────────────────────────────────────
# Make psycopg look like the sqlite3 connection the app expects: qmark
# placeholders become pyformat, and rows support both positional (row[0]) and
# keyed (row["col"]) access plus dict(row)/keys()/`in`, like sqlite3.Row.

class _Row:
    __slots__ = ("_cols", "_vals", "_map")

    def __init__(self, cols, vals):
        self._cols = cols
        self._vals = vals
        self._map = None

    def _mapping(self):
        if self._map is None:
            self._map = dict(zip(self._cols, self._vals))
        return self._map

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        return self._mapping()[key]

    def keys(self):
        return list(self._cols)

    def __contains__(self, key):
        return key in self._cols

    def __iter__(self):  # sqlite3.Row iterates values; dict(row) uses keys() first
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)


def _hybrid_row_factory(cursor):
    cols = [c.name for c in cursor.description] if cursor.description else []
    return lambda values: _Row(cols, values)


def _translate(sql: str) -> str:
    # Escape literal % (none today, but LIKE patterns would need it) then swap
    # sqlite's ? placeholders for psycopg's %s.
    return sql.replace("%", "%%").replace("?", "%s")


class _PGConnection:
    """Wraps a psycopg connection with the sqlite3-style surface the app uses."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        return self._conn.execute(_translate(sql), params or None)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


@contextmanager
def db():
    if USING_PG:
        conn = _PGConnection(psycopg.connect(DATABASE_URL, row_factory=_hybrid_row_factory))
    else:
        # timeout=30 makes a writer wait (up to 30s) for a competing write to
        # finish instead of failing immediately with "database is locked".
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

    SQLite escalates the transaction to a DB-wide write lock (BEGIN IMMEDIATE).
    PostgreSQL takes a transaction-scoped advisory lock instead.
    """
    if USING_PG:
        conn.execute("SELECT pg_advisory_xact_lock(?)", (_PG_LOCK_KEY,))
    else:
        conn.execute("BEGIN IMMEDIATE")


# Schema shared by both backends. {PK} and {DATETIME} are the only tokens that
# differ; everything else (IF NOT EXISTS, partial unique indexes, ON DELETE
# CASCADE, CHECK, REAL/TEXT/INTEGER) is valid on SQLite and PostgreSQL alike.
_SCHEMA = """
            CREATE TABLE IF NOT EXISTS employees (
                id            {PK},
                name          TEXT    UNIQUE NOT NULL,
                email         TEXT    NOT NULL,
                department    TEXT    DEFAULT '',
                manager_email TEXT    DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS violations (
                id              {PK},
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
                created_at      {DATETIME} NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_violations_emp_inc_date
                ON violations (employee_name, incident, created_at);
            CREATE INDEX IF NOT EXISTS idx_violations_created
                ON violations (created_at);
            CREATE INDEX IF NOT EXISTS idx_violations_penalty
                ON violations (penalty_color);

            CREATE TABLE IF NOT EXISTS users (
                id              {PK},
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

            CREATE TABLE IF NOT EXISTS permissions (
                id              {PK},
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

            CREATE TABLE IF NOT EXISTS documents (
                id              {PK},
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
            CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_slot_unique
                ON documents (owner, category)
                WHERE category IN ('iqama', 'contract', 'rent');

            CREATE TABLE IF NOT EXISTS app_settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS document_history (
                id          {PK},
                document_id INTEGER NOT NULL,
                old_start   TEXT    NOT NULL DEFAULT '',
                old_end     TEXT    NOT NULL DEFAULT '',
                new_start   TEXT    NOT NULL DEFAULT '',
                new_end     TEXT    NOT NULL DEFAULT '',
                old_owner   TEXT    NOT NULL DEFAULT '',
                new_owner   TEXT    NOT NULL DEFAULT '',
                changed_by  TEXT    NOT NULL DEFAULT '',
                changed_at  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_document_history_doc
                ON document_history (document_id, id);

            CREATE TABLE IF NOT EXISTS job_openings (
                id                {PK},
                title             TEXT    NOT NULL,
                department        TEXT    NOT NULL DEFAULT '',
                location          TEXT    NOT NULL DEFAULT '',
                employment_type   TEXT    NOT NULL DEFAULT '',
                description       TEXT    NOT NULL DEFAULT '',
                status            TEXT    NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
                min_years         REAL    NOT NULL DEFAULT 0,
                min_education     TEXT    NOT NULL DEFAULT '',
                gates             TEXT    NOT NULL DEFAULT '{}',
                required_skills   TEXT    NOT NULL DEFAULT '[]',
                preferred_skills  TEXT    NOT NULL DEFAULT '[]',
                languages         TEXT    NOT NULL DEFAULT '[]',
                weights           TEXT    NOT NULL DEFAULT '{}',
                rubric_version    INTEGER NOT NULL DEFAULT 1,
                semantic_criteria TEXT    NOT NULL DEFAULT '[]',
                created_by        TEXT    NOT NULL DEFAULT '',
                created_at        TEXT    NOT NULL,
                closed_at         TEXT
            );

            CREATE TABLE IF NOT EXISTS applicants (
                id                             {PK},
                job_id                         INTEGER NOT NULL REFERENCES job_openings(id) ON DELETE CASCADE,
                full_name                      TEXT    NOT NULL DEFAULT '',
                email                          TEXT    NOT NULL DEFAULT '',
                phone                          TEXT    NOT NULL DEFAULT '',
                nationality                    TEXT    NOT NULL DEFAULT '',
                city                           TEXT    NOT NULL DEFAULT '',
                source                         TEXT    NOT NULL DEFAULT '',
                stage                          TEXT    NOT NULL DEFAULT 'new' CHECK (stage IN ('new','screened','shortlisted','interview','offer','hired','rejected')),
                cv_attachment                  TEXT    NOT NULL DEFAULT '',
                cv_name                        TEXT    NOT NULL DEFAULT '',
                cv_mime                        TEXT    NOT NULL DEFAULT '',
                cv_text                        TEXT    NOT NULL DEFAULT '',
                parsed                         TEXT    NOT NULL DEFAULT '{}',
                corrections                    TEXT    NOT NULL DEFAULT '{}',
                score                          REAL    NOT NULL DEFAULT 0,
                rules_score                    REAL    NOT NULL DEFAULT 0,
                final_score                    REAL,
                score_breakdown                TEXT    NOT NULL DEFAULT '[]',
                gate_failures                  TEXT    NOT NULL DEFAULT '[]',
                needs_manual_review            INTEGER NOT NULL DEFAULT 0,
                notes                           TEXT    NOT NULL DEFAULT '',
                cv_revision                     INTEGER NOT NULL DEFAULT 1,
                semantic_status                 TEXT    NOT NULL DEFAULT 'disabled' CHECK (semantic_status IN ('pending','done','partial','failed','disabled','opted_out','manual')),
                semantic_reason                 TEXT    NOT NULL DEFAULT '',
                external_processing_consent_at  TEXT,
                consent_notice_version          TEXT    NOT NULL DEFAULT '',
                created_by                      TEXT    NOT NULL DEFAULT '',
                created_at                      TEXT    NOT NULL,
                updated_at                      TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_applicants_job_score
                ON applicants (job_id, score DESC);
            CREATE INDEX IF NOT EXISTS idx_applicants_job_stage
                ON applicants (job_id, stage);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_applicants_job_email_unique
                ON applicants (job_id, email) WHERE email <> '';

            CREATE TABLE IF NOT EXISTS applicant_stage_history (
                id           {PK},
                applicant_id INTEGER NOT NULL REFERENCES applicants(id) ON DELETE CASCADE,
                old_stage    TEXT    NOT NULL,
                new_stage    TEXT    NOT NULL,
                note         TEXT    NOT NULL DEFAULT '',
                changed_by   TEXT    NOT NULL DEFAULT '',
                changed_at   TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_applicant_stage_history_applicant
                ON applicant_stage_history (applicant_id, id);

            CREATE TABLE IF NOT EXISTS interview_feedback (
                id           {PK},
                applicant_id INTEGER NOT NULL REFERENCES applicants(id) ON DELETE CASCADE,
                interviewer  TEXT    NOT NULL DEFAULT '',
                result       TEXT    NOT NULL CHECK (result IN ('cleared','rejected')),
                ratings      TEXT    NOT NULL DEFAULT '[]',
                avg_rating   REAL    NOT NULL DEFAULT 0,
                comment      TEXT    NOT NULL DEFAULT '',
                created_at   TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS skills_taxonomy (
                id         TEXT    PRIMARY KEY,
                canonical  TEXT    NOT NULL,
                category   TEXT    NOT NULL,
                aliases    TEXT    NOT NULL DEFAULT '[]',
                is_active  INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS ats_semantic_runs (
                id                              {PK},
                applicant_id                    INTEGER NOT NULL REFERENCES applicants(id) ON DELETE CASCADE,
                cv_revision                     INTEGER NOT NULL,
                rubric_version                  INTEGER NOT NULL,
                consent_revision                TEXT    NOT NULL DEFAULT '',
                input_hash                      TEXT    NOT NULL DEFAULT '',
                pipeline_version                TEXT    NOT NULL DEFAULT '',
                redaction_version               TEXT    NOT NULL DEFAULT '',
                state                           TEXT    NOT NULL DEFAULT '',
                status                          TEXT    NOT NULL DEFAULT 'pending',
                attempts                        INTEGER NOT NULL DEFAULT 0,
                next_retry_at                   TEXT,
                lease_token                     TEXT,
                lease_expires_at                TEXT,
                error_code                      TEXT    NOT NULL DEFAULT '',
                requested_model                 TEXT    NOT NULL DEFAULT '',
                returned_model                  TEXT    NOT NULL DEFAULT '',
                request_id                      TEXT    NOT NULL DEFAULT '',
                prompt_tokens                   INTEGER NOT NULL DEFAULT 0,
                completion_tokens               INTEGER NOT NULL DEFAULT 0,
                total_tokens                    INTEGER NOT NULL DEFAULT 0,
                tokens                          INTEGER NOT NULL DEFAULT 0,
                cost                            REAL    NOT NULL DEFAULT 0,
                attempt_log                     TEXT    NOT NULL DEFAULT '[]',
                created_at                      TEXT    NOT NULL,
                updated_at                      TEXT    NOT NULL,
                completed_at                    TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_ats_semantic_runs_claim
                ON ats_semantic_runs (status, next_retry_at, lease_expires_at);
            CREATE INDEX IF NOT EXISTS idx_ats_semantic_runs_applicant
                ON ats_semantic_runs (applicant_id, id);

            CREATE TABLE IF NOT EXISTS ats_semantic_results (
                id                       {PK},
                run_id                   INTEGER NOT NULL REFERENCES ats_semantic_runs(id) ON DELETE CASCADE,
                criterion_key            TEXT    NOT NULL,
                question_hash            TEXT    NOT NULL DEFAULT '',
                p                        REAL    CHECK (p IS NULL OR (p >= 0 AND p <= 1)),
                classification           TEXT    NOT NULL DEFAULT 'uncertain' CHECK (classification IN ('yes','no','uncertain')),
                hr_override_value        INTEGER,
                hr_override_actor        TEXT    NOT NULL DEFAULT '',
                hr_override_reason       TEXT    NOT NULL DEFAULT '',
                hr_override_at           TEXT,
                confirmed_source_ranges  TEXT    NOT NULL DEFAULT '[]',
                created_at               TEXT    NOT NULL,
                updated_at               TEXT    NOT NULL,
                UNIQUE (run_id, criterion_key)
            );

            DROP TABLE IF EXISTS attendance;
            DROP TABLE IF EXISTS office_locations;
            DROP TABLE IF EXISTS office_networks;
            DROP TABLE IF EXISTS webauthn_credentials;
            DROP TABLE IF EXISTS webauthn_challenges;
"""


def _render_schema(pk: str, datetime_type: str) -> str:
    return _SCHEMA.replace("{PK}", pk).replace("{DATETIME}", datetime_type)


# Columns introduced after a table shipped. `CREATE TABLE IF NOT EXISTS` is a
# no-op on a database that already has the table, so the schema above alone
# would never reach an existing deployment — add them explicitly. Every entry
# must be nullable or carry a DEFAULT so back-filling existing rows is trivial.
_ADDED_COLUMNS = (
    # Reassigning a document to another owner is auditable (see routers/documents.py).
    ("document_history", "old_owner", "TEXT NOT NULL DEFAULT ''"),
    ("document_history", "new_owner", "TEXT NOT NULL DEFAULT ''"),
)


def _existing_columns(conn, table: str) -> set:
    if USING_PG:
        # Called with a raw psycopg connection from init_db(), so pyformat
        # placeholders. Scoped to the active schema so a same-named table
        # elsewhere can't mask a genuinely missing column.
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = %s AND table_schema = current_schema()",
            (table,),
        ).fetchall()
        return {r[0] for r in rows}
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_missing_columns(conn) -> None:
    """Idempotently apply `_ADDED_COLUMNS`. Runs on every boot; a no-op once the
    columns exist, so it is safe to call repeatedly and in any order.

    Both backends look the column up first rather than using Postgres'
    ``ADD COLUMN IF NOT EXISTS``: plain ``ALTER TABLE ADD COLUMN`` and
    ``information_schema`` are universal SQL, so this can't fail on an older
    server than the one it was written against. A boot must never die here."""
    for table, column, decl in _ADDED_COLUMNS:
        if column not in _existing_columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_db() -> None:
    if USING_PG:
        ddl = _render_schema("SERIAL PRIMARY KEY", "TEXT")
        conn = psycopg.connect(DATABASE_URL)
        try:
            # psycopg's extended protocol runs one statement per execute.
            for stmt in (s.strip() for s in ddl.split(";")):
                if stmt:
                    conn.execute(stmt)
            _add_missing_columns(conn)
            _seed_skills_taxonomy(conn, "%s")
            conn.commit()
        finally:
            conn.close()
        return

    ddl = _render_schema("INTEGER PRIMARY KEY AUTOINCREMENT", "DATETIME")
    raw = sqlite3.connect(DB_FILE)
    try:
        # WAL lets readers and a writer proceed concurrently; it's a persistent
        # property of the file, so setting it once at init is enough.
        raw.execute("PRAGMA journal_mode=WAL")
        raw.executescript(ddl)
        _add_missing_columns(raw)
        _seed_skills_taxonomy(raw, "?")
        raw.commit()
    finally:
        raw.close()


def _seed_skills_taxonomy(conn, placeholder: str) -> None:
    """Seed the editable taxonomy once; later HR edits are never overwritten."""
    if conn.execute("SELECT COUNT(*) FROM skills_taxonomy").fetchone()[0]:
        return
    import json
    from .ats.taxonomy import SKILLS

    sql = (
        "INSERT INTO skills_taxonomy (id, canonical, category, aliases, is_active) "
        f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})"
    )
    for skill in SKILLS:
        conn.execute(sql, (
            skill["id"], skill["canonical"], skill["category"],
            json.dumps(skill["aliases"], ensure_ascii=False), 1,
        ))
