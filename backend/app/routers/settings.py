import os
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field

from ..auth import ROLE_HR_MANAGER, CurrentUser, require_role
from ..db import db
from ..emailer import email_configured, email_from, email_transport, send_email
from ..reminders import read_config, send_reminders, write_config

router = APIRouter(prefix="/settings", tags=["settings"])

_manager = require_role(ROLE_HR_MANAGER)


class TestEmailIn(BaseModel):
    to: Optional[EmailStr] = None


class ReminderConfigIn(BaseModel):
    # Free-form so several addresses can be pasted (comma/space/newline separated);
    # parsed and de-duplicated server-side in reminders.parse_recipients.
    recipients: str = Field("", max_length=2000)
    enabled: bool = True


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


def _reminders_payload() -> dict:
    with db() as conn:
        cfg = read_config(conn)
    return {
        "recipients": cfg["recipients"],
        "enabled": cfg["enabled"],
        "last_sent": cfg["last_sent"],
        "email_configured": email_configured(),
    }


@router.get("/reminders")
def get_reminders(_: CurrentUser = Depends(_manager)):
    """Document-expiry reminder settings: who gets the daily digest, whether the
    automatic send is on, and when it last ran."""
    return _reminders_payload()


@router.post("/reminders")
def set_reminders(payload: ReminderConfigIn, _: CurrentUser = Depends(_manager)):
    write_config(payload.recipients, payload.enabled)
    return _reminders_payload()


@router.post("/reminders/run")
def run_reminders(_: CurrentUser = Depends(_manager)):
    """Send the digest now regardless of the enable toggle (still needs
    recipients + a configured email transport)."""
    return send_reminders(require_enabled=False)
