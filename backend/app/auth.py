import hashlib
import logging
import os
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock

import bcrypt
from fastapi import Depends, HTTPException, Request, status

from .db import db

logger = logging.getLogger("hr.auth")

SESSION_COOKIE = "hr_session"
CSRF_COOKIE = "hr_csrf"
CSRF_HEADER = "x-csrf-token"

SESSION_HOURS = 12          # default session lifetime
REMEMBER_DAYS = 30          # "remember me" session lifetime
RESET_TOKEN_MINUTES = 60    # password-reset link validity

# Set COOKIE_SECURE=true in production (Railway serves HTTPS) so the session
# cookie is never sent over plain HTTP.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")

ROLE_HR_MANAGER = "hr_manager"
ROLE_HR_OFFICER = "hr_officer"
ROLE_DEPT_HEAD = "dept_head"
ROLE_EMPLOYEE = "employee"
ALL_ROLES = (ROLE_HR_MANAGER, ROLE_HR_OFFICER, ROLE_DEPT_HEAD, ROLE_EMPLOYEE)

MIN_PASSWORD_LENGTH = 8

# --- Account lockout: 5 failed logins per account within 15 minutes locks the
# account for 15 minutes (persisted on the user row). A per-IP limiter (below)
# additionally slows attackers spraying many accounts.
LOCKOUT_MAX_FAILURES = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60

_ip_failures: dict[str, list[float]] = defaultdict(list)
_ip_lock = Lock()


def _utcnow() -> datetime:
    return datetime.utcnow()


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def ip_is_locked_out(ip: str) -> bool:
    now = time.monotonic()
    with _ip_lock:
        attempts = _ip_failures[ip] = [t for t in _ip_failures[ip] if now - t < LOCKOUT_WINDOW_SECONDS]
        return len(attempts) >= LOCKOUT_MAX_FAILURES


def record_ip_failure(ip: str) -> None:
    with _ip_lock:
        _ip_failures[ip].append(time.monotonic())


def clear_ip_failures(ip: str) -> None:
    with _ip_lock:
        _ip_failures.pop(ip, None)


@dataclass
class CurrentUser:
    id: int
    email: str
    name: str
    role: str
    department: str


def create_session(user_id: int, remember: bool) -> tuple[str, str, int]:
    """Returns (session_token, csrf_token, max_age_seconds)."""
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    lifetime = timedelta(days=REMEMBER_DAYS) if remember else timedelta(hours=SESSION_HOURS)
    now = _utcnow()
    with db() as conn:
        # opportunistic cleanup of expired sessions
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_fmt(now),))
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (_token_hash(token), user_id, csrf, _fmt(now + lifetime), _fmt(now)),
        )
    return token, csrf, int(lifetime.total_seconds())


def destroy_session(token: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def destroy_user_sessions(user_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def _load_session(token: str):
    with db() as conn:
        return conn.execute(
            """SELECT s.csrf_token, s.expires_at, u.id, u.email, u.name, u.role, u.department, u.is_active
               FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ?""",
            (_token_hash(token),),
        ).fetchone()


def require_user(request: Request) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    row = _load_session(token)
    if row is None or not row["is_active"] or row["expires_at"] < _fmt(_utcnow()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    # CSRF: state-changing requests must echo the session's CSRF token in a
    # header (double-submit; the cookie is readable by same-origin JS only).
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        sent = request.headers.get(CSRF_HEADER, "")
        if not secrets.compare_digest(sent.encode(), row["csrf_token"].encode()):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")
    return CurrentUser(
        id=row["id"], email=row["email"], name=row["name"],
        role=row["role"], department=row["department"],
    )


def require_role(*roles: str):
    def dep(user: CurrentUser = Depends(require_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return dep


def check_account_lockout(user_row) -> None:
    locked_until = user_row["locked_until"]
    if locked_until and locked_until > _fmt(_utcnow()):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Account temporarily locked after repeated failed logins. Try again later.",
            headers={"Retry-After": str(LOCKOUT_WINDOW_SECONDS)},
        )


def record_account_failure(user_id: int, failed_attempts: int) -> None:
    failed = failed_attempts + 1
    locked_until = None
    if failed >= LOCKOUT_MAX_FAILURES:
        locked_until = _fmt(_utcnow() + timedelta(seconds=LOCKOUT_WINDOW_SECONDS))
        failed = 0
    with db() as conn:
        conn.execute(
            "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
            (failed, locked_until, user_id),
        )


def clear_account_failures(user_id: int) -> None:
    with db() as conn:
        conn.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (user_id,))


def bootstrap_admin() -> None:
    """Create the first HR Manager account from env vars on an empty users
    table, so a fresh deployment is never left without a login."""
    email = os.environ.get("HR_BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("HR_BOOTSTRAP_ADMIN_PASSWORD", "")
    name = os.environ.get("HR_BOOTSTRAP_ADMIN_NAME", "HR Manager")
    with db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count:
        return
    if not email or len(password) < MIN_PASSWORD_LENGTH:
        logger.error(
            "No users exist and HR_BOOTSTRAP_ADMIN_EMAIL / HR_BOOTSTRAP_ADMIN_PASSWORD "
            "(min %d chars) are not set — nobody will be able to log in.",
            MIN_PASSWORD_LENGTH,
        )
        return
    with db() as conn:
        conn.execute(
            "INSERT INTO users (email, name, role, department, password_hash, created_at) VALUES (?, ?, ?, '', ?, ?)",
            (email, name, ROLE_HR_MANAGER, hash_password(password), _fmt(_utcnow())),
        )
    logger.info("Bootstrapped initial HR Manager account %s", email)
