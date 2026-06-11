import json
import logging
import os
import smtplib
import socket
import urllib.error
import urllib.request
from email.message import EmailMessage

logger = logging.getLogger("hr.email")

# Preferred transport: Resend's HTTP API (port 443). Railway blocks outbound
# SMTP ports (25/465/587), so SMTP is kept only as a fallback for hosts that
# allow it (e.g. a future self-managed deploy).
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "HR System <onboarding@resend.dev>")
RESEND_ENDPOINT = "https://api.resend.com/emails"

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)


class _IPv4SMTPSSL(smtplib.SMTP_SSL):
    """SMTP-over-SSL that resolves the host to IPv4 only.

    Railway's container egress has no IPv6 route, so smtplib's default — which
    may pick Gmail's AAAA record — fails with 'Network is unreachable'. We
    override the socket factory to connect via the A record while keeping
    self._host as the TLS server name so the certificate still validates."""

    def _get_socket(self, host, port, timeout):
        ipv4 = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)[0][4]
        sock = socket.create_connection(ipv4, timeout, self.source_address)
        return self.context.wrap_socket(sock, server_hostname=self._host)


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def resend_configured() -> bool:
    return bool(RESEND_API_KEY)


def email_configured() -> bool:
    return resend_configured() or smtp_configured()


def email_transport() -> str:
    if resend_configured():
        return "resend"
    if smtp_configured():
        return "smtp"
    return "none"


def email_from() -> str:
    return RESEND_FROM if resend_configured() else SMTP_FROM


def _send_via_resend(to: str, subject: str, body: str) -> bool:
    payload = json.dumps({"from": RESEND_FROM, "to": [to], "subject": subject, "text": body}).encode()
    req = urllib.request.Request(
        RESEND_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Resend is fronted by Cloudflare, which bans the default
            # "Python-urllib/x.y" agent (403, error 1010). Send our own.
            "User-Agent": "TravelGateHR/1.0 (+https://github.com/Yahia20/hr)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        logger.error("Resend rejected email to %s: HTTP %s %s", to, e.code, detail)
        return False
    except OSError:
        logger.exception("Failed to reach Resend for %s", to)
        return False


def _send_via_smtp(to: str, subject: str, body: str) -> bool:
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with _IPv4SMTPSSL(SMTP_HOST, SMTP_PORT, timeout=15) as srv:
            srv.login(SMTP_USER, SMTP_PASSWORD)
            srv.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        logger.exception("Failed to send email to %s", to)
        return False


def send_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email via the configured transport. Returns False (and
    logs) on any failure — callers must not leak success/failure to API clients
    (user enumeration)."""
    if resend_configured():
        return _send_via_resend(to, subject, body)
    if smtp_configured():
        return _send_via_smtp(to, subject, body)
    logger.warning("No email transport configured; email to %s not sent. Subject: %s", to, subject)
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
