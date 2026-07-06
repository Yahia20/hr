"""End-to-end tests for the attendance feature (clock in/out, geofence,
office CRUD, WebAuthn ceremony error paths, listing scope, pagination, export).

The real WebAuthn success path needs a physical authenticator, so biometric
verification is exercised up to the ceremony/registration boundary only."""
import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import app
from conftest import csrf

RIYADH = (24.7136, 46.6753)
CAIRO = (30.0444, 31.2357)


def _admin_row(admin, email):
    body = admin.get(f"/api/attendance?employee={email}").json()
    return body["rows"][0] if body["rows"] else None


def test_me_initial(new_employee):
    emp, _ = new_employee()
    me = emp.get("/api/attendance/me").json()
    assert me["today"] is None
    assert me["has_credential"] is False
    assert me["require_biometric"] is False
    assert me["require_geofence"] is False  # no offices configured


def test_clock_in_out_flow(new_employee):
    emp, email = new_employee()
    # No offices -> clocking allowed from anywhere.
    r = emp.post("/api/attendance/clock-in", json={"lat": 30.0, "lng": 31.0, "accuracy": 10}, headers=csrf(emp))
    assert r.status_code == 201, r.text
    assert r.json()["clock_in_at"] and r.json()["clock_out_at"] is None

    # A second clock-in the same day is rejected.
    r = emp.post("/api/attendance/clock-in", json={"lat": 30.0, "lng": 31.0}, headers=csrf(emp))
    assert r.status_code == 409 and r.json()["detail"] == "already_clocked_in"

    r = emp.post("/api/attendance/clock-out", json={"lat": 30.0, "lng": 31.0, "accuracy": 5}, headers=csrf(emp))
    assert r.status_code == 200 and r.json()["clock_out_at"]

    body = emp.get("/api/attendance").json()
    assert body["total"] == 1
    row = body["rows"][0]
    assert row["email"] == email and row["worked_hours"] is not None


def test_clock_out_without_clock_in(new_employee):
    emp, _ = new_employee()
    r = emp.post("/api/attendance/clock-out", json={"lat": 1, "lng": 1}, headers=csrf(emp))
    assert r.status_code == 409 and r.json()["detail"] == "not_clocked_in"


def test_geofence_enforced(admin, new_employee):
    r = admin.post(
        "/api/attendance/offices",
        json={"name": "HQ", "lat": RIYADH[0], "lng": RIYADH[1], "radius_m": 150},
        headers=csrf(admin),
    )
    assert r.status_code == 201, r.text
    emp, _ = new_employee()

    # Outside the fence -> 403 with the distance to the nearest office.
    r = emp.post("/api/attendance/clock-in", json={"lat": 25.0, "lng": 47.0, "accuracy": 10}, headers=csrf(emp))
    assert r.status_code == 403 and r.json()["detail"].startswith("outside_geofence:")

    # Missing location while geofencing is enforced -> 400.
    r = emp.post("/api/attendance/clock-in", json={}, headers=csrf(emp))
    assert r.status_code == 400 and r.json()["detail"] == "location_required"

    # Inside the fence -> ok, office name recorded.
    r = emp.post("/api/attendance/clock-in", json={"lat": RIYADH[0] + 0.0005, "lng": RIYADH[1], "accuracy": 20}, headers=csrf(emp))
    assert r.status_code == 201, r.text
    assert r.json()["clock_in_office"] == "HQ"

    me = emp.get("/api/attendance/me").json()
    assert me["require_geofence"] is True


def test_biometric_required_blocks_unregistered(monkeypatch, new_employee):
    monkeypatch.setattr("app.routers.attendance.REQUIRE_BIOMETRIC", True)
    emp, _ = new_employee()
    r = emp.post("/api/attendance/clock-in", json={"lat": 1, "lng": 1}, headers=csrf(emp))
    assert r.status_code == 403 and r.json()["detail"] == "fingerprint_not_registered"


def test_list_scope_and_pagination(admin):
    marker = "PGMARK"
    emps = []
    for i in range(3):
        _seq_email = f"pg{i}@test.com"
        admin.post(
            "/api/auth/users",
            json={"email": _seq_email, "name": f"{marker} {i}", "role": "employee", "department": "Pag", "password": "password123"},
            headers=csrf(admin),
        )
        from conftest import login
        c = login(_seq_email, "password123")
        c.post("/api/attendance/clock-in", json={"lat": 10, "lng": 10}, headers=csrf(c))
        emps.append(c)

    # Filter by the unique marker so the total is deterministic despite other tests.
    body = admin.get(f"/api/attendance?employee={marker}&limit=2&offset=0").json()
    assert body["total"] == 3
    assert len(body["rows"]) == 2
    body2 = admin.get(f"/api/attendance?employee={marker}&limit=2&offset=2").json()
    assert len(body2["rows"]) == 1

    # An employee only sees their own record.
    self_rows = emps[0].get("/api/attendance").json()
    assert self_rows["total"] == 1

    # limit is capped, and a bad date is rejected.
    assert admin.get("/api/attendance?limit=99999").status_code == 422
    assert admin.get("/api/attendance?date_from=nonsense").status_code == 400


def test_office_endpoints_role_guarded(new_employee):
    emp, _ = new_employee()
    assert emp.get("/api/attendance/offices").status_code == 403
    assert emp.post("/api/attendance/offices", json={"name": "x", "lat": 0, "lng": 0}, headers=csrf(emp)).status_code == 403
    assert emp.get("/api/attendance/export").status_code == 403


def test_webauthn_error_paths(new_employee):
    emp, _ = new_employee()
    opts = emp.post("/api/attendance/webauthn/register/begin", headers=csrf(emp)).json()
    assert opts["challenge"] and opts["rp"]["id"]
    assert opts["authenticatorSelection"]["userVerification"] == "required"

    r = emp.post("/api/attendance/webauthn/register/complete", json={"credential": {"id": "x"}}, headers=csrf(emp))
    assert r.status_code == 400 and r.json()["detail"] == "registration_failed"

    r = emp.post("/api/attendance/webauthn/clock/begin", headers=csrf(emp))
    assert r.status_code == 403 and r.json()["detail"] == "fingerprint_not_registered"

    assert emp.get("/api/attendance/webauthn/credentials").json() == []


def test_export_content_type(admin, new_employee):
    emp, _ = new_employee()
    emp.post("/api/attendance/clock-in", json={"lat": 1, "lng": 1}, headers=csrf(emp))
    r = admin.get("/api/attendance/export")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]


def test_auth_required():
    anon = TestClient(app)
    assert anon.get("/api/attendance").status_code == 401
    assert anon.post("/api/attendance/clock-in", json={}).status_code == 401


def test_risk_zero_accuracy_flagged(admin, new_employee):
    emp, email = new_employee()
    r = emp.post("/api/attendance/clock-in", json={"lat": 10, "lng": 10, "accuracy": 0}, headers=csrf(emp))
    assert r.status_code == 201
    row = _admin_row(admin, email)
    assert row["risk"]["level"] == "high"
    assert "zero_accuracy" in row["risk"]["reasons"]


def test_risk_impossible_travel_flagged(admin, new_employee):
    emp, email = new_employee()
    # Clock in in Riyadh and out in Cairo seconds later — physically impossible.
    emp.post("/api/attendance/clock-in", json={"lat": RIYADH[0], "lng": RIYADH[1], "accuracy": 20}, headers=csrf(emp))
    emp.post("/api/attendance/clock-out", json={"lat": CAIRO[0], "lng": CAIRO[1], "accuracy": 20}, headers=csrf(emp))
    row = _admin_row(admin, email)
    assert row["risk"]["level"] == "high"
    assert "impossible_travel" in row["risk"]["reasons"]


def test_risk_clean_when_plausible(admin, new_employee):
    emp, email = new_employee()
    emp.post("/api/attendance/clock-in", json={"lat": 10, "lng": 10, "accuracy": 22}, headers=csrf(emp))
    row = _admin_row(admin, email)
    assert row["risk"]["level"] == "none" and row["risk"]["reasons"] == []


def _hq(admin, radius=150):
    admin.post(
        "/api/attendance/offices",
        json={"name": "HQ", "lat": RIYADH[0], "lng": RIYADH[1], "radius_m": radius},
        headers=csrf(admin),
    )


def test_slack_cannot_widen_fence_far(admin, new_employee):
    # ~240m from a 150m office claiming accuracy=100: slack is capped at 50, so
    # the effective fence is 200m and the punch must be rejected, not accepted.
    _hq(admin)
    emp, _ = new_employee()
    r = emp.post(
        "/api/attendance/clock-in",
        json={"lat": RIYADH[0] + 0.00216, "lng": RIYADH[1], "accuracy": 100},
        headers=csrf(emp),
    )
    assert r.status_code == 403 and r.json()["detail"].startswith("outside_geofence:")


def test_edge_of_fence_is_flagged(admin, new_employee):
    # Just outside the 150m radius but inside radius+slack -> accepted BUT flagged.
    _hq(admin)
    emp, email = new_employee()
    r = emp.post(
        "/api/attendance/clock-in",
        json={"lat": RIYADH[0] + 0.00162, "lng": RIYADH[1], "accuracy": 40},  # ~180m out
        headers=csrf(emp),
    )
    assert r.status_code == 201, r.text
    row = _admin_row(admin, email)
    assert "edge_of_fence" in row["risk"]["reasons"]
    assert row["risk"]["level"] in ("low", "high")


def test_solidly_inside_is_not_flagged(admin, new_employee):
    _hq(admin)
    emp, email = new_employee()
    r = emp.post(
        "/api/attendance/clock-in",
        json={"lat": RIYADH[0] + 0.0003, "lng": RIYADH[1], "accuracy": 20},  # ~33m, well inside
        headers=csrf(emp),
    )
    assert r.status_code == 201
    row = _admin_row(admin, email)
    assert "edge_of_fence" not in row["risk"]["reasons"]


def test_low_precision_flagged(admin, new_employee):
    emp, email = new_employee()  # no offices -> geofence not enforced
    emp.post("/api/attendance/clock-in", json={"lat": 10, "lng": 10, "accuracy": 80}, headers=csrf(emp))
    row = _admin_row(admin, email)
    assert "low_precision" in row["risk"]["reasons"]


def test_risk_hidden_from_employee_and_ip_not_leaked(new_employee):
    emp, _ = new_employee()
    emp.post("/api/attendance/clock-in", json={"lat": 10, "lng": 10, "accuracy": 0}, headers=csrf(emp))
    row = emp.get("/api/attendance").json()["rows"][0]
    assert "risk" not in row  # spoof flags not revealed to the employee
    assert "clock_in_ip" not in row  # IP is audit-only, never in the list UI


def test_export_has_risk_and_ip_columns(admin, new_employee):
    emp, _ = new_employee()
    emp.post("/api/attendance/clock-in", json={"lat": 10, "lng": 10, "accuracy": 5}, headers=csrf(emp))
    r = admin.get("/api/attendance/export")
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).active
    headers = [c.value for c in ws[1]]
    for col in ("Risk", "Risk Reasons", "IP (In)", "IP (Out)"):
        assert col in headers
