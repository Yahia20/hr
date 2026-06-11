import json
import logging
import os
import smtplib
import socket
import urllib.error
import urllib.request
from email.message import EmailMessage

logger = logging.getLogger("hr.email")

# Email transports, in priority order: Brevo -> Resend -> SMTP. The HTTP APIs
# (Brevo/Resend) use port 443; Railway blocks outbound SMTP (25/465/587), so
# SMTP is only a fallback for hosts that allow it.
#
# Brevo only needs a *verified single sender* (a confirmation-link on any address
# you own) to email arbitrary recipients — no domain/DNS — so it's the choice
# when you don't own a domain. Resend can email arbitrary recipients only after
# a domain is verified (otherwise test mode: owner's address only).
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_SENDER = os.environ.get("BREVO_SENDER", "")  # a Brevo-verified sender email
BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME", "Travel Gate KSA HR")
BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"

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


def brevo_configured() -> bool:
    return bool(BREVO_API_KEY and BREVO_SENDER)


def email_configured() -> bool:
    return brevo_configured() or resend_configured() or smtp_configured()


def email_transport() -> str:
    if brevo_configured():
        return "brevo"
    if resend_configured():
        return "resend"
    if smtp_configured():
        return "smtp"
    return "none"


def email_from() -> str:
    if brevo_configured():
        return f"{BREVO_SENDER_NAME} <{BREVO_SENDER}>"
    if resend_configured():
        return RESEND_FROM
    return SMTP_FROM


def _post_json(url: str, headers: dict, body: dict, provider: str, to: str) -> bool:
    data = json.dumps(body).encode()
    base = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        # These APIs sit behind Cloudflare, which bans the default
        # "Python-urllib/x.y" agent (403, error 1010). Send our own.
        "User-Agent": "TravelGateHR/1.0 (+https://github.com/Yahia20/hr)",
    }
    req = urllib.request.Request(url, data=data, method="POST", headers={**base, **headers})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        logger.error("%s rejected email to %s: HTTP %s %s", provider, to, e.code, detail)
        return False
    except OSError:
        logger.exception("Failed to reach %s for %s", provider, to)
        return False


def _send_via_brevo(to: str, subject: str, body: str) -> bool:
    return _post_json(
        BREVO_ENDPOINT,
        {"api-key": BREVO_API_KEY},
        {
            "sender": {"email": BREVO_SENDER, "name": BREVO_SENDER_NAME},
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body,
        },
        "Brevo",
        to,
    )


def _send_via_resend(to: str, subject: str, body: str) -> bool:
    return _post_json(
        RESEND_ENDPOINT,
        {"Authorization": f"Bearer {RESEND_API_KEY}"},
        {"from": RESEND_FROM, "to": [to], "subject": subject, "text": body},
        "Resend",
        to,
    )


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
    if brevo_configured():
        return _send_via_brevo(to, subject, body)
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
