import logging
import os
import secrets
import time
from collections import defaultdict
from threading import Lock

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

logger = logging.getLogger("hr.auth")

# Either a plaintext password (legacy) or a bcrypt hash may be configured.
# The bcrypt hash is preferred; generate one with:
#   python -c "import bcrypt; print(bcrypt.hashpw(b'your-password', bcrypt.gensalt()).decode())"
HR_ADMIN_USERNAME = os.environ.get("HR_ADMIN_USERNAME", "hr")
HR_ADMIN_PASSWORD = os.environ.get("HR_ADMIN_PASSWORD", "")
HR_ADMIN_PASSWORD_HASH = os.environ.get("HR_ADMIN_PASSWORD_HASH", "")

# Refuse to authenticate anyone against a missing or known-default secret
# instead of silently falling back to "admin123" (fail closed).
_INSECURE_PASSWORDS = {"", "admin123", "admin", "password", "changeme"}

_security = HTTPBasic()

# --- Brute-force lockout: 5 failed attempts per client IP in a 15-minute
# window locks that IP out for 15 minutes. In-memory on purpose — the app is
# a single uvicorn process in front of SQLite; revisit if that changes.
LOCKOUT_MAX_FAILURES = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60

_failures: dict[str, list[float]] = defaultdict(list)
_failures_lock = Lock()


def _client_ip(request: Request) -> str:
    if request.client:
        return request.client.host
    return "unknown"


def _is_locked_out(ip: str) -> bool:
    now = time.monotonic()
    with _failures_lock:
        attempts = _failures[ip] = [t for t in _failures[ip] if now - t < LOCKOUT_WINDOW_SECONDS]
        return len(attempts) >= LOCKOUT_MAX_FAILURES


def _record_failure(ip: str) -> None:
    with _failures_lock:
        _failures[ip].append(time.monotonic())


def _clear_failures(ip: str) -> None:
    with _failures_lock:
        _failures.pop(ip, None)


def _password_ok(candidate: str) -> bool:
    if HR_ADMIN_PASSWORD_HASH:
        import bcrypt

        try:
            return bcrypt.checkpw(candidate.encode("utf-8"), HR_ADMIN_PASSWORD_HASH.encode("utf-8"))
        except ValueError:
            logger.error("HR_ADMIN_PASSWORD_HASH is not a valid bcrypt hash")
            return False
    if HR_ADMIN_PASSWORD in _INSECURE_PASSWORDS:
        return False
    # encode before compare_digest: the str variant raises TypeError on
    # non-ASCII input, which would surface as a 500
    return secrets.compare_digest(candidate.encode("utf-8"), HR_ADMIN_PASSWORD.encode("utf-8"))


def auth_is_configured() -> bool:
    return bool(HR_ADMIN_PASSWORD_HASH) or HR_ADMIN_PASSWORD not in _INSECURE_PASSWORDS


def require_admin(request: Request, creds: HTTPBasicCredentials = Depends(_security)) -> str:
    if not auth_is_configured():
        logger.error(
            "Rejecting login: set HR_ADMIN_PASSWORD_HASH (preferred) or a strong "
            "HR_ADMIN_PASSWORD — default/empty passwords are not accepted."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this server",
        )

    ip = _client_ip(request)
    if _is_locked_out(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(LOCKOUT_WINDOW_SECONDS)},
        )

    user_ok = secrets.compare_digest(creds.username.encode("utf-8"), HR_ADMIN_USERNAME.encode("utf-8"))
    pass_ok = _password_ok(creds.password)
    if not (user_ok and pass_ok):
        _record_failure(ip)
        logger.warning("Failed login attempt for user %r from %s", creds.username, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    _clear_failures(ip)
    return creds.username
