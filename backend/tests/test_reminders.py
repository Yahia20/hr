"""Tests for the document-expiry email reminders: config roundtrip, the
manager-only guard, the send gating (no recipients / email not configured), and
that collect_due only surfaces documents needing attention."""
from datetime import date, timedelta

from conftest import csrf


def _in(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def test_reminders_requires_manager(admin, new_employee):
    officer, _ = new_employee(role="hr_officer")
    assert officer.get("/api/settings/reminders").status_code == 403
    assert admin.get("/api/settings/reminders").status_code == 200


def test_config_roundtrip(admin):
    r = admin.post(
        "/api/settings/reminders",
        json={"recipients": "ahmed@example.com, ahmed@example.com other@example.com", "enabled": True},
        headers=csrf(admin),
    )
    assert r.status_code == 200
    body = admin.get("/api/settings/reminders").json()
    assert "ahmed@example.com" in body["recipients"]
    assert body["enabled"] is True
    assert body["email_configured"] is False  # no transport in tests


def test_run_gating(admin):
    # No recipients -> nothing sent.
    admin.post("/api/settings/reminders", json={"recipients": "", "enabled": True}, headers=csrf(admin))
    r = admin.post("/api/settings/reminders/run", headers=csrf(admin)).json()
    assert r["sent"] is False and r["reason"] == "no_recipients"

    # Recipients set, but no email transport configured in the test env.
    admin.post("/api/settings/reminders", json={"recipients": "a@b.com", "enabled": True}, headers=csrf(admin))
    r = admin.post("/api/settings/reminders/run", headers=csrf(admin)).json()
    assert r["sent"] is False and r["reason"] == "email_not_configured"


def test_disabled_blocks_scheduler_only(admin):
    from app.reminders import send_reminders

    admin.post("/api/settings/reminders", json={"recipients": "a@b.com", "enabled": False}, headers=csrf(admin))
    # Scheduler path respects the toggle...
    assert send_reminders(require_enabled=True)["reason"] == "disabled"
    # ...manual "run now" ignores it (still blocked later by email config).
    assert send_reminders(require_enabled=False)["reason"] == "email_not_configured"


def test_collect_due_only_attention(admin):
    from app.db import db
    from app.reminders import collect_due

    admin.post("/api/documents", json={
        "category": "license", "title": "Reminder Expired",
        "start_date": _in(-40), "end_date": _in(-3),
    }, headers=csrf(admin))
    admin.post("/api/documents", json={
        "category": "license", "title": "Reminder Fine",
        "start_date": _in(-10), "end_date": _in(300),
    }, headers=csrf(admin))

    with db() as conn:
        items = collect_due(conn)
    titles = {i["title"]: i["status"] for i in items}
    assert titles.get("Reminder Expired") == "expired"
    assert "Reminder Fine" not in titles  # green never surfaces
    # Sorted most-urgent first.
    days = [i["days_left"] for i in items]
    assert days == sorted(days)
