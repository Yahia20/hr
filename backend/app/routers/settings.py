import os

from fastapi import APIRouter, Depends

from ..auth import ROLE_HR_MANAGER, CurrentUser, require_role
from ..emailer import SMTP_FROM, SMTP_HOST, send_email, smtp_configured

router = APIRouter(prefix="/settings", tags=["settings"])

_manager = require_role(ROLE_HR_MANAGER)


@router.get("")
def get_settings(_: CurrentUser = Depends(_manager)):
    """Read-only system status for the Settings page. SMTP itself is configured
    via environment variables (SMTP_HOST/USER/PASSWORD), never stored here."""
    return {
        "smtp_configured": smtp_configured(),
        "smtp_host": SMTP_HOST,
        "smtp_from": SMTP_FROM,
        "app_base_url": os.environ.get("APP_BASE_URL", ""),
    }


@router.post("/test-email")
def test_email(user: CurrentUser = Depends(_manager)):
    """Send a test message to the signed-in manager's own address so they can
    confirm email delivery is working without logging a real violation."""
    if not smtp_configured():
        return {"sent": False, "reason": "smtp_not_configured"}
    ok = send_email(
        user.email,
        "HR System — Test Email",
        "This is a test email from the Travel Gate KSA HR System.\n"
        "If you received this, email notifications are configured correctly.",
    )
    return {"sent": ok}
