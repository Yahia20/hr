"""ATS privacy: the retention clock, the expiry sweep, early CV removal, the
audit trail, and the candidate stage emails.

Retention is a business-policy ceiling, not a legal safe harbour: the clock
starts ONCE, when an application first ends (rejected / hired) or its job
closes, and is never pushed back by later edits, re-scoring or a reopened job.
At ``erase_after`` the whole application is deleted (children cascade).

Every timestamp here is UTC, formatted ``YYYY-MM-DDTHH:MM:SSZ`` so string
comparison orders correctly in both SQLite and PostgreSQL.
"""
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from .db import db, lock
from .emailer import email_configured, send_email

logger = logging.getLogger("hr.recruitment.privacy")

# Bump whenever the candidate-facing notice text changes (frontend i18n: atsNotice*).
NOTICE_VERSION = "2026-10-v1"
NOTICE_CHANNELS = ("email", "whatsapp", "in_person", "other")
TERMINAL_STAGES = ("rejected", "hired")

K_DAYS = "ats_retention_days"
K_LAST = "ats_retention_last"
K_EMAILS = "ats_stage_emails_enabled"
K_TEMPLATES = "ats_stage_email_templates"
DEFAULT_DAYS = 180
MIN_DAYS, MAX_DAYS = 1, 365

EMAIL_STAGES = ("interview", "offer", "rejected")
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_ALLOWED_PLACEHOLDERS = {"name", "job"}
DEFAULT_TEMPLATES = {
    "interview": {
        "en": {"subject": "Interview invitation — {job}",
               "body": "Dear {name},\n\nThank you for applying for {job} at Travel Gate. We would like to invite you to an interview. Our HR team will contact you to arrange a time.\n\nTravel Gate HR"},
        "ar": {"subject": "دعوة لمقابلة — {job}",
               "body": "عزيزي/عزيزتي {name}،\n\nشكراً لتقديمك على وظيفة {job} في ترافل جيت. يسعدنا دعوتك لمقابلة، وسيتواصل معك فريق الموارد البشرية لتحديد الموعد.\n\nالموارد البشرية — ترافل جيت"},
    },
    "offer": {
        "en": {"subject": "Job offer — {job}",
               "body": "Dear {name},\n\nWe are pleased to let you know that Travel Gate would like to offer you the {job} position. Our HR team will contact you with the details.\n\nTravel Gate HR"},
        "ar": {"subject": "عرض وظيفي — {job}",
               "body": "عزيزي/عزيزتي {name}،\n\nيسعدنا إبلاغك بأن ترافل جيت ترغب في تقديم عرض لك على وظيفة {job}. سيتواصل معك فريق الموارد البشرية بالتفاصيل.\n\nالموارد البشرية — ترافل جيت"},
    },
    "rejected": {
        "en": {"subject": "Your application — {job}",
               "body": "Dear {name},\n\nThank you for your interest in the {job} position at Travel Gate. After careful review we will not be moving forward with your application at this time. We wish you every success.\n\nTravel Gate HR"},
        "ar": {"subject": "طلبك للتوظيف — {job}",
               "body": "عزيزي/عزيزتي {name}،\n\nشكراً لاهتمامك بوظيفة {job} في ترافل جيت. بعد المراجعة، لن نتمكن من المضي في طلبك حالياً. نتمنى لك كل التوفيق.\n\nالموارد البشرية — ترافل جيت"},
    },
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_str(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row is not None else default


def _set(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def retention_days(conn) -> int:
    try:
        value = int(_get(conn, K_DAYS, str(DEFAULT_DAYS)))
    except ValueError:
        return DEFAULT_DAYS
    return min(MAX_DAYS, max(MIN_DAYS, value))


def last_run(conn) -> dict:
    try:
        return json.loads(_get(conn, K_LAST, "{}") or "{}")
    except json.JSONDecodeError:
        return {}


def set_retention_days(days: int) -> int:
    if not MIN_DAYS <= days <= MAX_DAYS:
        raise ValueError(f"retention days must be between {MIN_DAYS} and {MAX_DAYS}")
    with db() as conn:
        _set(conn, K_DAYS, str(days))
    return days


def log_event(conn, action: str, applicant_id, job_id, actor: str, reason: str = "") -> None:
    conn.execute(
        "INSERT INTO ats_privacy_events (action, applicant_id, job_id, actor, reason, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (action, applicant_id, job_id, actor, reason, utc_str(utc_now())),
    )


def _start_clocks(conn, where: str, params: tuple) -> None:
    """Start the clock on matching applicants that have none yet (never extends one).
    The period is today's setting, capped by what the candidate's notice promised."""
    current = retention_days(conn)
    start = utc_now()
    rows = conn.execute(
        f"SELECT id, notice_retention_days FROM applicants WHERE {where} AND retention_started_at IS NULL", params
    ).fetchall()
    for row in rows:
        days = min(current, row["notice_retention_days"] or current)
        conn.execute(
            "UPDATE applicants SET retention_started_at=?, erase_after=?, retention_days_snapshot=? "
            "WHERE id=? AND retention_started_at IS NULL",
            (utc_str(start), utc_str(start + timedelta(days=days)), days, row["id"]),
        )


def start_retention_for_applicant(conn, applicant_id: int) -> None:
    _start_clocks(conn, "id=?", (applicant_id,))


def start_retention_for_job(conn, job_id: int) -> None:
    _start_clocks(conn, "job_id=?", (job_id,))


def cancel_pending_emails(conn, applicant_id: int) -> None:
    conn.execute(
        "UPDATE applicant_stage_history SET notify_status='cancelled' WHERE applicant_id=? AND notify_status='pending'",
        (applicant_id,),
    )


def _strip_breakdown(raw: str) -> str:
    try:
        items = json.loads(raw or "[]")
    except json.JSONDecodeError:
        items = []
    keep = [
        {"criterion": i.get("criterion"), "weight": i.get("weight"), "score_0_4": i.get("score_0_4"),
         "evidence": [], "missing": []}
        for i in items if isinstance(i, dict)
    ]
    return json.dumps(keep, separators=(",", ":"))


def purge_cv(conn, applicant_id: int, actor: str, reason: str) -> bool:
    """Early CV removal. Caller holds ``lock(conn)``. Keeps identity, numeric
    scores and stage until ``erase_after``; removes the CV and everything derived
    from or written about its contents. Returns False if absent or already purged."""
    row = conn.execute(
        "SELECT job_id, score_breakdown FROM applicants WHERE id=? AND cv_purged_at IS NULL", (applicant_id,)
    ).fetchone()
    if row is None:
        return False
    conn.execute(
        "UPDATE applicants SET cv_attachment='', cv_name='', cv_mime='', cv_text='', parsed='{}', "
        "corrections='{}', score_breakdown=?, gate_failures='[]', source='', nationality='', city='', "
        "notes='', needs_manual_review=0, cv_purged_at=?, cv_purge_reason=?, "
        "row_version=row_version+1 WHERE id=?",
        (_strip_breakdown(row["score_breakdown"]), utc_str(utc_now()), reason, applicant_id),
    )
    cancel_pending_emails(conn, applicant_id)
    conn.execute(
        "UPDATE applicant_stage_history SET note='', notify_subject='', notify_body='' WHERE applicant_id=?",
        (applicant_id,),
    )
    # A removed CV still leaves identity behind, so the deletion deadline must exist.
    start_retention_for_applicant(conn, applicant_id)
    conn.execute("DELETE FROM interview_feedback WHERE applicant_id=?", (applicant_id,))
    conn.execute("DELETE FROM ats_semantic_runs WHERE applicant_id=?", (applicant_id,))
    log_event(conn, "cv_removed", applicant_id, row["job_id"], actor, reason)
    return True


def sweep(*, dry_run: bool, actor: str = "scheduler") -> dict:
    """Delete every application whose ``erase_after`` has passed. A dry run
    only reads. Each deletion is its own short locked transaction."""
    now = utc_str(utc_now())
    with db() as conn:
        due = conn.execute(
            "SELECT id, job_id, erase_after FROM applicants "
            "WHERE erase_after IS NOT NULL AND erase_after <= ? ORDER BY erase_after, id",
            (now,),
        ).fetchall()
    if dry_run:
        return {"dry_run": True, "due": len(due), "items": [{"id": r["id"], "erase_after": r["erase_after"]} for r in due]}

    deleted = failed = 0
    for r in due:
        try:
            with db() as conn:
                lock(conn)
                still = conn.execute(
                    "SELECT 1 FROM applicants WHERE id=? AND erase_after IS NOT NULL AND erase_after <= ?",
                    (r["id"], now),
                ).fetchone()
                if still is None:
                    continue
                conn.execute("DELETE FROM applicants WHERE id=?", (r["id"],))
                log_event(conn, "expired", r["id"], r["job_id"], actor, "retention")
            deleted += 1
        except Exception:  # one bad row must not stop the sweep
            failed += 1
            logger.exception("retention: could not erase applicant id=%s", r["id"])
    summary = {"dry_run": False, "due": len(due), "deleted": deleted, "failed": failed, "actor": actor, "at": now}
    with db() as conn:
        previous = last_run(conn)
        status = {"last_attempt": summary, "last_success": summary if failed == 0 else previous.get("last_success")}
        _set(conn, K_LAST, json.dumps(status, separators=(",", ":")))
    if deleted or failed:
        logger.info("retention sweep: due=%s deleted=%s failed=%s", len(due), deleted, failed)
    return summary


# --- Candidate stage emails -------------------------------------------------

def emails_enabled(conn) -> bool:
    return _get(conn, K_EMAILS, "0") == "1"


def email_templates(conn) -> dict:
    try:
        stored = json.loads(_get(conn, K_TEMPLATES, "{}") or "{}")
    except json.JSONDecodeError:
        stored = {}
    merged = json.loads(json.dumps(DEFAULT_TEMPLATES))
    for stage, langs in (stored or {}).items():
        if stage in merged and isinstance(langs, dict):
            for lang, tpl in langs.items():
                if lang in ("en", "ar") and isinstance(tpl, dict):
                    merged[stage][lang].update({k: str(v) for k, v in tpl.items() if k in ("subject", "body")})
    return merged


def validate_templates(templates: dict) -> dict:
    clean = {}
    for stage in EMAIL_STAGES:
        clean[stage] = {}
        for lang in ("en", "ar"):
            tpl = ((templates or {}).get(stage) or {}).get(lang) or {}
            subject, body = str(tpl.get("subject", "")).strip(), str(tpl.get("body", "")).strip()
            if not subject or not body or len(subject) > 200 or len(body) > 5000:
                raise ValueError(f"{stage}/{lang}: subject and body are required (max 200 / 5000 chars)")
            if "\n" in subject or "\r" in subject:
                raise ValueError(f"{stage}/{lang}: the subject must be one line")
            unknown = set(_PLACEHOLDER.findall(subject + body)) - _ALLOWED_PLACEHOLDERS
            if unknown:
                raise ValueError(f"{stage}/{lang}: only {{name}} and {{job}} are allowed")
            clean[stage][lang] = {"subject": subject, "body": body}
    return clean


def save_email_settings(enabled: bool, templates: dict) -> dict:
    clean = validate_templates(templates)
    with db() as conn:
        _set(conn, K_EMAILS, "1" if enabled else "0")
        _set(conn, K_TEMPLATES, json.dumps(clean, ensure_ascii=False, separators=(",", ":")))
    return {"enabled": enabled, "templates": clean}


def render_email(conn, stage: str, lang: str, name: str, job: str) -> dict:
    tpl = email_templates(conn)[stage][lang]
    values = {"name": name or ("المتقدم" if lang == "ar" else "Candidate"), "job": job}
    fill = lambda text: _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)  # noqa: E731
    return {"subject": fill(tpl["subject"]).replace("\n", " "), "body": fill(tpl["body"])}


def message_hash(message: dict) -> str:
    """Binds a stage move to the exact message HR saw in the preview."""
    return hashlib.sha256(f"{message['subject']}\n{message['body']}".encode("utf-8")).hexdigest()


_SIMPLE_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


def valid_recipient(address: str) -> bool:
    return bool(address) and len(address) <= 254 and bool(_SIMPLE_EMAIL.match(address))


def send_stage_email(history_id: int) -> None:
    """Best-effort background send. Reloads by history id, claims the row once,
    sends outside any transaction, records 'accepted' (by the provider — not
    proof of delivery) or 'failed'. Never retries automatically."""
    with db() as conn:
        lock(conn)
        h = conn.execute(
            "SELECT h.id, h.applicant_id, h.new_stage, h.notify_status, h.notify_subject, h.notify_body, "
            "a.stage, a.email, a.cv_purged_at, "
            "(SELECT MAX(id) FROM applicant_stage_history x WHERE x.applicant_id = h.applicant_id) AS latest_id "
            "FROM applicant_stage_history h JOIN applicants a ON a.id = h.applicant_id WHERE h.id=?",
            (history_id,),
        ).fetchone()
        if h is None or h["notify_status"] != "pending":
            return
        superseded = h["latest_id"] != h["id"] or h["stage"] != h["new_stage"]
        if (superseded or h["cv_purged_at"] or not valid_recipient(h["email"]) or not emails_enabled(conn)
                or not h["notify_subject"]):
            conn.execute("UPDATE applicant_stage_history SET notify_status='cancelled' WHERE id=?", (history_id,))
            return
        message = {"subject": h["notify_subject"], "body": h["notify_body"]}
        conn.execute("UPDATE applicant_stage_history SET notify_status='sending' WHERE id=?", (history_id,))
        to = h["email"]
    ok = False
    try:
        ok = email_configured() and send_email(to, message["subject"], message["body"])
    finally:
        with db() as conn:
            conn.execute(
                "UPDATE applicant_stage_history SET notify_status=?, notified_at=? WHERE id=? AND notify_status='sending'",
                ("accepted" if ok else "failed", utc_str(utc_now()), history_id),
            )


def recover_interrupted_emails() -> None:
    """At startup: queued sends are cancelled, in-flight ones become 'unknown'
    (the provider may or may not have accepted them) — nothing is resent."""
    with db() as conn:
        conn.execute("UPDATE applicant_stage_history SET notify_status='cancelled' WHERE notify_status='pending'")
        conn.execute("UPDATE applicant_stage_history SET notify_status='unknown' WHERE notify_status='sending'")
