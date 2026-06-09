import os
import sqlite3
from contextlib import contextmanager

DB_FILE = os.environ.get("HR_DB_FILE", os.path.join(os.path.dirname(__file__), "..", "..", "hr_system.db"))
DB_FILE = os.path.abspath(DB_FILE)


@contextmanager
def db():
    conn = sqlite3.connect(DB_FILE)
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
            """
        )
    finally:
        raw.close()
