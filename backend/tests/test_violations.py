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


def test_day_override_clears_hours_and_is_labelled(admin):
    # First "Food & Beverage" violation is Orange (4.5 hrs + 0.5 day). Overriding
    # the days must clear the matrix hours so the row isn't deducted twice.
    r = admin.post("/api/violations", json={
        "employee_name": "Ovr Guy", "category": "Policy Violations",
        "incident": "Food & Beverage in Prohibited Areas", "override_days": 3,
    }, headers=csrf(admin))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["penalty_color"] == "Orange"
    assert body["deduction_days"] == 3 and body["deduction_hours"] == 0
    assert "Override" in body["penalty_label"]


def test_investigation_can_carry_deduction_and_shows_it(admin):
    r = admin.post("/api/violations", json={
        "employee_name": "Inv Guy", "category": "Attendance & Adherence",
        "incident": "Late Arrival", "force_investigation": True, "override_days": 2,
    }, headers=csrf(admin))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["penalty_color"] == "Investigation"
    assert body["deduction_days"] == 2                       # both allowed together
    assert "2" in body["penalty_label"] and "Override" in body["penalty_label"]  # not hidden


def test_active_freezes_counts_distinct_employees(admin):
    before = admin.get("/api/stats/dashboard").json()["totals"]["active_freezes"]
    # Two different first-time Black incidents → two active freezes, one person.
    for incident in ("Attendance Manipulation", "Early Leave"):
        r = admin.post("/api/violations", json={
            "employee_name": "Frozen Guy", "category": "Attendance & Adherence", "incident": incident,
        }, headers=csrf(admin))
        assert r.status_code == 201 and r.json()["freeze_months"] == 3
    after = admin.get("/api/stats/dashboard").json()["totals"]["active_freezes"]
    assert after - before == 1
