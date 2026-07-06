"""Shared pytest fixtures. Environment must be configured before the app is
imported, because the app reads config (DB path, attendance flags) at import."""
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("HR_DB_FILE", os.path.join(tempfile.mkdtemp(), "test_hr.db"))
os.environ.setdefault("HR_BOOTSTRAP_ADMIN_EMAIL", "admin@test.com")
os.environ.setdefault("HR_BOOTSTRAP_ADMIN_PASSWORD", "password123")
# Biometric off so the clock flows are testable without a real authenticator;
# individual tests flip it on via monkeypatch. Geofence on to exercise it.
os.environ.setdefault("ATTENDANCE_REQUIRE_BIOMETRIC", "false")
os.environ.setdefault("ATTENDANCE_REQUIRE_GEOFENCE", "true")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ADMIN = ("admin@test.com", "password123")
_seq = {"n": 0}


def csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": c.cookies.get("hr_csrf", "")}


def login(email: str, password: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="session")
def client():
    # The context manager runs the lifespan (init_db + bootstrap_admin) once.
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin(client):
    return login(*ADMIN)


@pytest.fixture(autouse=True)
def _clean_offices(admin):
    """Every test starts with no geofence offices; tests opt in explicitly."""
    for o in admin.get("/api/attendance/offices").json():
        admin.delete(f"/api/attendance/offices/{o['id']}", headers=csrf(admin))
    yield


@pytest.fixture
def new_employee(admin):
    """Create a fresh employee (unique email) and return a logged-in client.
    Fresh each call so per-user-per-day clock-in state never collides."""
    def _make(name=None, role="employee", department="Ops"):
        _seq["n"] += 1
        email = f"emp{_seq['n']}@test.com"
        r = admin.post(
            "/api/auth/users",
            json={
                "email": email,
                "name": name or f"Emp {_seq['n']}",
                "role": role,
                "department": department,
                "password": "password123",
            },
            headers=csrf(admin),
        )
        assert r.status_code in (200, 201), r.text
        return login(email, "password123"), email

    return _make
