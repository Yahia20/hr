"""Tests for the violations API. Focused on the audit-trail guarantee
(submitted_by can't be spoofed), category validation, date-filter validation,
and role guards. The full escalation-logic suite is tracked separately."""
from conftest import csrf


def _log(client, **over):
    body = {"employee_name": "Test Emp", "category": "Attendance & Adherence", "incident": "Late Arrival"}
    body.update(over)
    return client.post("/api/violations", json=body, headers=csrf(client))


def test_submitted_by_is_always_session_user(admin):
    me = admin.get("/api/auth/me").json()["user"]["name"]
    r = _log(admin, submitted_by="Spoofed CEO")
    assert r.status_code == 201, r.text
    assert r.json()["submitted_by"] == me
    assert r.json()["submitted_by"] != "Spoofed CEO"  # payload value is ignored


def test_unknown_category_or_incident_rejected(admin):
    assert _log(admin, category="Nope").status_code == 400
    assert _log(admin, incident="Nope").status_code == 400


def test_invalid_date_filter_rejected(admin):
    assert admin.get("/api/violations?date_from=2026-99-99").status_code == 400
    assert admin.get("/api/violations?date_to=2026-02-31").status_code == 400


def test_officer_can_log_but_employee_cannot(admin, new_employee):
    officer, _ = new_employee(role="hr_officer")
    assert _log(officer).status_code == 201
    emp_user, _ = new_employee(role="employee")
    assert _log(emp_user).status_code == 403
