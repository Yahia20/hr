#!/usr/bin/env python3
"""Copy an existing SQLite HR database into a fresh PostgreSQL database, verbatim.

Every row is copied with its original primary keys, so nothing that references a
row by id (or a session token) breaks. The source file is only ever READ.

Usage (run from the backend/ directory):

    python scripts/migrate_sqlite_to_pg.py \
        --sqlite /data/hr_system.db \
        --pg postgresql://user:pass@host:5432/dbname

Defaults: --sqlite from $HR_DB_FILE (else ../hr_system.db), --pg from $DATABASE_URL.
Add --dry-run to report counts without writing, or --force to allow a non-empty
target (it will refuse otherwise). On success it verifies row counts and the set
of primary keys match on both sides, then advances the id sequences.
"""
import argparse
import os
import sqlite3
import sys

# Make `import app.*` work when run from backend/.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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


def _counts(execute, tables):
    return {t: execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate the SQLite HR DB into PostgreSQL.")
    ap.add_argument("--sqlite", default=os.environ.get("HR_DB_FILE",
                    os.path.join(os.path.dirname(__file__), "..", "hr_system.db")))
    ap.add_argument("--pg", default=os.environ.get("DATABASE_URL", ""))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="allow a non-empty target")
    args = ap.parse_args()

    src_path = os.path.abspath(args.sqlite)
    if not args.pg:
        print("error: no target — pass --pg or set DATABASE_URL", file=sys.stderr)
        return 2
    if not os.path.exists(src_path):
        print(f"error: SQLite file not found: {src_path}", file=sys.stderr)
        return 2

    # Build the target schema through the app's own definition (single source of
    # truth) by pointing app.db at the target before importing it.
    os.environ["DATABASE_URL"] = args.pg
    import app.db as appdb
    if not appdb.USING_PG:
        print("error: --pg / DATABASE_URL is not a PostgreSQL URL", file=sys.stderr)
        return 2
    import psycopg

    src = sqlite3.connect(src_path)
    src.row_factory = sqlite3.Row
    print(f"source : {src_path}")
    print(f"target : {args.pg.rsplit('@', 1)[-1]}")

    appdb.init_db()  # create the schema on the target if it isn't there yet
    dst = psycopg.connect(args.pg)
    try:
        # Refuse to clobber an already-populated target unless forced.
        existing = _counts(dst.execute, TABLES)
        non_empty = {t: n for t, n in existing.items() if n}
        if non_empty and not args.force:
            print(f"error: target already has data {non_empty}; use --force to override",
                  file=sys.stderr)
            return 3

        src_counts = _counts(src.execute, TABLES)
        print("\nrows to copy:")
        for t in TABLES:
            print(f"  {t:18} {src_counts[t]}")
        if args.dry_run:
            print("\n--dry-run: nothing written")
            return 0

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
        ok = True
        dst_counts = _counts(dst.execute, TABLES)
        for t in TABLES:
            if src_counts[t] != dst_counts[t]:
                print(f"MISMATCH {t}: source {src_counts[t]} vs target {dst_counts[t]}")
                ok = False
                continue
            key = PK[t]
            s = {r[0] for r in src.execute(f"SELECT {key} FROM {t}").fetchall()}
            d = {r[0] for r in dst.execute(f"SELECT {key} FROM {t}").fetchall()}
            if s != d:
                print(f"MISMATCH {t}: primary keys differ (missing {len(s - d)}, extra {len(d - s)})")
                ok = False
        if not ok:
            print("\nVERIFICATION FAILED — target left in place for inspection", file=sys.stderr)
            return 4

        total = sum(src_counts.values())
        print(f"\nOK: {total} rows migrated and verified across {len(TABLES)} tables.")
        return 0
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    raise SystemExit(main())
