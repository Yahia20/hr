import hashlib
import logging
import os
import secrets
import sqlite3
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .. import auth as A
from ..db import db
from ..emailer import send_email, smtp_configured
from ..schemas import (
    ForgotPasswordIn,
    LoginIn,
    ResetPasswordIn,
    UserIn,
    UserOut,
)

logger = logging.getLogger("hr.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# Public base URL of the frontend, used to build password-reset links.
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5173")


def _user_out(row) -> dict:
    return {
        "id": row["id"], "email": row["email"], "name": row["name"],
        "role": row["role"], "department": row["department"],
    }


def _set_auth_cookies(response: Response, token: str, csrf: str, max_age: int) -> None:
    response.set_cookie(
        A.SESSION_COOKIE, token, max_age=max_age, httponly=True,
        samesite="lax", secure=A.COOKIE_SECURE, path="/",
    )
    # CSRF cookie is intentionally readable by same-origin JS (double-submit).
    response.set_cookie(
        A.CSRF_COOKIE, csrf, max_age=max_age, httponly=False,
        samesite="lax", secure=A.COOKIE_SECURE, path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(A.SESSION_COOKIE, path="/")
    response.delete_cookie(A.CSRF_COOKIE, path="/")


@router.post("/login")
def login(payload: LoginIn, request: Request, response: Response):
    ip = A.client_ip(request)
    if A.ip_is_locked_out(ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(A.LOCKOUT_WINDOW_SECONDS)},
        )

    email = payload.email.strip().lower()
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if row is not None:
        A.check_account_lockout(row)

    # Same generic error whether the email or the password is wrong.
    if row is None or not row["is_active"] or not A.verify_password(payload.password, row["password_hash"]):
        A.record_ip_failure(ip)
        if row is not None:
            A.record_account_failure(row["id"], row["failed_attempts"])
        logger.warning("Failed login for %r from %s", email, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    A.clear_ip_failures(ip)
    A.clear_account_failures(row["id"])
    token, csrf, max_age = A.create_session(row["id"], payload.remember_me)
    _set_auth_cookies(response, token, csrf, max_age)
    return {"user": _user_out(row)}


@router.post("/logout")
def logout(request: Request, response: Response):
    # No CSRF/auth requirement: logging out an unauthenticated client is a
    # no-op, and requiring a valid CSRF token here would strand expired UIs.
    token = request.cookies.get(A.SESSION_COOKIE)
    if token:
        A.destroy_session(token)
    _clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me")
def me(user: A.CurrentUser = Depends(A.require_user)):
    return {"user": {
        "id": user.id, "email": user.email, "name": user.name,
        "role": user.role, "department": user.department,
    }}


@router.post("/forgot")
def forgot_password(payload: ForgotPasswordIn, request: Request):
    ip = A.client_ip(request)
    if A.ip_is_locked_out(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Try again later.")
    # Count reset requests against the IP limiter so the endpoint can't be
    # used to spam mailboxes or probe accounts at full speed.
    A.record_ip_failure(ip)

    email = payload.email.strip().lower()
    with db() as conn:
        row = conn.execute("SELECT id, name FROM users WHERE email = ? AND is_active = 1", (email,)).fetchone()

    if row is not None:
        token = secrets.token_urlsafe(32)
        expires = (datetime.utcnow() + timedelta(minutes=A.RESET_TOKEN_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
        with db() as conn:
            conn.execute("DELETE FROM password_resets WHERE user_id = ?", (row["id"],))
            conn.execute(
                "INSERT INTO password_resets (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (hashlib.sha256(token.encode()).hexdigest(), row["id"], expires),
            )
        link = f"{APP_BASE_URL}/?reset_token={token}"
        sent = send_email(
            email,
            "HR System — Password Reset",
            f"Hello {row['name']},\n\nUse this link to reset your password "
            f"(valid for {A.RESET_TOKEN_MINUTES} minutes):\n\n{link}\n\n"
            "If you did not request this, you can ignore this email.",
        )
        if not sent and not smtp_configured():
            # Dev fallback: surface the link in server logs only.
            logger.warning("Password reset link for %s: %s", email, link)

    # Always the same response — never reveal whether the account exists.
    return {"ok": True, "message": "If the account exists, a reset link has been sent."}


@router.post("/reset")
def reset_password(payload: ResetPasswordIn):
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with db() as conn:
        row = conn.execute(
            "SELECT user_id, expires_at, used FROM password_resets WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if row is None or row["used"] or row["expires_at"] < now:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset link")
        conn.execute("UPDATE password_resets SET used = 1 WHERE token_hash = ?", (token_hash,))
        conn.execute(
            "UPDATE users SET password_hash = ?, failed_attempts = 0, locked_until = NULL WHERE id = ?",
            (A.hash_password(payload.new_password), row["user_id"]),
        )
    # A password reset invalidates every existing session for the account.
    A.destroy_user_sessions(row["user_id"])
    return {"ok": True}


# --- User management (HR Manager only) ---------------------------------------

@router.get("/users", response_model=list[UserOut])
def list_users(_: A.CurrentUser = Depends(A.require_role(A.ROLE_HR_MANAGER))):
    with db() as conn:
        rows = conn.execute(
            "SELECT id, email, name, role, department, is_active FROM users ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserIn, _: A.CurrentUser = Depends(A.require_role(A.ROLE_HR_MANAGER))):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with db() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO users (email, name, role, department, password_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   RETURNING id, email, name, role, department, is_active""",
                (payload.email.strip().lower(), payload.name.strip(), payload.role,
                 payload.department.strip(), A.hash_password(payload.password), now),
            )
            return dict(cur.fetchone())
        except sqlite3.IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")


@router.delete("/users/{user_id}", status_code=204)
def deactivate_user(user_id: int, current: A.CurrentUser = Depends(A.require_role(A.ROLE_HR_MANAGER))):
    if user_id == current.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate your own account")
    with db() as conn:
        conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
    A.destroy_user_sessions(user_id)
