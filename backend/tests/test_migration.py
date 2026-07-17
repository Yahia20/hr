"""SQLite → PostgreSQL migration tests.

These only run when the suite is pointed at PostgreSQL (the ``backend-postgres``
CI job, ``DATABASE_URL`` set) — a migration inherently needs a real Postgres
target. Each test builds a throwaway SQLite source and migrates it into a fresh,
uniquely-named temporary database on the same server, so nothing touches the
app's own test database.
"""
import os
import sqlite3
import tempfile
from urllib.parse import urlsplit, urlunsplit

import pytest

from app import db as appdb
from app import migration

pytestmark = pytest.mark.skipif(not appdb.USING_PG, reason="migration target requires PostgreSQL")

if appdb.USING_PG:
    import psycopg

_seq = {"n": 0}


def _with_dbname(url: str, dbname: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path="/" + dbname))


def _maint_url() -> str:
    # Connect to the stock 'postgres' database to CREATE/DROP others.
    return _with_dbname(appdb.DATABASE_URL, "postgres")


def _build_sqlite_source(path: str) -> dict:
    """Create a SQLite DB with the app schema + a handful of known rows.
    Returns the expected {table: count}."""
    ddl = appdb._render_schema("INTEGER PRIMARY KEY AUTOINCREMENT", "DATETIME")
    con = sqlite3.connect(path)
    try:
        con.executescript(ddl)
        con.execute(
            "INSERT INTO employees (id, name, email, department) VALUES (?,?,?,?)",
            (7, "Sara", "sara@x.com", "Ops"),
        )
        con.execute(
            "INSERT INTO users (id, email, name, role, password_hash, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (3, "boss@x.com", "Boss", "hr_manager", "hash", "2026-01-01 00:00:00"),
        )
        con.execute(
            "INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at, created_at) "
            "VALUES (?,?,?,?,?)",
            ("tok", 3, "csrf", "2026-12-31 00:00:00", "2026-01-01 00:00:00"),
        )
        con.execute(
            "INSERT INTO violations (id, employee_name, category, incident, penalty_color, "
            "penalty_label, created_at) VALUES (?,?,?,?,?,?,?)",
            (42, "Sara", "Attendance", "Late", "Yellow", "Warning", "2026-02-02 09:00:00"),
        )
        con.execute("INSERT INTO app_settings (key, value) VALUES (?,?)", ("k", "v"))
        con.commit()
    finally:
        con.close()
    return {"employees": 1, "users": 1, "sessions": 1, "violations": 1, "app_settings": 1}


@pytest.fixture
def fresh_target(monkeypatch):
    """Create an empty, uniquely-named Postgres DB and point app.db at it; drop it
    on teardown. Restores DATABASE_URL so later tests are unaffected."""
    _seq["n"] += 1
    dbname = f"hrmig_test_{os.getpid()}_{_seq['n']}"
    original = appdb.DATABASE_URL
    maint = _maint_url()
    con = psycopg.connect(maint, autocommit=True)
    try:
        con.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        con.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        con.close()

    target_url = _with_dbname(original, dbname)
    monkeypatch.setattr(appdb, "DATABASE_URL", target_url)
    try:
        yield target_url
    finally:
        monkeypatch.setattr(appdb, "DATABASE_URL", original)
        con = psycopg.connect(maint, autocommit=True)
        try:
            con.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        finally:
            con.close()


def test_migrate_copies_every_row_with_original_keys(fresh_target):
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "src.db")
        expected = _build_sqlite_source(src)

        appdb.init_db()  # lifespan builds the schema before the migration check
        assert migration.target_non_empty() == {}  # fresh target starts empty

        result = migration.migrate(src)
        assert result["ok"], result
        assert result["reason"] == "migrated"
        assert result["total"] == sum(expected.values())

        # Rows arrived with their ORIGINAL primary keys, not renumbered.
        con = psycopg.connect(fresh_target)
        try:
            assert con.execute("SELECT name FROM employees WHERE id = 7").fetchone()[0] == "Sara"
            assert con.execute("SELECT email FROM users WHERE id = 3").fetchone()[0] == "boss@x.com"
            assert con.execute("SELECT employee_name FROM violations WHERE id = 42").fetchone()[0] == "Sara"
            assert con.execute("SELECT value FROM app_settings WHERE key = 'k'").fetchone()[0] == "v"

            # Sequences advanced past the copied ids: a fresh insert gets id > 7.
            new_id = con.execute(
                "INSERT INTO employees (name, email) VALUES ('Ali', 'ali@x.com') RETURNING id"
            ).fetchone()[0]
            con.commit()
            assert new_id > 7
        finally:
            con.close()


def test_migrate_refuses_non_empty_target(fresh_target):
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "src.db")
        _build_sqlite_source(src)

        assert migration.migrate(src)["ok"]  # first pass populates the target
        assert migration.target_non_empty()  # now non-empty

        again = migration.migrate(src)  # second pass must refuse, not double-insert
        assert not again["ok"]
        assert again["reason"] == "target_not_empty"


def test_dry_run_writes_nothing(fresh_target):
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "src.db")
        expected = _build_sqlite_source(src)

        result = migration.migrate(src, dry_run=True)
        assert result["ok"] and result["reason"] == "dry_run"
        assert result["counts"]["employees"] == expected["employees"]
        assert migration.target_non_empty() == {}  # target still untouched


def test_boot_hook_migrates_then_is_idempotent(fresh_target, monkeypatch):
    """The MIGRATE_ON_BOOT startup path: first boot migrates, second boot is a
    no-op (target already populated), and neither raises."""
    from app import main

    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "src.db")
        _build_sqlite_source(src)

        monkeypatch.setenv("MIGRATE_ON_BOOT", "1")
        monkeypatch.setattr(appdb, "DB_FILE", src)

        appdb.init_db()  # lifespan runs init_db() before _maybe_migrate_on_boot()
        main._maybe_migrate_on_boot()  # first boot: migrates
        assert migration.target_non_empty()["employees"] == 1

        main._maybe_migrate_on_boot()  # second boot: sees data, skips cleanly
        assert migration.target_non_empty()["employees"] == 1  # not doubled
