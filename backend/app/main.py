import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import bootstrap_admin
from .db import init_db
from .routers import auth as auth_router
from .routers import attendance, employees, matrix, settings, stats, violations

logger = logging.getLogger("hr")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    bootstrap_admin()
    yield


app = FastAPI(title="HR Disciplinary API", version="1.0.0", lifespan=lifespan)

_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_allowed_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
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
    return {"ok": True}


# Auth (login/logout/reset) is the only open router; every other router
# declares its own role requirements per endpoint (see routers/*.py).
app.include_router(auth_router.router, prefix="/api")
app.include_router(employees.router, prefix="/api")
app.include_router(violations.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(matrix.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(attendance.router, prefix="/api")


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
