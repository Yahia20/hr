"""Tests for the early-leave permissions (استئذان) API: recording, the monthly
quota, month scoping, attachment access (HR-manager only), and role guards."""
from conftest import csrf, login

# base64("hello") — content doesn't matter, only that it's valid base64.
TINY_B64 = "aGVsbG8="


def make_employee(admin, name):
    r = admin.post(
        "/api/employees",
        json={"name": name, "email": f"{name.replace(' ', '.').lower()}@test.com", "department": "Ops", "manager_email": ""},
        headers=csrf(admin),
    )
    assert r.status_code in (200, 201), r.text
    return name


def _emp_summary(admin, month, name):
    body = admin.get(f"/api/permissions?month={month}").json()
    return next((e for e in body["employees"] if e["employee_name"] == name), None)


def test_record_and_summary(admin):
    name = make_employee(admin, "Perm Ali")
    r = admin.post(
        "/api/permissions",
        json={"employee_name": name, "permission_date": "2026-07-05", "note": "left early"},
        headers=csrf(admin),
    )
    assert r.status_code == 201, r.text
    assert r.json()["has_attachment"] is False

    row = _emp_summary(admin, "2026-07", name)
    assert row and row["used"] == 1 and row["remaining"] == 1
    assert row["permissions"][0]["permission_date"] == "2026-07-05"


def test_quota_enforced(admin):
    name = make_employee(admin, "Perm Quota")
    for _ in range(2):
        r = admin.post("/api/permissions", json={"employee_name": name, "permission_date": "2026-08-10"}, headers=csrf(admin))
        assert r.status_code == 201, r.text
    r = admin.post("/api/permissions", json={"employee_name": name, "permission_date": "2026-08-11"}, headers=csrf(admin))
    assert r.status_code == 409 and r.json()["detail"] == "quota_exceeded"

    row = _emp_summary(admin, "2026-08", name)
    assert row["used"] == 2 and row["remaining"] == 0


def test_month_scoping(admin):
    name = make_employee(admin, "Perm Month")
    admin.post("/api/permissions", json={"employee_name": name, "permission_date": "2026-03-15"}, headers=csrf(admin))
    assert _emp_summary(admin, "2026-03", name)["used"] == 1
    assert _emp_summary(admin, "2026-04", name)["used"] == 0  # quota resets by month


def test_unknown_employee_and_bad_input(admin):
    r = admin.post("/api/permissions", json={"employee_name": "Nobody Here", "permission_date": "2026-07-01"}, headers=csrf(admin))
    assert r.status_code == 400 and r.json()["detail"] == "unknown_employee"

    name = make_employee(admin, "Perm Bad")
    r = admin.post("/api/permissions", json={"employee_name": name, "permission_date": "2026/07/01"}, headers=csrf(admin))
    assert r.status_code == 422  # date format rejected by the schema
    r = admin.post(
        "/api/permissions",
        json={"employee_name": name, "permission_date": "2026-07-01", "attachment": TINY_B64, "attachment_mime": "application/x-msdownload"},
        headers=csrf(admin),
    )
    assert r.status_code == 422  # disallowed mime type

    assert admin.get("/api/permissions?month=2026-7").status_code == 400  # bad month format


def test_attachment_is_manager_only(admin, new_employee):
    name = make_employee(admin, "Perm Attach")
    r = admin.post(
        "/api/permissions",
        json={"employee_name": name, "permission_date": "2026-09-02", "attachment": TINY_B64, "attachment_name": "doc.png", "attachment_mime": "image/png"},
        headers=csrf(admin),
    )
    pid = r.json()["id"]
    assert r.json()["has_attachment"] is True

    got = admin.get(f"/api/permissions/{pid}/attachment").json()
    assert got["attachment"] == TINY_B64 and got["attachment_mime"] == "image/png"

    officer, _ = new_employee(role="hr_officer")
    assert officer.get(f"/api/permissions/{pid}/attachment").status_code == 403


def test_officer_can_record_but_not_delete(admin, new_employee):
    name = make_employee(admin, "Perm Officer")
    officer, _ = new_employee(role="hr_officer")
    r = officer.post("/api/permissions", json={"employee_name": name, "permission_date": "2026-10-01"}, headers=csrf(officer))
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    assert officer.delete(f"/api/permissions/{pid}", headers=csrf(officer)).status_code == 403
    assert admin.delete(f"/api/permissions/{pid}", headers=csrf(admin)).status_code == 204
    assert _emp_summary(admin, "2026-10", name)["used"] == 0


def test_employee_role_forbidden(admin, new_employee):
    emp_user, _ = new_employee(role="employee")
    assert emp_user.get("/api/permissions").status_code == 403
    assert emp_user.post("/api/permissions", json={"employee_name": "x", "permission_date": "2026-07-01"}, headers=csrf(emp_user)).status_code == 403


def test_auth_required_permissions():
    from fastapi.testclient import TestClient
    from app.main import app
    anon = TestClient(app)
    assert anon.get("/api/permissions").status_code == 401
