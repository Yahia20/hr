"""Tests for the expiry-tracked documents API: create/list/renew, the
traffic-light status bands (green/yellow/red/expired) computed from end_date,
slot uniqueness for employee & rent records, attachment access (HR-manager
only), and role guards."""
from datetime import date, timedelta

from conftest import csrf

# base64("hello") — content doesn't matter, only that it's valid base64.
TINY_B64 = "aGVsbG8="


def _in(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _mk(client, **over):
    body = {
        "category": "license",
        "title": "Test License",
        "start_date": _in(-30),
        "end_date": _in(30),
    }
    body.update(over)
    r = client.post("/api/documents", json=body, headers=csrf(client))
    return r


def test_create_and_list(admin):
    r = _mk(admin, title="Trade License", end_date=_in(60))
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["status"] == "green" and doc["has_attachment"] is False

    rows = admin.get("/api/documents?category=license").json()
    assert any(d["id"] == doc["id"] and d["title"] == "Trade License" for d in rows)


def test_status_bands(admin):
    cases = {
        _in(30): "green",
        _in(15): "green",    # 15 days > 14 -> still green
        _in(14): "yellow",   # exactly two weeks
        _in(8): "yellow",
        _in(7): "red",       # exactly one week
        _in(1): "red",
        _in(0): "red",       # expires today
        _in(-1): "expired",
    }
    for end, expected in cases.items():
        doc = _mk(admin, end_date=end, start_date=_in(-40)).json()
        assert doc["status"] == expected, f"{end} -> {doc['status']}, expected {expected}"


def test_end_before_start_rejected(admin):
    r = _mk(admin, start_date=_in(10), end_date=_in(5))
    assert r.status_code == 422  # schema-level model validator


def test_slot_uniqueness_and_renew(admin):
    first = _mk(admin, category="iqama", owner="Doc Worker", title="Iqama", end_date=_in(20))
    assert first.status_code == 201, first.text
    did = first.json()["id"]

    # A second iqama for the same person collides with the slot constraint.
    dup = _mk(admin, category="iqama", owner="Doc Worker", title="Iqama", end_date=_in(400))
    assert dup.status_code == 409 and dup.json()["detail"] == "slot_exists"

    # Renewing edits the existing row in place; status flips green.
    r = admin.patch(f"/api/documents/{did}", json={"end_date": _in(400)}, headers=csrf(admin))
    assert r.status_code == 200 and r.json()["status"] == "green"
    assert r.json()["end_date"] == _in(400)


def test_open_categories_allow_multiple(admin):
    a = _mk(admin, category="license", title="License A")
    b = _mk(admin, category="license", title="License B")
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["id"] != b.json()["id"]


def test_patch_rejects_bad_range(admin):
    did = _mk(admin, category="vehicle", title="Car Insurance").json()["id"]
    r = admin.patch(f"/api/documents/{did}", json={"start_date": _in(20), "end_date": _in(10)}, headers=csrf(admin))
    assert r.status_code == 400


def test_bad_category(admin):
    r = _mk(admin, category="passport")
    assert r.status_code == 422  # not in the allow-list
    assert admin.get("/api/documents?category=passport").status_code == 400


def test_attachment_is_manager_only(admin, new_employee):
    doc = _mk(admin, category="contract", owner="Attach Worker", title="Contract",
              attachment=TINY_B64, attachment_name="c.png", attachment_mime="image/png").json()
    assert doc["has_attachment"] is True

    got = admin.get(f"/api/documents/{doc['id']}/attachment").json()
    assert got["attachment"] == TINY_B64 and got["attachment_mime"] == "image/png"

    officer, _ = new_employee(role="hr_officer")
    assert officer.get(f"/api/documents/{doc['id']}/attachment").status_code == 403


def test_officer_can_manage_but_not_delete(admin, new_employee):
    officer, _ = new_employee(role="hr_officer")
    r = _mk(officer, category="rent", owner="rawda", title="Rawda Branch Rent")
    assert r.status_code == 201, r.text
    did = r.json()["id"]

    assert officer.patch(f"/api/documents/{did}", json={"note": "updated"}, headers=csrf(officer)).status_code == 200
    assert officer.delete(f"/api/documents/{did}", headers=csrf(officer)).status_code == 403
    assert admin.delete(f"/api/documents/{did}", headers=csrf(admin)).status_code == 204


def test_employee_role_forbidden(admin, new_employee):
    emp_user, _ = new_employee(role="employee")
    assert emp_user.get("/api/documents").status_code == 403
    assert _mk(emp_user).status_code == 403


def test_auth_required_documents():
    from fastapi.testclient import TestClient
    from app.main import app
    anon = TestClient(app)
    assert anon.get("/api/documents").status_code == 401
