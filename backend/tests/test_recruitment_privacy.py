"""ATS Phase 4: notice attestation, retention clock and sweep, early CV removal,
erasure, export access and opt-in candidate emails (synthetic data only)."""
from conftest import csrf
from app import recruitment_privacy as privacy
from app.db import db
from test_recruitment import _create_job, _cv, _upload


def _applicant(client, job_id, **changes):
    response = _upload(client, job_id, **changes)
    assert response.status_code == 201, response.text
    return response.json()


def _row(applicant_id, cols="*"):
    with db() as conn:
        return conn.execute(f"SELECT {cols} FROM applicants WHERE id=?", (applicant_id,)).fetchone()


def _events(applicant_id):
    with db() as conn:
        return [r["action"] for r in conn.execute(
            "SELECT action FROM ats_privacy_events WHERE applicant_id=? ORDER BY id", (applicant_id,))]


def test_upload_and_preview_require_notice_attestation(admin):
    job, _ = _create_job(admin)
    assert _upload(admin, job["id"], notice_attested=False).json()["detail"] == "notice_required"
    assert _upload(admin, job["id"], notice_channel="carrier_pigeon").status_code == 400
    created = _applicant(admin, job["id"], notice_channel="whatsapp")
    row = _row(created["id"], "notice_attested_at, notice_attested_by, notice_channel, processing_notice_version")
    assert row["notice_attested_at"].endswith("Z") and row["notice_attested_by"]
    assert row["notice_channel"] == "whatsapp" and row["processing_notice_version"] == privacy.NOTICE_VERSION
    preview = admin.post("/api/recruitment/parse-preview", headers=csrf(admin), json={
        "cv_attachment": _cv("p@example.test"), "cv_name": "p.txt", "cv_mime": "text/plain"})
    assert preview.status_code == 400


def test_api_never_returns_the_cv_full_text(admin):
    job, _ = _create_job(admin)
    created = _applicant(admin, job["id"])
    detail = admin.get(f"/api/recruitment/applicants/{created['id']}").json()
    for key in ("readable_text", "normalized_text", "line_map", "sections"):
        assert key not in detail["parsed"] and key not in created["parsed"]
    preview = admin.post("/api/recruitment/parse-preview", headers=csrf(admin), json={
        "cv_attachment": _cv("q@example.test"), "cv_name": "q.txt", "cv_mime": "text/plain", "notice_attested": True})
    assert "readable_text" not in preview.json()["parsed"]
    # Nothing in the whole response may reproduce the CV text (a sentence only the CV contains).
    assert "fictional operations team" not in preview.text
    assert "fictional operations team" not in admin.get(f"/api/recruitment/applicants/{created['id']}").text


def test_retention_clock_starts_once_and_is_not_extended(admin):
    job, payload = _create_job(admin)
    rejected = _applicant(admin, job["id"])
    active = _applicant(admin, job["id"])
    assert _row(rejected["id"], "erase_after")["erase_after"] is None
    admin.post(f"/api/recruitment/applicants/{rejected['id']}/stage", json={"stage": "rejected"}, headers=csrf(admin))
    first = _row(rejected["id"], "retention_started_at, erase_after, retention_days_snapshot")
    with db() as conn:
        days = privacy.retention_days(conn)
    assert first["erase_after"] and first["retention_days_snapshot"] == days
    assert _row(active["id"], "erase_after")["erase_after"] is None

    # A criteria edit re-scores, and a close/reopen cycle happens: the first clock never moves.
    changed = {**payload, "min_years": 1, "status": "closed"}
    assert admin.put(f"/api/recruitment/jobs/{job['id']}", json=changed, headers=csrf(admin)).status_code == 200
    assert _row(rejected["id"], "erase_after")["erase_after"] == first["erase_after"]
    assert _row(active["id"], "erase_after")["erase_after"]  # closing started the rest
    admin.put(f"/api/recruitment/jobs/{job['id']}", json={**changed, "status": "open"}, headers=csrf(admin))
    admin.post(f"/api/recruitment/jobs/{job['id']}/close", headers=csrf(admin))
    assert _row(rejected["id"], "erase_after")["erase_after"] == first["erase_after"]


def test_sweep_dry_run_reads_only_then_deletes_due_applications(admin):
    job, _ = _create_job(admin)
    due = _applicant(admin, job["id"])
    later = _applicant(admin, job["id"])
    admin.post(f"/api/recruitment/applicants/{due['id']}/stage", json={"stage": "screened", "note": "x"}, headers=csrf(admin))
    admin.post(f"/api/recruitment/applicants/{due['id']}/feedback", json={"result": "cleared"}, headers=csrf(admin))
    with db() as conn:
        conn.execute("UPDATE applicants SET erase_after='2000-01-01T00:00:00Z' WHERE id=?", (due["id"],))
        conn.execute("UPDATE applicants SET erase_after='2999-01-01T00:00:00Z' WHERE id=?", (later["id"],))
        before_last = privacy.last_run(conn)

    preview = admin.post("/api/recruitment/retention/run?dry_run=true", headers=csrf(admin)).json()
    assert due["id"] in {i["id"] for i in preview["items"]} and later["id"] not in {i["id"] for i in preview["items"]}
    assert _row(due["id"], "id") is not None
    with db() as conn:
        assert privacy.last_run(conn) == before_last

    result = admin.post("/api/recruitment/retention/run?dry_run=false", headers=csrf(admin)).json()
    assert result["deleted"] >= 1 and result["failed"] == 0
    assert _row(due["id"], "id") is None and _row(later["id"], "id") is not None
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM applicant_stage_history WHERE applicant_id=?", (due["id"],)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM interview_feedback WHERE applicant_id=?", (due["id"],)).fetchone()[0] == 0
        assert privacy.last_run(conn)["last_success"]["deleted"] >= 1
    assert _events(due["id"]) == ["expired"]


def test_cv_removal_clears_contents_and_freezes_the_dossier(admin, new_employee):
    job, payload = _create_job(admin)
    a = _applicant(admin, job["id"], notes="call back", nationality="Egyptian")
    admin.post(f"/api/recruitment/applicants/{a['id']}/stage", json={"stage": "screened", "note": "liked"}, headers=csrf(admin))
    admin.post(f"/api/recruitment/applicants/{a['id']}/feedback", json={"result": "cleared", "comment": "ok"}, headers=csrf(admin))
    officer, _ = new_employee(role="hr_officer", department="Ops")
    assert officer.post(f"/api/recruitment/applicants/{a['id']}/purge-cv", json={"reason": "manual"}, headers=csrf(officer)).status_code == 403

    assert admin.post(f"/api/recruitment/applicants/{a['id']}/purge-cv", json={"reason": "withdrawn"}, headers=csrf(admin)).status_code == 200
    row = _row(a["id"])
    assert row["cv_attachment"] == "" and row["cv_text"] == "" and row["parsed"] == "{}"
    assert row["notes"] == "" and row["nationality"] == "" and row["cv_purge_reason"] == "withdrawn"
    assert row["email"] == a["email"] and row["score"] == a["score"]
    assert '"line"' not in row["score_breakdown"]
    with db() as conn:
        assert conn.execute("SELECT note FROM applicant_stage_history WHERE applicant_id=?", (a["id"],)).fetchone()["note"] == ""
        assert conn.execute("SELECT COUNT(*) FROM interview_feedback WHERE applicant_id=?", (a["id"],)).fetchone()[0] == 0
    assert admin.get(f"/api/recruitment/applicants/{a['id']}/cv").status_code == 410
    assert admin.patch(f"/api/recruitment/applicants/{a['id']}", json={"notes": "x"}, headers=csrf(admin)).json()["detail"] == "cv_purged"
    assert admin.post(f"/api/recruitment/applicants/{a['id']}/feedback", json={"result": "cleared"}, headers=csrf(admin)).status_code == 409
    assert admin.post(f"/api/recruitment/applicants/{a['id']}/stage", json={"stage": "shortlisted"}, headers=csrf(admin)).status_code == 409
    assert admin.post(f"/api/recruitment/applicants/{a['id']}/purge-cv", json={"reason": "manual"}, headers=csrf(admin)).status_code == 409

    # A criteria change re-scores the others but leaves the removed one, now marked stale.
    edited = admin.put(f"/api/recruitment/jobs/{job['id']}", json={**payload, "min_years": 9}, headers=csrf(admin)).json()
    assert edited["rescored_applicants"] == 0
    listed = admin.get(f"/api/recruitment/jobs/{job['id']}/applicants").json()
    assert listed[0]["score_stale"] is True and listed[0]["cv_purged_at"]
    assert admin.post(f"/api/recruitment/applicants/{a['id']}/stage", json={"stage": "rejected"}, headers=csrf(admin)).status_code == 200
    assert _events(a["id"]) == ["cv_removed"]


def test_erasure_request_deletes_every_application_for_the_email(admin):
    job1, _ = _create_job(admin)
    job2, _ = _create_job(admin)
    email = "erase.me@example.test"
    a1 = _applicant(admin, job1["id"], email=email)
    a2 = _applicant(admin, job2["id"], email=email)
    other = _applicant(admin, job2["id"])
    response = admin.delete(
        f"/api/recruitment/applicants/{a1['id']}?reason=erasure_request&all_for_email=true", headers=csrf(admin))
    assert response.status_code == 204
    assert _row(a1["id"], "id") is None and _row(a2["id"], "id") is None and _row(other["id"], "id") is not None
    assert _events(a2["id"]) == ["deleted"]


def test_export_is_manager_only(admin, new_employee):
    job, _ = _create_job(admin)
    officer, _ = new_employee(role="hr_officer", department="Ops")
    assert officer.get(f"/api/recruitment/jobs/{job['id']}/export").status_code == 403
    assert admin.get(f"/api/recruitment/jobs/{job['id']}/export").status_code == 200


def test_retention_settings_bounds_and_roles(admin, new_employee):
    officer, _ = new_employee(role="hr_officer", department="Ops")
    assert officer.get("/api/recruitment/retention").status_code == 403
    assert admin.put("/api/recruitment/retention", json={"days": 0}, headers=csrf(admin)).status_code == 422
    assert admin.put("/api/recruitment/retention", json={"days": 366}, headers=csrf(admin)).status_code == 422
    saved = admin.put("/api/recruitment/retention", json={"days": 90}, headers=csrf(admin)).json()
    assert saved["days"] == 90
    admin.put("/api/recruitment/retention", json={"days": privacy.DEFAULT_DAYS}, headers=csrf(admin))


def test_candidate_email_is_opt_in_previewed_and_sent_once(admin, monkeypatch):
    sent = []
    monkeypatch.setattr(privacy, "email_configured", lambda: True)
    monkeypatch.setattr(privacy, "send_email", lambda to, subject, body: sent.append((to, subject, body)) or True)
    job, _ = _create_job(admin, title="Synthetic Visa Role")
    a = _applicant(admin, job["id"], full_name="Rana Synthetic", email="rana@example.com")

    off = admin.post(f"/api/recruitment/applicants/{a['id']}/stage", json={"stage": "rejected", "notify": True}, headers=csrf(admin))
    assert off.json()["detail"] == "stage_emails_disabled"

    templates = admin.get("/api/recruitment/email-settings").json()["templates"]
    bad = {**templates, "offer": {**templates["offer"], "en": {"subject": "Hi {salary}", "body": "x"}}}
    assert admin.put("/api/recruitment/email-settings", json={"enabled": True, "templates": bad}, headers=csrf(admin)).status_code == 400
    assert admin.put("/api/recruitment/email-settings", json={"enabled": True, "templates": templates}, headers=csrf(admin)).status_code == 200
    try:
        preview = admin.get(f"/api/recruitment/applicants/{a['id']}/stage-email-preview?stage=rejected&lang=ar").json()
        assert preview["to"] == "rana@example.com" and "Rana Synthetic" in preview["body"] and "Synthetic Visa Role" in preview["subject"]
        assert admin.post(f"/api/recruitment/applicants/{a['id']}/stage", json={"stage": "screened", "notify": True}, headers=csrf(admin)).json()["detail"] == "no_email_for_stage"

        stale = admin.post(f"/api/recruitment/applicants/{a['id']}/stage",
                           json={"stage": "rejected", "notify": True, "notify_language": "ar", "preview_hash": "x"}, headers=csrf(admin))
        assert stale.json()["detail"] == "preview_outdated"
        moved = admin.post(f"/api/recruitment/applicants/{a['id']}/stage",
                           json={"stage": "rejected", "notify": True, "notify_language": "ar",
                                 "preview_hash": preview["hash"]}, headers=csrf(admin))
        assert moved.status_code == 200
        assert len(sent) == 1 and sent[0][0] == "rana@example.com" and sent[0][1] == preview["subject"]
        with db() as conn:
            status = conn.execute("SELECT notify_status, notified_at FROM applicant_stage_history WHERE id=?",
                                  (moved.json()["id"],)).fetchone()
        assert status["notify_status"] == "accepted" and status["notified_at"]
        privacy.send_stage_email(moved.json()["id"])  # a second run never resends
        assert len(sent) == 1

        b = _applicant(admin, job["id"], email="no-mail")
        assert admin.post(f"/api/recruitment/applicants/{b['id']}/stage",
                          json={"stage": "rejected", "notify": True}, headers=csrf(admin)).json()["detail"] == "invalid_recipient"
    finally:
        admin.put("/api/recruitment/email-settings", json={"enabled": False, "templates": templates}, headers=csrf(admin))


def _history_row(applicant_id, status):
    with db() as conn:
        return conn.execute(
            "INSERT INTO applicant_stage_history (applicant_id, old_stage, new_stage, changed_at, notify_status, "
            "notify_subject, notify_body) VALUES (?, 'new', 'new', '2026-01-01 00:00:00', ?, 's', 'b') RETURNING id",
            (applicant_id, status),
        ).fetchone()["id"]


def _status(history_id):
    with db() as conn:
        return conn.execute("SELECT notify_status FROM applicant_stage_history WHERE id=?", (history_id,)).fetchone()[0]


def test_interrupted_emails_are_never_resent(admin):
    job, _ = _create_job(admin)
    a = _applicant(admin, job["id"])
    pending, sending = _history_row(a["id"], "pending"), _history_row(a["id"], "sending")
    privacy.recover_interrupted_emails()
    assert (_status(pending), _status(sending)) == ("cancelled", "unknown")


def test_queued_email_is_cancelled_by_cv_removal_and_by_a_newer_move(admin, monkeypatch):
    sent = []
    monkeypatch.setattr(privacy, "send_email", lambda *args: sent.append(args) or True)
    monkeypatch.setattr(privacy, "email_configured", lambda: True)
    job, _ = _create_job(admin)
    a = _applicant(admin, job["id"], email="queued@example.com")
    b = _applicant(admin, job["id"], email="queued2@example.com")
    templates = admin.get("/api/recruitment/email-settings").json()["templates"]
    admin.put("/api/recruitment/email-settings", json={"enabled": True, "templates": templates}, headers=csrf(admin))
    try:
        queued = _history_row(a["id"], "pending")
        admin.post(f"/api/recruitment/applicants/{a['id']}/purge-cv", json={"reason": "withdrawn"}, headers=csrf(admin))
        privacy.send_stage_email(queued)
        assert _status(queued) == "cancelled"

        older = _history_row(b["id"], "pending")
        admin.post(f"/api/recruitment/applicants/{b['id']}/stage", json={"stage": "screened"}, headers=csrf(admin))
        privacy.send_stage_email(older)
        assert _status(older) == "cancelled" and sent == []
    finally:
        admin.put("/api/recruitment/email-settings", json={"enabled": False, "templates": templates}, headers=csrf(admin))


def test_cv_removal_starts_the_clock_and_keeps_the_record_frozen(admin):
    job, _ = _create_job(admin)
    a = _applicant(admin, job["id"])
    ts = "2026-01-01T00:00:00Z"
    with db() as conn:
        run = conn.execute(
            "INSERT INTO ats_semantic_runs (applicant_id, cv_revision, rubric_version, created_at, updated_at) "
            "VALUES (?, 1, 1, ?, ?) RETURNING id", (a["id"], ts, ts)).fetchone()["id"]
        conn.execute("INSERT INTO ats_semantic_results (run_id, criterion_key, created_at, updated_at) "
                     "VALUES (?, 'k', ?, ?)", (run, ts, ts))
    admin.post(f"/api/recruitment/applicants/{a['id']}/purge-cv", json={"reason": "withdrawn"}, headers=csrf(admin))
    assert _row(a["id"], "erase_after")["erase_after"]  # identity left behind gets a deletion date
    moved = admin.post(f"/api/recruitment/applicants/{a['id']}/stage",
                       json={"stage": "rejected", "note": "new private note"}, headers=csrf(admin))
    assert moved.status_code == 200 and moved.json()["note"] == ""
    assert admin.post(f"/api/recruitment/applicants/{a['id']}/feedback", json={"result": "cleared"},
                      headers=csrf(admin)).status_code == 409
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ats_semantic_runs WHERE applicant_id=?", (a["id"],)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM ats_semantic_results WHERE run_id=?", (run,)).fetchone()[0] == 0


def test_clock_never_exceeds_the_period_promised_in_the_notice(admin):
    try:
        admin.put("/api/recruitment/retention", json={"days": 30}, headers=csrf(admin))
        job, _ = _create_job(admin)
        a = _applicant(admin, job["id"])  # notice given while the policy said 30 days
        admin.put("/api/recruitment/retention", json={"days": 365}, headers=csrf(admin))
        admin.post(f"/api/recruitment/applicants/{a['id']}/stage", json={"stage": "rejected"}, headers=csrf(admin))
        assert _row(a["id"], "retention_days_snapshot")["retention_days_snapshot"] == 30
    finally:
        admin.put("/api/recruitment/retention", json={"days": privacy.DEFAULT_DAYS}, headers=csrf(admin))


def test_upload_rechecks_the_job_inside_the_insert_transaction(admin, monkeypatch):
    """Simulate a close that lands while the CV is being parsed (after the first status read)."""
    from app.routers import recruitment as rec
    job, _ = _create_job(admin)
    real_score = rec.score

    def close_then_score(*args, **kwargs):
        with db() as conn:
            conn.execute("UPDATE job_openings SET status='closed' WHERE id=?", (job["id"],))
        return real_score(*args, **kwargs)

    monkeypatch.setattr(rec, "score", close_then_score)
    response = _upload(admin, job["id"])
    assert response.status_code == 409 and response.json()["detail"] == "job_closed"
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM applicants WHERE job_id=?", (job["id"],)).fetchone()[0] == 0


def test_rescore_never_publishes_against_a_newer_rubric(admin, monkeypatch):
    """A PATCH whose rubric changed between scoring and publishing is refused, not silently stale."""
    from app.routers import recruitment as rec
    job, _ = _create_job(admin)
    a = _applicant(admin, job["id"])
    real = rec._score_stored

    def bump_then_score(*args, **kwargs):
        with db() as conn:
            conn.execute("UPDATE job_openings SET rubric_version = rubric_version + 1 WHERE id=?", (job["id"],))
        return real(*args, **kwargs)

    monkeypatch.setattr(rec, "_score_stored", bump_then_score)
    response = admin.patch(f"/api/recruitment/applicants/{a['id']}", json={"notes": "x"}, headers=csrf(admin))
    assert response.status_code == 409 and response.json()["detail"] == "conflict"


def test_the_promise_is_the_notice_that_was_sent_not_the_setting_at_upload(admin):
    try:
        job, _ = _create_job(admin)
        admin.put("/api/recruitment/retention", json={"days": 365}, headers=csrf(admin))
        a = _applicant(admin, job["id"], notice_retention_days=30)  # HR had sent a 30-day notice
        admin.post(f"/api/recruitment/applicants/{a['id']}/stage", json={"stage": "rejected"}, headers=csrf(admin))
        assert _row(a["id"], "notice_retention_days, retention_days_snapshot")["retention_days_snapshot"] == 30
    finally:
        admin.put("/api/recruitment/retention", json={"days": privacy.DEFAULT_DAYS}, headers=csrf(admin))


def test_a_removed_cv_cannot_get_a_new_candidate_email(admin):
    job, _ = _create_job(admin)
    a = _applicant(admin, job["id"], email="gone@example.com")
    admin.post(f"/api/recruitment/applicants/{a['id']}/purge-cv", json={"reason": "manual"}, headers=csrf(admin))
    moved = admin.post(f"/api/recruitment/applicants/{a['id']}/stage",
                       json={"stage": "rejected", "notify": True, "preview_hash": "x"}, headers=csrf(admin))
    assert moved.status_code == 409 and moved.json()["detail"] == "cv_purged"
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM applicant_stage_history WHERE applicant_id=? AND notify_body<>''",
                            (a["id"],)).fetchone()[0] == 0
