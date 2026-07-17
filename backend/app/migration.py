"""SQLite → PostgreSQL data migration.

Copies an existing SQLite HR database into the currently-configured PostgreSQL
database (``app.db.DATABASE_URL``), verbatim: every row keeps its original
primary keys so nothing that references a row breaks. The source file is only
ever READ. Shared by the CLI (``scripts/migrate_sqlite_to_pg.py``) and the
MIGRATE_ON_BOOT startup hook in ``main.py``.
"""
import logging
import sqlite3

from . import db as appdb

logger = logging.getLogger("hr.migration")

# Order matters only for the real foreign keys (sessions/password_resets -> users);
# the rest reference employees by name, not by a DB-level FK.
TABLES = [
    "employees", "users", "sessions", "password_resets",
    "violations", "permissions", "documents", "document_history", "app_settings",
]
# Tables whose id is a SERIAL column whose sequence must be advanced post-copy.
SERIAL_TABLES = ["employees", "users", "violations", "permissions", "documents", "document_history"]
# Primary key used to verify every row made it across.
PK = {
    "employees": "id", "users": "id", "violations": "id", "permissions": "id",
    "documents": "id", "document_history": "id",
    "sessions": "token_hash", "password_resets": "token_hash", "app_settings": "key",
}


def _counts(execute) -> dict:
    return {t: execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def target_non_empty() -> dict:
    """{table: count} for non-empty tables in the configured Postgres target."""
    import psycopg
    conn = psycopg.connect(appdb.DATABASE_URL)
    try:
        return {t: n for t, n in _counts(conn.execute).items() if n}
    finally:
        conn.close()


def migrate(sqlite_path: str, *, dry_run: bool = False, force: bool = False, log=logger.info) -> dict:
    """Copy every row from the SQLite file into the configured Postgres target.

    Returns a summary dict with ``ok`` (bool) and ``reason``. Refuses a non-empty
    target unless ``force``. Verifies row counts AND primary-key sets match before
    reporting success. Never modifies the source file.
    """
    if not appdb.USING_PG:
        return {"ok": False, "reason": "target_not_postgres"}

    import psycopg
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    appdb.init_db()  # ensure the schema exists on the target (idempotent)
    dst = psycopg.connect(appdb.DATABASE_URL)
    try:
        existing = {t: n for t, n in _counts(dst.execute).items() if n}
        if existing and not force:
            return {"ok": False, "reason": "target_not_empty", "existing": existing}

        src_counts = _counts(src.execute)
        if dry_run:
            return {"ok": True, "reason": "dry_run", "counts": src_counts}

        for t in TABLES:
            rows = src.execute(f"SELECT * FROM {t}").fetchall()
            if not rows:
                continue
            cols = rows[0].keys()
            collist = ", ".join(cols)
            placeholders = ", ".join(["%s"] * len(cols))
            with dst.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO {t} ({collist}) VALUES ({placeholders})",
                    [tuple(r[c] for c in cols) for r in rows],
                )
        dst.commit()

        # Advance the id sequences past the copied rows.
        for t in SERIAL_TABLES:
            dst.execute(
                f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {t}), 1), (SELECT COUNT(*) FROM {t}) > 0)"
            )
        dst.commit()

        # Verify: identical row counts AND identical primary-key sets per table.
        dst_counts = _counts(dst.execute)
        for t in TABLES:
            if src_counts[t] != dst_counts[t]:
                log(f"MISMATCH {t}: source {src_counts[t]} vs target {dst_counts[t]}")
                return {"ok": False, "reason": "count_mismatch", "table": t}
            key = PK[t]
            s = {r[0] for r in src.execute(f"SELECT {key} FROM {t}").fetchall()}
            d = {r[0] for r in dst.execute(f"SELECT {key} FROM {t}").fetchall()}
            if s != d:
                log(f"MISMATCH {t}: primary-key sets differ")
                return {"ok": False, "reason": "key_mismatch", "table": t}

        return {"ok": True, "reason": "migrated", "counts": src_counts, "total": sum(src_counts.values())}
    finally:
        src.close()
        dst.close()
