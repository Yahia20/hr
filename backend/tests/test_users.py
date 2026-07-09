"""Tests for user role management (PATCH /api/auth/users/{id}): promoting a user
grants the matching page access, field/role validation, role guards, and the
last-active-manager safeguard."""
from conftest import csrf, login

ADMIN_EMAIL = "admin@test.com"


def _uid(admin, email):
    users = admin.get("/api/auth/users").json()
    return next(u["id"] for u in users if u["email"] == email)


def test_promote_grants_permissions_access(admin, new_employee):
    emp, email = new_employee(role="employee")
    assert emp.get("/api/permissions").status_code == 403  # employees can't see permissions
    uid = _uid(admin, email)

    r = admin.patch(f"/api/auth/users/{uid}", json={"role": "hr_officer"}, headers=csrf(admin))
    assert r.status_code == 200 and r.json()["role"] == "hr_officer"

    # The role change dropped the old session; a fresh login picks up the access.
    assert emp.get("/api/permissions").status_code == 401
    emp2 = login(email, "password123")
    assert emp2.get("/api/permissions").status_code == 200


def test_update_department_only(admin, new_employee):
    _, email = new_employee(role="dept_head", department="Ops")
    uid = _uid(admin, email)
    r = admin.patch(f"/api/auth/users/{uid}", json={"department": "Finance"}, headers=csrf(admin))
    assert r.status_code == 200
    assert r.json()["department"] == "Finance" and r.json()["role"] == "dept_head"


def test_update_guards(admin, new_employee):
    officer, _ = new_employee(role="hr_officer")
    _, email = new_employee(role="employee")
    uid = _uid(admin, email)

    # Only HR manager may update.
    assert officer.patch(f"/api/auth/users/{uid}", json={"role": "hr_officer"}, headers=csrf(officer)).status_code == 403
    # Bad role, empty body, unknown user.
    assert admin.patch(f"/api/auth/users/{uid}", json={"role": "root"}, headers=csrf(admin)).status_code == 422
    assert admin.patch(f"/api/auth/users/{uid}", json={}, headers=csrf(admin)).status_code == 400
    assert admin.patch("/api/auth/users/999999", json={"role": "hr_officer"}, headers=csrf(admin)).status_code == 404


def test_update_requires_auth():
    from fastapi.testclient import TestClient
    from app.main import app
    anon = TestClient(app)
    assert anon.patch("/api/auth/users/1", json={"role": "hr_officer"}).status_code == 401


def test_last_manager_cannot_be_demoted(admin, new_employee):
    # With two managers, demoting one is allowed.
    _, email = new_employee(role="employee")
    uid = _uid(admin, email)
    assert admin.patch(f"/api/auth/users/{uid}", json={"role": "hr_manager"}, headers=csrf(admin)).status_code == 200
    assert admin.patch(f"/api/auth/users/{uid}", json={"role": "employee"}, headers=csrf(admin)).status_code == 200

    # The bootstrap admin, now the only active manager, is protected. The guard
    # runs before the update, so a blocked call leaves the admin session intact.
    managers = [u for u in admin.get("/api/auth/users").json() if u["role"] == "hr_manager" and u["is_active"]]
    if len(managers) == 1:
        admin_id = _uid(admin, ADMIN_EMAIL)
        assert admin.patch(f"/api/auth/users/{admin_id}", json={"role": "employee"}, headers=csrf(admin)).status_code == 409
        assert admin.get("/api/auth/users").status_code == 200  # session still valid
