"""Real contention on the recruitment write paths: parallel requests against a
live server, checking the invariants the lock protocol promises (no lost rubric
versions, one application per email, no CV evidence republished after removal)."""
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx

from test_concurrency import _auth, base_url  # noqa: F401  (module-scoped live server fixture)
from test_recruitment import _cv, _job_payload, _seq


def _client(url):
    cookies, headers = _auth(url)
    return httpx.Client(base_url=url, cookies=cookies, headers=headers, timeout=60)


def _new_job(c, **changes):
    payload = {**_job_payload(), **changes}
    r = c.post("/api/recruitment/jobs", json=payload)
    assert r.status_code == 201, r.text
    return r.json(), payload


def _upload(c, job_id, email=None, skills="Amadeus, PNR, Excel, customer service"):
    email = email or f"race{next(_seq)}@example.test"
    return c.post(f"/api/recruitment/jobs/{job_id}/applicants", json={
        "source": "synthetic-test", "cv_attachment": _cv(email, skills=skills), "cv_name": "synthetic.txt",
        "cv_mime": "text/plain", "notice_attested": True, "notice_channel": "email",
    })


def _parallel(n, fn):
    gate = threading.Barrier(n)

    def run(i):
        gate.wait()
        return fn(i)

    with ThreadPoolExecutor(n) as pool:
        return list(pool.map(run, range(n)))


def test_parallel_criteria_edits_lose_no_rubric_version(base_url):
    c = _client(base_url)
    job, payload = _new_job(c)
    applicants = [_upload(c, job["id"]).json()["id"] for _ in range(4)]
    edits = 6

    def edit(i):
        with _client(base_url) as mine:
            return mine.put(f"/api/recruitment/jobs/{job['id']}", json={**payload, "min_years": 10 + i}).status_code

    assert _parallel(edits, edit) == [200] * edits
    final = c.get(f"/api/recruitment/jobs/{job['id']}").json()
    assert final["rubric_version"] == job["rubric_version"] + edits

    # A score that claims to be current must equal a fresh score under the final rubric.
    before = {a: c.get(f"/api/recruitment/applicants/{a}").json() for a in applicants}
    assert c.post(f"/api/recruitment/jobs/{job['id']}/rescore").json()["rescored_applicants"] == len(applicants)
    for a in applicants:
        after = c.get(f"/api/recruitment/applicants/{a}").json()
        assert after["score_stale"] is False
        if not before[a]["score_stale"]:
            assert before[a]["score"] == after["score"]
    c.close()


def test_same_email_uploaded_in_parallel_creates_one_application(base_url):
    c = _client(base_url)
    job, _ = _new_job(c)
    email = f"twin{next(_seq)}@example.test"

    def upload(_):
        with _client(base_url) as mine:
            return _upload(mine, job["id"], email).status_code

    codes = _parallel(4, upload)
    assert sorted(codes) == [201, 409, 409, 409]
    listed = c.get("/api/recruitment/applicants", params={"job_id": job["id"]}).json()
    assert len(listed) == 1
    c.close()


def test_cv_removal_racing_rescore_never_republishes_evidence(base_url):
    c = _client(base_url)
    job, _ = _new_job(c)
    applicants = [_upload(c, job["id"]).json()["id"] for _ in range(8)]

    def work(i):
        with _client(base_url) as mine:
            if i == 0:
                return [mine.post(f"/api/recruitment/jobs/{job['id']}/rescore").status_code for _ in range(3)]
            return [mine.post(f"/api/recruitment/applicants/{a}/purge-cv", json={"reason": "manual"}).status_code
                    for a in applicants[(i - 1) * 2:(i - 1) * 2 + 2]]

    results = _parallel(5, work)
    assert results[0] == [200, 200, 200]
    assert all(code == 200 for codes in results[1:] for code in codes)
    for a in applicants:
        row = c.get(f"/api/recruitment/applicants/{a}").json()
        assert row["cv_purged_at"]
        assert all(not item["evidence"] for item in row["score_breakdown"]), a
    c.close()
