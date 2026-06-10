import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("hr.email")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns False (and logs) on any failure —
    callers must not leak success/failure to API clients (user enumeration)."""
    if not smtp_configured():
        logger.warning("SMTP not configured; email to %s not sent. Subject: %s", to, subject)
        return False
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as srv:
            srv.login(SMTP_USER, SMTP_PASSWORD)
            srv.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        logger.exception("Failed to send email to %s", to)
        return False


def send_violation_emails(
    *,
    employee_name: str,
    employee_email: str,
    manager_email: str,
    category: str,
    incident: str,
    penalty_label: str,
    deduction_days: float,
    comment: str,
    submitted_by: str,
) -> None:
    """Notify the employee and their manager that a violation was logged.

    Best-effort and side-effect only: runs in a background task, sends to each
    recipient independently, and never raises (send_email swallows failures)."""
    subject = f"HR Disciplinary Notice — {employee_name}"
    lines = [
        f"A disciplinary violation has been recorded for {employee_name}.",
        "",
        f"Category:  {category}",
        f"Incident:  {incident}",
        f"Penalty:   {penalty_label}",
        f"Deduction: {deduction_days} day(s)",
    ]
    if comment:
        lines += ["", f"Comment: {comment}"]
    lines += ["", f"Recorded by: {submitted_by}", "", "— Travel Gate KSA HR System"]
    body = "\n".join(lines)

    # dedupe so we don't double-send when employee and manager share an address
    recipients = {e.strip() for e in (employee_email, manager_email) if e and e.strip()}
    if not recipients:
        logger.info("Violation for %s has no recipient emails; nothing sent", employee_name)
    for to in recipients:
        send_email(to, subject, body)
