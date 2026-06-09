import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import require_admin
from .db import init_db
from .routers import employees, matrix, stats, violations


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="HR Disciplinary API", version="1.0.0", lifespan=lifespan)

_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_allowed_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/auth/check")
def auth_check(user: str = Depends(require_admin)):
    return {"user": user}


_protected = [Depends(require_admin)]
app.include_router(employees.router, prefix="/api", dependencies=_protected)
app.include_router(violations.router, prefix="/api", dependencies=_protected)
app.include_router(stats.router, prefix="/api", dependencies=_protected)
app.include_router(matrix.router, prefix="/api", dependencies=_protected)
