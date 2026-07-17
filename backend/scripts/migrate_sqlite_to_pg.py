#!/usr/bin/env python3
"""Copy an existing SQLite HR database into a fresh PostgreSQL database, verbatim.

Thin CLI wrapper around ``app.migration.migrate`` (the same core the
MIGRATE_ON_BOOT startup hook uses), so the CLI and the boot path can never
diverge. Every row is copied with its original primary keys, so nothing that
references a row by id (or a session token) breaks. The source file is only
ever READ.

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
import sys

# Make `import app.*` work when run from backend/.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


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

    # Point app.db at the target BEFORE importing it — USING_PG / DATABASE_URL are
    # captured at import time. The migration core builds the schema through the
    # app's own definition (single source of truth).
    os.environ["DATABASE_URL"] = args.pg
    from app import migration

    if not migration.appdb.USING_PG:
        print("error: --pg / DATABASE_URL is not a PostgreSQL URL", file=sys.stderr)
        return 2

    print(f"source : {src_path}")
    print(f"target : {args.pg.rsplit('@', 1)[-1]}")

    result = migration.migrate(src_path, dry_run=args.dry_run, force=args.force, log=print)
    reason = result.get("reason")

    if reason == "target_not_empty":
        print(f"error: target already has data {result['existing']}; use --force to override",
              file=sys.stderr)
        return 3
    if reason == "dry_run":
        print("\nrows to copy:")
        for t, n in result["counts"].items():
            print(f"  {t:18} {n}")
        print("\n--dry-run: nothing written")
        return 0
    if reason in ("count_mismatch", "key_mismatch"):
        # migrate() already logged the offending table via log=print.
        print("\nVERIFICATION FAILED — target left in place for inspection", file=sys.stderr)
        return 4
    if not result.get("ok"):
        print(f"error: migration failed ({reason})", file=sys.stderr)
        return 4

    print("\nrows copied:")
    for t, n in result["counts"].items():
        print(f"  {t:18} {n}")
    print(f"\nOK: {result['total']} rows migrated and verified across {len(result['counts'])} tables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
