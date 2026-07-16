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


def test_expiring_summary(admin):
    # Employee docs only count toward alerts while their owner is on the roster.
    for name in ("Exp A", "Exp B"):
        admin.post("/api/employees", json={"name": name, "email": f"{name.replace(' ', '')}@e.com", "department": "Ops", "manager_email": ""}, headers=csrf(admin))
    # Seed one of each urgency in distinct slots/lists.
    _mk(admin, category="iqama", owner="Exp A", title="Iqama", end_date=_in(3))      # red
    _mk(admin, category="contract", owner="Exp B", title="Contract", end_date=_in(10))  # yellow
    _mk(admin, category="license", title="Old License", start_date=_in(-40), end_date=_in(-2))  # expired
    _mk(admin, category="license", title="Fresh License", end_date=_in(300))         # green (excluded)

    body = admin.get("/api/documents/expiring").json()
    statuses = {i["status"] for i in body["items"]}
    assert "green" not in statuses  # green never appears
    assert body["counts"]["total"] == len(body["items"])
    assert body["counts"]["red"] >= 1 and body["counts"]["yellow"] >= 1 and body["counts"]["expired"] >= 1
    assert body["by_scope"]["employee"] >= 2  # the iqama + contract above
    # Most urgent (smallest days_left) first.
    days = [i["days_left"] for i in body["items"]]
    assert days == sorted(days)


def test_expiring_requires_hr(admin, new_employee):
    emp_user, _ = new_employee(role="employee")
    assert emp_user.get("/api/documents/expiring").status_code == 403


def test_excel_export(admin):
    _mk(admin, category="license", title="Export Me", end_date=_in(90))
    r = admin.get("/api/documents/export?category=license")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert r.content[:2] == b"PK"  # xlsx is a zip container


def test_renewal_history(admin):
    did = _mk(admin, category="iqama", owner="Hist Worker", title="Iqama", end_date=_in(20)).json()["id"]
    admin.patch(f"/api/documents/{did}", json={"end_date": _in(200)}, headers=csrf(admin))
    admin.patch(f"/api/documents/{did}", json={"end_date": _in(400)}, headers=csrf(admin))
    # A note-only edit must NOT create a history row.
    admin.patch(f"/api/documents/{did}", json={"note": "just a note"}, headers=csrf(admin))

    hist = admin.get(f"/api/documents/{did}/history").json()
    assert len(hist) == 2
    assert hist[0]["new_end"] == _in(400) and hist[0]["old_end"] == _in(200)  # newest first
    assert hist[1]["new_end"] == _in(200) and hist[1]["old_end"] == _in(20)
    assert hist[0]["changed_by"]  # records who renewed


def test_per_category_thresholds(admin):
    try:
        # Widen iqama's window: warn red within 30 days, yellow within 60.
        r = admin.post("/api/settings/thresholds", json={"thresholds": {"iqama": {"yellow": 60, "red": 30}}}, headers=csrf(admin))
        assert r.status_code == 200
        assert admin.get("/api/settings/thresholds").json()["thresholds"]["iqama"] == {"yellow": 60, "red": 30}

        # An iqama 20 days out is now RED (would be green under the 14/7 default)...
        iq = _mk(admin, category="iqama", owner="Threshold Worker", title="Iqama", end_date=_in(20)).json()
        assert iq["status"] == "red"
        # ...while a license 20 days out still uses the default and is green.
        lic = _mk(admin, category="license", title="Still Default", end_date=_in(20)).json()
        assert lic["status"] == "green"
    finally:
        # Restore defaults even if an assertion above fails, so 60/30 doesn't
        # leak into the shared session DB and skew later tests.
        admin.post("/api/settings/thresholds", json={"thresholds": {"iqama": {"yellow": 14, "red": 7}}}, headers=csrf(admin))


def test_deleted_employee_docs_excluded_from_alerts(admin):
    # An employee document counts toward alerts only while the employee exists.
    admin.post("/api/employees", json={"name": "Ghost Emp", "email": "ghost@e.com", "department": "Ops", "manager_email": ""}, headers=csrf(admin))
    admin.post("/api/documents", json={"category": "iqama", "owner": "Ghost Emp", "title": "Iqama", "start_date": _in(-300), "end_date": _in(3)}, headers=csrf(admin))

    def ghost_in_expiring():
        return any(i["owner"] == "Ghost Emp" for i in admin.get("/api/documents/expiring").json()["items"])

    assert ghost_in_expiring()  # red iqama shows up while employed
    assert admin.delete("/api/employees/Ghost%20Emp", headers=csrf(admin)).status_code == 204
    assert not ghost_in_expiring()  # no longer counted after deletion
    # ...but the document itself is preserved, not destroyed.
    kept = admin.get("/api/documents?category=iqama&owner=Ghost%20Emp").json()
    assert len(kept) == 1 and kept[0]["title"] == "Iqama"


def test_auth_required_documents():
    from fastapi.testclient import TestClient
    from app.main import app
    anon = TestClient(app)
    assert anon.get("/api/documents").status_code == 401
