"""Real concurrency tests: fire parallel requests at a live uvicorn server and
assert the read-modify-write invariants hold (quota, escalation). These would
fail against the pre-lock code, where two requests read the same stale count."""
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
import uvicorn

from app.main import app
from conftest import ADMIN


class _ThreadServer(uvicorn.Server):
    # Signal handlers can only be installed on the main thread; skip them so the
    # server can run inside a test thread.
    def install_signal_handlers(self) -> None:
        pass


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def base_url():
    port = _free_port()
    server = _ThreadServer(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(200):  # wait up to ~10s for startup (runs init_db + bootstrap)
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    else:
        server.should_exit = True
        raise RuntimeError("live server did not become ready")
    yield url
    server.should_exit = True
    thread.join(timeout=5)


def _auth(url):
    r = httpx.post(f"{url}/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=10)
    assert r.status_code == 200, r.text
    cookies = {"hr_session": r.cookies.get("hr_session"), "hr_csrf": r.cookies.get("hr_csrf")}
    return cookies, {"X-CSRF-Token": r.cookies.get("hr_csrf")}


def _parallel(fn, n, workers=8):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(lambda _: fn(), range(n)))


def test_permission_quota_holds_under_concurrency(base_url):
    cookies, headers = _auth(base_url)
    httpx.post(f"{base_url}/api/employees",
               json={"name": "Conc Emp", "email": "conc@e.com", "department": "Ops", "manager_email": ""},
               cookies=cookies, headers=headers, timeout=10)

    def grant():
        return httpx.post(f"{base_url}/api/permissions",
                          json={"employee_name": "Conc Emp", "permission_date": "2026-05-10"},
                          cookies=cookies, headers=headers, timeout=10).status_code

    codes = _parallel(grant, 8)
    assert codes.count(201) == 2, codes          # exactly the monthly quota, never more
    assert codes.count(409) == 6, codes

    body = httpx.get(f"{base_url}/api/permissions?month=2026-05", cookies=cookies, headers=headers, timeout=10).json()
    row = next(e for e in body["employees"] if e["employee_name"] == "Conc Emp")
    assert row["used"] == 2


def test_violation_escalation_serialized_under_concurrency(base_url):
    cookies, headers = _auth(base_url)

    def log():
        r = httpx.post(f"{base_url}/api/violations",
                       json={"employee_name": "Esc Emp", "category": "Attendance & Adherence", "incident": "Late Arrival"},
                       cookies=cookies, headers=headers, timeout=10)
        return r.json().get("penalty_color")

    colors = _parallel(log, 3, workers=3)
    # "Late Arrival" escalates Yellow → Yellow → Orange. Three concurrent logs
    # must produce that exact multiset — not three identical Yellows from a race.
    assert sorted(colors) == ["Orange", "Yellow", "Yellow"], colors
