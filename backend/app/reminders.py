"""Document-expiry email reminders.

A daily digest of every document that needs attention (expired / within one week /
within two weeks) is emailed to the configured recipients. Recipients and the
on/off toggle live in the `app_settings` table so they're editable from the UI
without a redeploy; an optional `DOC_ALERT_EMAIL` env var seeds the recipients on
first run for env-only deployments.
"""
import logging
import os
import re
from datetime import datetime

from .db import db
from .doc_config import ALERT_ELIGIBLE_SQL, load_thresholds, thresholds_for
from .emailer import email_configured, send_email
from .expiry import ATTENTION_STATUSES, compute_status

logger = logging.getLogger("hr.reminders")

# app_settings keys
K_RECIPIENTS = "doc_alert_recipients"
K_ENABLED = "doc_alert_enabled"
K_LAST_SENT = "doc_alert_last_sent"

_SPLIT = re.compile(r"[,\s;]+")
_CATEGORY_LABEL = {
    "iqama": "Iqama (Residence Permit)",
    "contract": "Contract",
    "rent": "Rent",
    "vehicle": "Vehicle",
    "license": "License",
}
# Readable names for the fixed rent slots, so the digest doesn't print raw keys.
_RENT_LABEL = {"rawda": "Al-Rawda Branch", "hamra": "Al-Hamra Branch", "housing": "Housing"}


def _get(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row is not None else default


def _set(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def parse_recipients(raw: str) -> list[str]:
    """Split a free-form recipients string into a de-duplicated, ordered list."""
    seen, out = set(), []
    for part in _SPLIT.split(raw or ""):
        p = part.strip()
        if p and "@" in p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


def read_config(conn) -> dict:
    recipients = _get(conn, K_RECIPIENTS)
    if not recipients:
        # Seed once from the env var for env-only deployments.
        recipients = os.environ.get("DOC_ALERT_EMAIL", "").strip()
    enabled_raw = _get(conn, K_ENABLED, "")
    # Default: on as soon as there's a recipient, unless explicitly turned off.
    enabled = enabled_raw == "1" if enabled_raw else bool(parse_recipients(recipients))
    return {
        "recipients": recipients,
        "recipient_list": parse_recipients(recipients),
        "enabled": enabled,
        "last_sent": _get(conn, K_LAST_SENT) or None,
    }


def write_config(recipients: str, enabled: bool) -> dict:
    with db() as conn:
        _set(conn, K_RECIPIENTS, (recipients or "").strip())
        _set(conn, K_ENABLED, "1" if enabled else "0")
    with db() as conn:
        return read_config(conn)


def collect_due(conn) -> list[dict]:
    """Documents that need attention, most urgent first (per-category thresholds)."""
    tmap = load_thresholds(conn)
    # The digest never needs the base64 attachment; skip it to keep the read
    # light. Orphaned employee documents (owner off the roster) are excluded.
    rows = conn.execute(
        "SELECT id, category, owner, title, start_date, end_date, note, "
        f"created_by, created_at FROM documents WHERE {ALERT_ELIGIBLE_SQL}"
    ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        yellow, red = thresholds_for(d["category"], tmap)
        st = compute_status(d["end_date"], yellow, red)
        if st["status"] in ATTENTION_STATUSES:
            items.append({**d, **st})
    items.sort(key=lambda d: d["days_left"] if d["days_left"] is not None else 1 << 30)
    return items


def _describe(d: dict) -> str:
    if d["category"] in ("vehicle", "license"):
        who = d["title"] or d["owner"] or "—"
    else:
        who = d["owner"] or d["title"] or "—"
    label = _CATEGORY_LABEL.get(d["category"], d["category"])
    if d["category"] == "rent" and d["owner"]:
        label = f"Rent — {_RENT_LABEL.get(d['owner'], d['owner'])}"
    days = d["days_left"]
    if d["status"] == "expired":
        tag = f"EXPIRED {abs(days)} day(s) ago"
    elif days == 0:
        tag = "expires TODAY"
    else:
        tag = f"{days} day(s) left"
    return f"- [{tag}] {who} — {label} — ends {d['end_date']}"


def build_digest(items: list[dict]) -> tuple[str, str]:
    n = len(items)
    subject = f"HR document expiry reminder — {n} item(s) need attention"
    lines = [
        f"{n} document(s) are expired or expiring soon and need attention:",
        "",
        *[_describe(d) for d in items],
        "",
        "Open the HR system → Employee Documents / Company Documents to renew them.",
        "",
        "— Travel Gate KSA HR System",
    ]
    return subject, "\n".join(lines)


def send_reminders(*, require_enabled: bool) -> dict:
    """Send the digest. `require_enabled=True` for the scheduler (respects the
    toggle); `False` for a manual "send now" (always attempts). Returns a summary
    and never raises."""
    try:
        with db() as conn:
            cfg = read_config(conn)
            recipients = cfg["recipient_list"]
            if require_enabled and not cfg["enabled"]:
                return {"sent": False, "reason": "disabled", "count": 0}
            if not recipients:
                return {"sent": False, "reason": "no_recipients", "count": 0}
            if not email_configured():
                return {"sent": False, "reason": "email_not_configured", "count": 0}
            items = collect_due(conn)
        if not items:
            return {"sent": False, "reason": "nothing_due", "count": 0, "recipients": recipients}

        subject, body = build_digest(items)
        results = [send_email(to, subject, body) for to in recipients]
        ok = any(results)
        # Only stamp "last sent" when a message actually went out, so the UI
        # doesn't claim delivery on a run where every send failed.
        if ok:
            with db() as conn:
                _set(conn, K_LAST_SENT, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        return {
            "sent": ok,
            "reason": "ok" if ok else "send_failed",
            "count": len(items),
            "recipients": recipients,
        }
    except Exception:  # never let a reminder failure escape (scheduler/endpoint)
        logger.exception("Failed to send document reminders")
        return {"sent": False, "reason": "error", "count": 0}
