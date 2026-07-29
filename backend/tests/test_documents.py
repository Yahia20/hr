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


def test_calendar_invalid_dates_rejected(admin):
    # Format-valid but nonexistent days must be refused, not just format-checked.
    assert _mk(admin, end_date="2026-02-31").status_code == 422
    assert _mk(admin, end_date="2026-99-99").status_code == 422
    assert _mk(admin, start_date="2026-13-01").status_code == 422


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


def test_patch_reassigns_owner(admin):
    """A paper filed under the wrong person can be moved to the right one."""
    did = _mk(admin, category="iqama", owner="Wrong Name", title="Iqama").json()["id"]
    r = admin.patch(f"/api/documents/{did}", json={"owner": "  Right Name  ", "title": "Iqama 2024"},
                    headers=csrf(admin))
    assert r.status_code == 200, r.text
    assert r.json()["owner"] == "Right Name" and r.json()["title"] == "Iqama 2024"

    rows = admin.get("/api/documents?category=iqama&owner=Right Name").json()
    assert [d["id"] for d in rows] == [did]
    assert admin.get("/api/documents?category=iqama&owner=Wrong Name").json() == []


def test_patch_owner_collision_rejected(admin):
    """Moving a slot record onto an owner who already has one is a 409, not a
    silent overwrite or a 500 from the unique index."""
    _mk(admin, category="contract", owner="Taken Slot", title="Contract")
    other = _mk(admin, category="contract", owner="Free Slot", title="Contract").json()["id"]
    r = admin.patch(f"/api/documents/{other}", json={"owner": "Taken Slot"}, headers=csrf(admin))
    assert r.status_code == 409 and r.json()["detail"] == "slot_exists"
    # The failed move left the record where it was, and the audit row written
    # before the UPDATE collided was rolled back with it — no orphan history.
    assert admin.get("/api/documents?category=contract&owner=Free Slot").json()[0]["id"] == other
    assert admin.get(f"/api/documents/{other}/history").json() == []


def test_patch_cannot_blank_a_slot_owner(admin):
    did = _mk(admin, category="rent", owner="blankable", title="Some Rent").json()["id"]
    assert admin.patch(f"/api/documents/{did}", json={"owner": "   "}, headers=csrf(admin)).status_code == 400
    # Open-list categories have no owner to begin with, so blanking is fine there.
    lic = _mk(admin, category="license", title="Some License").json()["id"]
    assert admin.patch(f"/api/documents/{lic}", json={"owner": ""}, headers=csrf(admin)).status_code == 200


def test_attachment_name_is_manager_only(admin, new_employee):
    """A file name leaks what the file holds, so it rides the same gate as the
    bytes: officers see `has_attachment` but never `attachment_name`."""
    did = _mk(admin, category="license", title="Named Doc", attachment=TINY_B64,
              attachment_name="ahmed-medical-report.pdf", attachment_mime="application/pdf").json()["id"]

    officer, _ = new_employee(role="hr_officer")
    assert officer.get(f"/api/documents/{did}/attachment").status_code == 403
    row = [d for d in officer.get("/api/documents?category=license").json() if d["id"] == did][0]
    assert row["has_attachment"] is True and row["attachment_name"] == ""
    # ...and not through the alert surfaces either.
    alerts = officer.get("/api/documents/expiring").json()["items"]
    assert all(i["attachment_name"] == "" for i in alerts)

    mine = [d for d in admin.get("/api/documents?category=license").json() if d["id"] == did][0]
    assert mine["attachment_name"] == "ahmed-medical-report.pdf"


def test_officer_cannot_change_an_existing_attachment(admin, new_employee):
    """Replacing/clearing a file destroys something the officer can't even open,
    so it rides the manager gate. Attaching a first file stays open to staff."""
    officer, _ = new_employee(role="hr_officer")

    # No attachment yet → an officer may add one.
    did = _mk(officer, category="vehicle", title="Officer Van").json()["id"]
    r = officer.patch(f"/api/documents/{did}",
                      json={"attachment": TINY_B64, "attachment_name": "a.png", "attachment_mime": "image/png"},
                      headers=csrf(officer))
    assert r.status_code == 200, r.text

    # Now one exists → replacing or clearing it is refused.
    assert officer.patch(f"/api/documents/{did}", json={"attachment": ""},
                         headers=csrf(officer)).status_code == 403
    assert officer.patch(f"/api/documents/{did}",
                         json={"attachment": "d29ybGQ=", "attachment_name": "b.pdf", "attachment_mime": "application/pdf"},
                         headers=csrf(officer)).status_code == 403
    # The file is untouched, and other fields are still editable by the officer.
    assert admin.get(f"/api/documents/{did}/attachment").json()["attachment"] == TINY_B64
    assert officer.patch(f"/api/documents/{did}", json={"note": "still fine"},
                         headers=csrf(officer)).status_code == 200
    # A manager can do both.
    assert admin.patch(f"/api/documents/{did}", json={"attachment": ""},
                       headers=csrf(admin)).status_code == 200


def test_patch_replaces_and_removes_attachment(admin):
    did = _mk(admin, category="vehicle", title="Van", attachment=TINY_B64,
              attachment_name="old.png", attachment_mime="image/png").json()["id"]
    rows = admin.get("/api/documents?category=vehicle").json()
    assert [d for d in rows if d["id"] == did][0]["attachment_name"] == "old.png"

    new_b64 = "d29ybGQ="  # base64("world")
    r = admin.patch(f"/api/documents/{did}",
                    json={"attachment": new_b64, "attachment_name": "new.pdf", "attachment_mime": "application/pdf"},
                    headers=csrf(admin))
    assert r.status_code == 200 and r.json()["attachment_name"] == "new.pdf"
    assert admin.get(f"/api/documents/{did}/attachment").json()["attachment"] == new_b64

    # An empty attachment clears the file and its metadata.
    r = admin.patch(f"/api/documents/{did}", json={"attachment": ""}, headers=csrf(admin))
    assert r.status_code == 200 and r.json()["has_attachment"] is False
    assert r.json()["attachment_name"] == ""
    assert admin.get(f"/api/documents/{did}/attachment").status_code == 404


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


def test_reassignment_is_audited(admin):
    """Moving a paper to another owner must leave a trace — otherwise a record
    can be shifted between employees with nothing to show who did it."""
    did = _mk(admin, category="iqama", owner="Audit From", title="Iqama", end_date=_in(30)).json()["id"]
    r = admin.patch(f"/api/documents/{did}", json={"owner": "Audit To"}, headers=csrf(admin))
    assert r.status_code == 200, r.text

    hist = admin.get(f"/api/documents/{did}/history").json()
    assert len(hist) == 1
    entry = hist[0]
    assert entry["old_owner"] == "Audit From" and entry["new_owner"] == "Audit To"
    assert entry["changed_by"]
    # A pure reassignment is not a renewal: the dates are untouched on both sides.
    assert entry["old_start"] == entry["new_start"] and entry["old_end"] == entry["new_end"]


def test_renewal_leaves_owner_columns_blank(admin):
    """A date-only edit must not read as a reassignment in the history."""
    did = _mk(admin, category="contract", owner="Owner Stable", title="Contract", end_date=_in(30)).json()["id"]
    admin.patch(f"/api/documents/{did}", json={"end_date": _in(300)}, headers=csrf(admin))
    entry = admin.get(f"/api/documents/{did}/history").json()[0]
    assert entry["old_owner"] == "" and entry["new_owner"] == ""


def test_reassign_and_renew_in_one_edit(admin):
    did = _mk(admin, category="iqama", owner="Both From", title="Iqama", end_date=_in(30)).json()["id"]
    admin.patch(f"/api/documents/{did}", json={"owner": "Both To", "end_date": _in(365)}, headers=csrf(admin))
    entry = admin.get(f"/api/documents/{did}/history").json()[0]
    assert entry["old_owner"] == "Both From" and entry["new_owner"] == "Both To"
    assert entry["old_end"] == _in(30) and entry["new_end"] == _in(365)


def test_added_columns_reach_a_preexisting_table(tmp_path):
    """`CREATE TABLE IF NOT EXISTS` skips a table that already exists, so the
    audit columns must be patched in explicitly or a live database never gets
    them. Rebuild the pre-upgrade table and check the migration lands."""
    import sqlite3

    from app.db import _add_missing_columns

    conn = sqlite3.connect(tmp_path / "legacy.db")
    try:
        conn.execute(
            """CREATE TABLE document_history (
                   id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL,
                   old_start TEXT NOT NULL DEFAULT '', old_end TEXT NOT NULL DEFAULT '',
                   new_start TEXT NOT NULL DEFAULT '', new_end TEXT NOT NULL DEFAULT '',
                   changed_by TEXT NOT NULL DEFAULT '', changed_at TEXT NOT NULL)"""
        )
        conn.execute(
            "INSERT INTO document_history (document_id, old_end, new_end, changed_at)"
            " VALUES (1, '2026-01-01', '2027-01-01', '2026-01-01 00:00:00')"
        )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(document_history)")}
        assert "old_owner" not in cols  # the pre-upgrade shape

        _add_missing_columns(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(document_history)")}
        assert {"old_owner", "new_owner"} <= cols
        # The existing row survives and back-fills to the empty default.
        row = conn.execute("SELECT new_end, old_owner, new_owner FROM document_history").fetchone()
        assert row == ("2027-01-01", "", "")

        _add_missing_columns(conn)  # idempotent: a second boot must not fail
    finally:
        conn.close()


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
