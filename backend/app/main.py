import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db as appdb
from .auth import bootstrap_admin
from .db import db, init_db
from .reminders import send_reminders
from .routers import auth as auth_router
from .routers import documents, employees, matrix, permissions, settings, stats, violations

logger = logging.getLogger("hr")


def _env_true(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


def _check_production_config() -> None:
    """Loud startup warnings when running in production (COOKIE_SECURE=true) with
    config that would break or weaken the deployment. Warnings, not hard failures,
    so a deploy is never bricked — but they're impossible to miss in the logs."""
    if not _env_true("COOKIE_SECURE"):
        logger.warning(
            "COOKIE_SECURE is not 'true' — session cookies will be sent over plain "
            "HTTP. Set COOKIE_SECURE=true in production (behind HTTPS)."
        )
        return  # remaining checks only matter once we're actually in prod mode

    if not os.environ.get("APP_BASE_URL", "").strip():
        logger.warning(
            "APP_BASE_URL is unset in production — password-reset links will be "
            "malformed. Set APP_BASE_URL to the public https URL of the app."
        )
    db_file = os.environ.get("HR_DB_FILE", "").strip()
    if not db_file:
        logger.warning(
            "HR_DB_FILE is unset — the SQLite database lives inside the container and "
            "is LOST on every redeploy. Point HR_DB_FILE at a mounted volume "
            "(e.g. /data/hr_system.db)."
        )


# Hour of day (0-23, server local time) to send the daily expiry digest.
REMINDER_HOUR = int(os.environ.get("DOC_REMINDER_HOUR", "8"))


async def _reminder_scheduler() -> None:
    """Send the document-expiry digest once a day at REMINDER_HOUR. Best-effort:
    exceptions are swallowed so a bad tick never kills the loop, and it fires at
    most once per calendar day per running process."""
    while True:
        now = datetime.now()
        target = now.replace(hour=REMINDER_HOUR, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        try:
            await asyncio.sleep((target - now).total_seconds())
        except asyncio.CancelledError:
            break
        # send_reminders is blocking (SMTP/HTTP); run it off the event loop so
        # the daily send never freezes concurrent requests.
        summary = await asyncio.to_thread(send_reminders, require_enabled=True)
        if summary.get("sent"):
            logger.info("Daily document reminder sent: %s", summary)


def _maybe_migrate_on_boot() -> None:
    """One-shot SQLite→PostgreSQL migration at startup, gated on MIGRATE_ON_BOOT.

    Lets the Railway cutover be config-only (no terminal): point HR_DB_FILE at the
    existing SQLite volume, set DATABASE_URL to the new Postgres, set
    MIGRATE_ON_BOOT=1, deploy. On boot the app copies every row into the (empty)
    Postgres, verifies it, then serves from Postgres. Remove MIGRATE_ON_BOOT after
    the first successful boot.

    Idempotent and safe to leave on: it never runs when the target already has
    data (so a second deploy is a no-op), and it aborts startup loudly if a
    migration is attempted but fails verification, rather than silently serving a
    half-copied database.
    """
    if not _env_true("MIGRATE_ON_BOOT"):
        return
    if not appdb.USING_PG:
        logger.warning("MIGRATE_ON_BOOT is set but DATABASE_URL is not PostgreSQL — skipping.")
        return

    from .migration import migrate, target_non_empty

    existing = target_non_empty()
    if existing:
        logger.info("MIGRATE_ON_BOOT: target already has data %s — skipping migration.", existing)
        return
    if not os.path.exists(appdb.DB_FILE):
        logger.warning(
            "MIGRATE_ON_BOOT: no SQLite source at %s — nothing to migrate, starting empty.",
            appdb.DB_FILE,
        )
        return

    logger.info("MIGRATE_ON_BOOT: migrating SQLite %s into PostgreSQL…", appdb.DB_FILE)
    summary = migrate(appdb.DB_FILE, log=logger.warning)
    if not summary.get("ok"):
        raise RuntimeError(f"MIGRATE_ON_BOOT failed: {summary}")
    logger.info("MIGRATE_ON_BOOT: migrated %s rows and verified: %s",
                summary.get("total"), summary.get("counts"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    _maybe_migrate_on_boot()  # before bootstrap_admin: a migrated users table must not re-seed
    bootstrap_admin()
    _check_production_config()
    task = asyncio.create_task(_reminder_scheduler())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="HR Disciplinary API", version="1.0.0", lifespan=lifespan)

_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_allowed_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api"):
        # API responses carry HR data; keep them out of shared caches.
        response.headers["Cache-Control"] = "no-store"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.get("/health")
def health():
    # Verify the database is actually reachable — a bare 200 would let the
    # platform keep routing traffic to an instance whose DB/volume is down.
    try:
        with db() as conn:
            conn.execute("SELECT 1")
    except Exception:
        logger.exception("Health check failed: database unreachable")
        return JSONResponse({"ok": False, "db": "unreachable"}, status_code=503)
    return {"ok": True, "db": "ok"}


# Auth (login/logout/reset) is the only open router; every other router
# declares its own role requirements per endpoint (see routers/*.py).
app.include_router(auth_router.router, prefix="/api")
app.include_router(employees.router, prefix="/api")
app.include_router(violations.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(matrix.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(permissions.router, prefix="/api")
app.include_router(documents.router, prefix="/api")


# Serve the built React SPA from the same origin as the API. The frontend talks
# to a relative "/api" with same-origin cookies, so both must share one origin.
# Mounted last (after the routers and /health) so it only catches non-API paths;
# skipped entirely when no build is present (e.g. local dev with the Vite proxy).
_frontend_dist = os.environ.get("FRONTEND_DIST") or str(
    Path(__file__).resolve().parents[2] / "frontend" / "dist"
)
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
else:
    logger.warning("Frontend build not found at %s; serving API only", _frontend_dist)
