import os
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr

from ..auth import ROLE_HR_MANAGER, CurrentUser, require_role
from ..emailer import email_configured, email_from, email_transport, send_email

router = APIRouter(prefix="/settings", tags=["settings"])

_manager = require_role(ROLE_HR_MANAGER)


class TestEmailIn(BaseModel):
    to: Optional[EmailStr] = None


@router.get("")
def get_settings(_: CurrentUser = Depends(_manager)):
    """Read-only delivery status for the Settings page. Email is configured via
    environment variables (RESEND_API_KEY, or SMTP_*), never stored here."""
    return {
        "email_configured": email_configured(),
        "transport": email_transport(),
        "email_from": email_from(),
        "app_base_url": os.environ.get("APP_BASE_URL", ""),
    }


@router.post("/test-email")
def test_email(payload: TestEmailIn, user: CurrentUser = Depends(_manager)):
    """Send a test message so a manager can confirm delivery without logging a
    real violation. Defaults to the signed-in manager's own address."""
    if not email_configured():
        return {"sent": False, "reason": "email_not_configured"}
    recipient = payload.to or user.email
    ok = send_email(
        recipient,
        "HR System — Test Email",
        "This is a test email from the Travel Gate KSA HR System.\n"
        "If you received this, email notifications are configured correctly.",
    )
    return {"sent": ok, "to": recipient}
