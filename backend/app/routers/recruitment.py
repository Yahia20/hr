"""Recruitment API backed by the deterministic, local ATS engine."""
import base64
import io
import json
from dataclasses import replace
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from ..ats import extract_text, parse_cv, score
from ..ats.parse import EDUCATION_ORDINAL, Evidence, SkillMatch
from ..ats.role_templates import DEFAULT_WEIGHTS, ROLE_TEMPLATES
from ..ats.taxonomy import SKILLS_BY_ID
from ..auth import (
    ROLE_DEPT_HEAD,
    ROLE_HR_MANAGER,
    ROLE_HR_OFFICER,
    CurrentUser,
    require_role,
)
from ..db import IntegrityError, db, lock
from ..emailer import email_configured
from .. import recruitment_privacy as privacy
from ..schemas import (
    ApplicantIn,
    ApplicantPatchIn,
    EmailSettingsIn,
    FeedbackIn,
    JobIn,
    ParsePreviewIn,
    PurgeCvIn,
    RetentionIn,
    StageIn,
    TaxonomyIn,
)

router = APIRouter(prefix="/recruitment", tags=["recruitment"])

_hr_staff = require_role(ROLE_HR_MANAGER, ROLE_HR_OFFICER)
_hr_or_head = require_role(ROLE_HR_MANAGER, ROLE_HR_OFFICER, ROLE_DEPT_HEAD)
_manager = require_role(ROLE_HR_MANAGER)

_JOB_JSON = ("gates", "required_skills", "preferred_skills", "languages", "weights", "semantic_criteria")
_APPLICANT_JSON = ("parsed", "corrections", "score_breakdown", "gate_failures")
_STAGE_NEXT = {
    "new": {"screened", "rejected"},
    "screened": {"shortlisted", "rejected"},
    "shortlisted": {"interview", "rejected"},
    "interview": {"offer", "rejected"},
    "offer": {"hired", "rejected"},
    "hired": {"rejected"},
    "rejected": {"screened"},
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _xlsx_safe(value):
    """Neutralise Excel formula injection: CV-derived text is attacker-controlled."""
    if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _job_dict(row, *, include_description: bool = True) -> dict:
    result = dict(row)
    for field in _JOB_JSON:
        result[field] = _load_json(result.get(field), [] if field in {"required_skills", "preferred_skills", "languages", "semantic_criteria"} else {})
    if not include_description:
        result.pop("description", None)
    return result


# Parser output that reproduces the whole CV; never returned by the API
# (manager CV download is the only route to the document itself).
_PARSED_PRIVATE = ("readable_text", "normalized_text", "line_map", "sections")


def _applicant_public(row, *, include_detail: bool = True, job_rubric_version: Optional[int] = None) -> dict:
    result = dict(row)
    result.pop("cv_attachment", None)
    result.pop("cv_text", None)
    for field in _APPLICANT_JSON:
        result[field] = _load_json(result.get(field), [] if field in {"score_breakdown", "gate_failures"} else {})
    for key in _PARSED_PRIVATE:
        result["parsed"].pop(key, None)
    if not include_detail:
        result.pop("parsed", None)
        result.pop("corrections", None)
    if job_rubric_version is not None and "scored_rubric_version" in result:
        result["score_stale"] = result["scored_rubric_version"] < job_rubric_version
    result["needs_manual_review"] = bool(result.get("needs_manual_review"))
    result["has_cv"] = bool(row["cv_attachment"]) if "cv_attachment" in row.keys() else True
    return result


def _ensure_department(user: CurrentUser, department: str) -> None:
    if user.role == ROLE_DEPT_HEAD and user.department != department:
        raise HTTPException(403, "department_scope")


def _get_job(job_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM job_openings WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Job not found")
    return row


def _get_applicant_with_job(applicant_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT a.*, j.department AS job_department, j.rubric_version AS job_rubric_version "
            "FROM applicants a JOIN job_openings j ON j.id = a.job_id WHERE a.id = ?",
            (applicant_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Applicant not found")
    return row


def _job_engine_dict(job_row) -> dict:
    return _job_dict(job_row)


def _validate_job(job: dict) -> None:
    # The engine is the source of truth for gate names, education levels and
    # weight validity. Empty CV values leave gates unknown without failing them.
    try:
        score(parse_cv(""), job)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc))


def _taxonomy_snapshot() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, canonical, category, aliases FROM skills_taxonomy WHERE is_active=1"
        ).fetchall()
    return [
        {**dict(row), "aliases": _load_json(row["aliases"], [])}
        for row in rows
    ]


def _parse_with_taxonomy(cv_text: str, taxonomy: Optional[list[dict]] = None):
    """Parse with the editable DB taxonomy (the seed is only the starting copy)."""
    taxonomy = taxonomy if taxonomy is not None else _taxonomy_snapshot()
    return parse_cv(cv_text, taxonomy=taxonomy)


def _corrected_parsed(
    cv_text: str,
    corrections: dict,
    profile: Optional[dict] = None,
    taxonomy: Optional[list[dict]] = None,
):
    parsed = _parse_with_taxonomy(cv_text, taxonomy)
    profile = profile or {}
    profile_updates = {
        key: profile[key]
        for key in ("nationality", "city")
        if profile.get(key)
    }
    if profile_updates:
        parsed = replace(parsed, **profile_updates)

    allowed = {
        "years_experience", "education", "languages", "skills", "nationality", "city",
        "willing_to_relocate", "driving_licence", "transferable_iqama",
    }
    unknown = set(corrections) - allowed
    if unknown:
        raise HTTPException(400, f"Unsupported correction fields: {', '.join(sorted(unknown))}")

    updates: dict[str, Any] = {}
    if "years_experience" in corrections:
        value = corrections["years_experience"]
        if value is not None:
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise HTTPException(400, "years_experience must be numeric or null")
            if not 0 <= value <= 80:
                raise HTTPException(400, "years_experience must be between 0 and 80")
        updates["years_experience"] = value
    if "education" in corrections:
        value = corrections["education"]
        if value in (None, ""):
            updates.update(education=None, education_ordinal=None)
        else:
            key = str(value).strip().lower().replace(" ", "_").replace("-", "_")
            if key not in EDUCATION_ORDINAL:
                raise HTTPException(400, "Unknown education level")
            updates.update(education=key, education_ordinal=EDUCATION_ORDINAL[key])
    if "languages" in corrections:
        values = corrections["languages"]
        if not isinstance(values, list) or any(not isinstance(item, str) or len(item) > 80 for item in values):
            raise HTTPException(400, "languages correction must be a list of short strings")
        updates["languages"] = [item.strip() for item in values if item.strip()]
    if "skills" in corrections:
        values = corrections["skills"]
        if not isinstance(values, list) or len(values) > 200:
            raise HTTPException(400, "skills correction must be a list")
        existing = {item.id: item for item in parsed.skills}
        corrected = []
        for item in values:
            skill_id = item.get("skill_id", item.get("id", "")) if isinstance(item, dict) else str(item)
            skill_id = skill_id.strip().lower().replace(" ", "_").replace("-", "_")
            if not skill_id or len(skill_id) > 100:
                raise HTTPException(400, "invalid skill correction")
            if skill_id in existing:
                corrected.append(existing[skill_id])
                continue
            meta = SKILLS_BY_ID.get(skill_id, {"canonical": skill_id.replace("_", " "), "category": "manual"})
            corrected.append(SkillMatch(
                skill_id, meta["canonical"], meta["category"],
                [Evidence("manual correction", f"HR correction: {meta['canonical']}", -1)],
            ))
        updates["skills"] = corrected
    for key in ("nationality", "city"):
        if key in corrections:
            value = corrections[key]
            if value is not None and (not isinstance(value, str) or len(value) > 120):
                raise HTTPException(400, f"{key} must be a short string or null")
            updates[key] = value.strip() if isinstance(value, str) else value
    for key in ("willing_to_relocate", "driving_licence", "transferable_iqama"):
        if key in corrections:
            value = corrections[key]
            if value is not None and not isinstance(value, bool):
                raise HTTPException(400, f"{key} must be boolean or null")
            updates[key] = value
    return replace(parsed, **updates) if updates else parsed


def _score_stored(
    cv_text: str,
    corrections: dict,
    job: dict,
    profile: Optional[dict] = None,
    taxonomy: Optional[list[dict]] = None,
):
    parsed = _corrected_parsed(cv_text, corrections, profile, taxonomy)
    try:
        return score(parsed, job)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc))


def _score_values(result) -> tuple:
    result_dict = result.to_dict()
    return (
        result.rules_score,
        result.rules_score,
        result.rules_score,
        _json(result_dict["breakdown"]),
        _json(result.gate_failures),
    )


@router.get("/templates")
def list_templates(_: CurrentUser = Depends(_hr_staff)):
    """Starter role templates the "New job" form pre-fills from."""
    keys = ("id", "title", "required_skills", "preferred_skills", "min_years",
            "min_education", "languages", "gates", "weights")
    return [{key: template[key] for key in keys} for template in ROLE_TEMPLATES]


@router.get("/jobs")
def list_jobs(user: CurrentUser = Depends(_hr_or_head)):
    sql = (
        "SELECT id, title, department, location, employment_type, status, min_years, "
        "min_education, gates, required_skills, preferred_skills, languages, weights, "
        "rubric_version, semantic_criteria, created_by, created_at, closed_at "
        "FROM job_openings"
    )
    params: tuple = ()
    if user.role == ROLE_DEPT_HEAD:
        sql += " WHERE department = ?"
        params = (user.department,)
    sql += " ORDER BY created_at DESC, id DESC"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_job_dict(row, include_description=False) for row in rows]


@router.post("/jobs", status_code=201)
def create_job(payload: JobIn, user: CurrentUser = Depends(_hr_staff)):
    values = payload.model_dump()
    if not values["weights"]:
        values["weights"] = dict(DEFAULT_WEIGHTS)
    _validate_job(values)
    now = _now()
    closed_at = now if values["status"] == "closed" else None
    with db() as conn:
        row = conn.execute(
            """INSERT INTO job_openings
               (title, department, location, employment_type, description, status,
                min_years, min_education, gates, required_skills, preferred_skills,
                languages, weights, rubric_version, semantic_criteria, created_by,
                created_at, closed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
               RETURNING *""",
            (
                values["title"], values["department"], values["location"], values["employment_type"],
                values["description"], values["status"], values["min_years"], values["min_education"],
                _json(values["gates"]), _json(values["required_skills"]),
                _json(values["preferred_skills"]), _json(values["languages"]), _json(values["weights"]),
                _json(values["semantic_criteria"]), user.name, now, closed_at,
            ),
        ).fetchone()
    return _job_dict(row)


@router.get("/jobs/{job_id}")
def get_job(job_id: int, user: CurrentUser = Depends(_hr_or_head)):
    row = _get_job(job_id)
    _ensure_department(user, row["department"])
    return _job_dict(row)


@router.put("/jobs/{job_id}")
def update_job(job_id: int, payload: JobIn, user: CurrentUser = Depends(_hr_staff)):
    values = payload.model_dump()
    if not values["weights"]:
        values["weights"] = dict(DEFAULT_WEIGHTS)
    _validate_job(values)
    criteria_fields = {
        "min_years", "min_education", "gates", "required_skills",
        "preferred_skills", "languages", "weights", "semantic_criteria",
    }
    with db() as conn:
        # Read + version + write under the lock every score publisher takes, so two
        # edits can't both claim the same rubric_version.
        lock(conn)
        old_row = conn.execute("SELECT * FROM job_openings WHERE id = ?", (job_id,)).fetchone()
        if old_row is None:
            raise HTTPException(404, "Job not found")
        old = _job_dict(old_row)
        changed = any(old[field] != values[field] for field in criteria_fields)
        rubric_version = old["rubric_version"] + (1 if changed else 0)
        closed_at = old["closed_at"]
        if values["status"] != old["status"]:
            closed_at = _now() if values["status"] == "closed" else None
        if values["status"] == "closed":
            privacy.start_retention_for_job(conn, job_id)
        row = conn.execute(
            """UPDATE job_openings SET title=?, department=?, location=?, employment_type=?,
               description=?, status=?, min_years=?, min_education=?, gates=?, required_skills=?,
               preferred_skills=?, languages=?, weights=?, rubric_version=?, semantic_criteria=?, closed_at=?
               WHERE id=? RETURNING *""",
            (
                values["title"], values["department"], values["location"], values["employment_type"],
                values["description"], values["status"], values["min_years"], values["min_education"],
                _json(values["gates"]), _json(values["required_skills"]),
                _json(values["preferred_skills"]), _json(values["languages"]), _json(values["weights"]),
                rubric_version, _json(values["semantic_criteria"]), closed_at, job_id,
            ),
        ).fetchone()
        applicants = conn.execute(
            f"SELECT {_RESCORE_COLUMNS} FROM applicants WHERE job_id = ? AND cv_purged_at IS NULL",
            (job_id,),
        ).fetchall() if changed else []

    updated_job = _job_dict(row)
    updated_job["rescored_applicants"] = _rescore_applicants(updated_job, applicants)
    return updated_job


_RESCORE_COLUMNS = "id, cv_text, corrections, nationality, city, row_version"


def _rescore_applicants(job: dict, applicants) -> int:
    """Score applicants outside the lock, then publish under it; returns rows published."""
    rescored = []
    taxonomy = _taxonomy_snapshot() if applicants else []
    rubric_version = job["rubric_version"]
    for applicant in applicants:
        result = _score_stored(
            applicant["cv_text"], _load_json(applicant["corrections"], {}), job,
            {"nationality": applicant["nationality"], "city": applicant["city"]}, taxonomy,
        )
        rescored.append((*_score_values(result), rubric_version, _now(), applicant["id"], applicant["row_version"],
                         job["id"], rubric_version))
    published = 0
    if rescored:
        with db() as conn:
            lock(conn)
            for item in rescored:
                # A concurrent edit, CV removal, deletion or newer rubric wins; that row keeps its old score.
                published += conn.execute(
                    "UPDATE applicants SET score=?, rules_score=?, final_score=?, score_breakdown=?, "
                    "gate_failures=?, scored_rubric_version=?, updated_at=?, row_version=row_version+1 "
                    "WHERE id=? AND row_version=? AND cv_purged_at IS NULL "
                    "AND (SELECT rubric_version FROM job_openings WHERE id=?) = ?",
                    item,
                ).rowcount
    return published


@router.post("/jobs/{job_id}/rescore")
def rescore_job(job_id: int, _: CurrentUser = Depends(_hr_staff)):
    """Re-score a job's applicants with the current taxonomy, criteria unchanged."""
    with db() as conn:
        lock(conn)
        row = conn.execute("SELECT * FROM job_openings WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Job not found")
        applicants = conn.execute(
            f"SELECT {_RESCORE_COLUMNS} FROM applicants WHERE job_id = ? AND cv_purged_at IS NULL",
            (job_id,),
        ).fetchall()
    return {"rescored_applicants": _rescore_applicants(_job_dict(row), applicants)}


@router.post("/jobs/{job_id}/close")
def close_job(job_id: int, _: CurrentUser = Depends(_hr_staff)):
    if _get_job(job_id)["status"] == "closed":
        return {"id": job_id, "status": "closed"}
    now = _now()
    with db() as conn:
        lock(conn)  # an upload in flight re-checks the status under this same lock
        privacy.start_retention_for_job(conn, job_id)
        conn.execute("UPDATE job_openings SET status='closed', closed_at=? WHERE id=?", (now, job_id))
    return {"id": job_id, "status": "closed", "closed_at": now}


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: int, _: CurrentUser = Depends(_hr_staff)):
    """Delete a job that never received applicants (e.g. created by mistake).

    applicants.job_id cascades, so a job with applicants is refused: those go
    through the applicant delete/retention paths, which keep the audit trail.
    """
    with db() as conn:
        lock(conn)  # same lock as upload, so no applicant can arrive between check and delete
        if conn.execute("SELECT 1 FROM job_openings WHERE id = ?", (job_id,)).fetchone() is None:
            raise HTTPException(404, "Job not found")
        if conn.execute("SELECT 1 FROM applicants WHERE job_id = ? LIMIT 1", (job_id,)).fetchone():
            raise HTTPException(409, "job_has_applicants")
        conn.execute("DELETE FROM job_openings WHERE id = ?", (job_id,))


@router.get("/jobs/{job_id}/applicants")
def list_applicants(
    job_id: int,
    stage: Optional[str] = Query(None, pattern="^(new|screened|shortlisted|interview|offer|hired|rejected)$"),
    sort: str = Query("score", pattern="^(score|newest)$"),
    user: CurrentUser = Depends(_hr_or_head),
):
    job = _get_job(job_id)
    _ensure_department(user, job["department"])
    where = "job_id = ?"
    params: list[Any] = [job_id]
    if stage:
        where += " AND stage = ?"
        params.append(stage)
    order = "score DESC, id ASC" if sort == "score" else "created_at DESC, id DESC"
    with db() as conn:
        rows = conn.execute(
            "SELECT id, job_id, full_name, email, phone, nationality, city, source, stage, "
            "cv_name, cv_mime, score, rules_score, final_score, parsed, corrections, "
            "score_breakdown, gate_failures, needs_manual_review, notes, cv_revision, "
            "semantic_status, semantic_reason, external_processing_consent_at, "
            "consent_notice_version, created_by, created_at, updated_at, scored_rubric_version, "
            "retention_started_at, erase_after, cv_purged_at, cv_purge_reason, "
            "(cv_attachment != '') AS has_cv FROM applicants WHERE " + where + " ORDER BY " + order,
            params,
        ).fetchall()
    result = []
    for row in rows:
        item = _applicant_public(row, include_detail=False, job_rubric_version=job["rubric_version"])
        item["has_cv"] = bool(row["has_cv"])
        # Two summary columns for the ranked table; HR corrections win over the parser.
        parsed = _load_json(row["parsed"], {})
        corrections = _load_json(row["corrections"], {})
        for key in ("years_experience", "education"):
            item[key] = corrections[key] if key in corrections else parsed.get(key)
        result.append(item)
    return result


@router.post("/jobs/{job_id}/applicants", status_code=201)
def create_applicant(job_id: int, payload: ApplicantIn, user: CurrentUser = Depends(_hr_staff)):
    if not payload.notice_attested or payload.notice_channel not in privacy.NOTICE_CHANNELS:
        raise HTTPException(400, "notice_required")
    job_row = _get_job(job_id)
    if job_row["status"] != "open":
        raise HTTPException(409, "job_closed")
    try:
        raw = base64.b64decode(payload.cv_attachment, validate=True)
        extracted = extract_text(raw, payload.cv_name)
        parsed = _parse_with_taxonomy(extracted.text)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    profile = {"nationality": payload.nationality, "city": payload.city}
    scored_parsed = replace(parsed, **{key: value for key, value in profile.items() if value})
    try:
        scored = score(scored_parsed, _job_engine_dict(job_row))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc))

    full_name = payload.full_name or parsed.name or ""
    email = payload.email or parsed.email or ""
    phone = payload.phone or parsed.phone or ""
    now = _now()
    values = _score_values(scored)
    try:
        with db() as conn:
            lock(conn)
            current = conn.execute(
                "SELECT status, rubric_version FROM job_openings WHERE id=?", (job_id,)
            ).fetchone()
            if current is None or current["status"] != "open":
                raise HTTPException(409, "job_closed")
            if current["rubric_version"] != job_row["rubric_version"]:
                raise HTTPException(409, "criteria_changed")
            # The promise is what the notice said; fall back to today's setting if the client didn't say.
            promised_days = payload.notice_retention_days or privacy.retention_days(conn)
            row = conn.execute(
                """INSERT INTO applicants
                   (job_id, full_name, email, phone, nationality, city, source, stage,
                    cv_attachment, cv_name, cv_mime, cv_text, parsed, corrections,
                    score, rules_score, final_score, score_breakdown, gate_failures,
                    needs_manual_review, notes, cv_revision, semantic_status, semantic_reason,
                    external_processing_consent_at, consent_notice_version, created_by,
                    created_at, updated_at, scored_rubric_version, notice_attested_at,
                    notice_attested_by, notice_channel, processing_notice_version, notice_retention_days)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?, '{}', ?, ?, ?, ?, ?,
                           ?, ?, 1, 'disabled', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *""",
                (
                    job_id, full_name, email.lower(), phone, payload.nationality, payload.city, payload.source,
                    payload.cv_attachment, payload.cv_name, payload.cv_mime, extracted.text,
                    _json(parsed.to_dict()), *values[:3], values[3], values[4],
                    int(extracted.needs_manual_review), payload.notes,
                    "semantic processing is disabled in Phase 2",
                    payload.external_processing_consent_at, payload.consent_notice_version,
                    user.name, now, now, job_row["rubric_version"],
                    privacy.utc_str(privacy.utc_now()), user.id, payload.notice_channel, privacy.NOTICE_VERSION,
                    promised_days,
                ),
            ).fetchone()
    except IntegrityError:
        raise HTTPException(409, "duplicate_application")
    return _applicant_public(row, job_rubric_version=job_row["rubric_version"])


@router.get("/jobs/{job_id}/export")
def export_applicants(job_id: int, _: CurrentUser = Depends(_manager)):
    job = _get_job(job_id)
    with db() as conn:
        rows = conn.execute(
            "SELECT id, full_name, email, phone, nationality, city, source, stage, score, "
            "parsed, gate_failures, needs_manual_review, created_at FROM applicants "
            "WHERE job_id = ? ORDER BY score DESC, id ASC",
            (job_id,),
        ).fetchall()
    wb = Workbook()
    ws = wb.active
    ws.title = "Applicants"
    ws.append([
        "Rank", "ID", "Name", "Email", "Phone", "Nationality", "City", "Source", "Stage",
        "Score", "Years", "Education", "Gate failures", "Needs review", "Created At",
    ])
    for rank, r in enumerate(rows, start=1):
        parsed = _load_json(r["parsed"], {})
        ws.append([
            rank, r["id"], _xlsx_safe(r["full_name"]), _xlsx_safe(r["email"]), _xlsx_safe(r["phone"]),
            _xlsx_safe(r["nationality"]), _xlsx_safe(r["city"]), _xlsx_safe(r["source"]), r["stage"],
            r["score"], parsed.get("years_experience"), parsed.get("education"),
            ", ".join(_load_json(r["gate_failures"], [])), "yes" if r["needs_manual_review"] else "",
            r["created_at"],
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"applicants_job{job['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/applicants/{applicant_id}")
def get_applicant(applicant_id: int, user: CurrentUser = Depends(_hr_or_head)):
    row = _get_applicant_with_job(applicant_id)
    _ensure_department(user, row["job_department"])
    with db() as conn:
        history = conn.execute(
            "SELECT * FROM applicant_stage_history WHERE applicant_id=? ORDER BY id", (applicant_id,)
        ).fetchall()
        feedback = conn.execute(
            "SELECT * FROM interview_feedback WHERE applicant_id=? ORDER BY id DESC", (applicant_id,)
        ).fetchall()
    result = _applicant_public(row, job_rubric_version=row["job_rubric_version"])
    result.pop("job_department", None)
    result.pop("job_rubric_version", None)
    result["history"] = [dict(item) for item in history]
    result["feedback"] = [
        {**dict(item), "ratings": _load_json(item["ratings"], [])} for item in feedback
    ]
    return result


@router.get("/applicants/{applicant_id}/cv")
def get_cv(applicant_id: int, _: CurrentUser = Depends(_manager)):
    with db() as conn:
        row = conn.execute(
            "SELECT cv_attachment, cv_name, cv_mime, cv_purged_at FROM applicants WHERE id=?", (applicant_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Applicant not found")
    if row["cv_purged_at"]:
        raise HTTPException(410, "cv_removed")
    if not row["cv_attachment"]:
        raise HTTPException(404, "No CV")
    return {"id": applicant_id, "cv_attachment": row["cv_attachment"], "cv_name": row["cv_name"], "cv_mime": row["cv_mime"]}


@router.patch("/applicants/{applicant_id}")
def patch_applicant(applicant_id: int, payload: ApplicantPatchIn, _: CurrentUser = Depends(_hr_staff)):
    row = _get_applicant_with_job(applicant_id)
    if row["cv_purged_at"]:
        raise HTTPException(409, "cv_purged")
    supplied = payload.model_fields_set
    if not supplied:
        raise HTTPException(400, "No changes supplied")
    corrections = _load_json(row["corrections"], {})
    if "corrections" in supplied:
        corrections = payload.corrections or {}
    notes = payload.notes if "notes" in supplied else row["notes"]
    job_row = _get_job(row["job_id"])
    result = _score_stored(
        row["cv_text"], corrections, _job_engine_dict(job_row),
        {"nationality": row["nationality"], "city": row["city"]},
    )
    values = _score_values(result)
    with db() as conn:
        lock(conn)
        updated = conn.execute(
            "UPDATE applicants SET notes=?, corrections=?, score=?, rules_score=?, final_score=?, "
            "score_breakdown=?, gate_failures=?, scored_rubric_version=?, updated_at=?, "
            "row_version=row_version+1 WHERE id=? AND row_version=? AND cv_purged_at IS NULL "
            "AND (SELECT rubric_version FROM job_openings WHERE id=?) = ? RETURNING *",
            (notes, _json(corrections), *values, job_row["rubric_version"], _now(), applicant_id, row["row_version"],
             job_row["id"], job_row["rubric_version"]),
        ).fetchone()
    if updated is None:
        raise HTTPException(409, "conflict")
    return _applicant_public(updated, job_rubric_version=job_row["rubric_version"])


@router.post("/applicants/{applicant_id}/stage")
def change_stage(
    applicant_id: int, payload: StageIn, background: BackgroundTasks, user: CurrentUser = Depends(_hr_staff),
):
    now = _now()
    with db() as conn:
        lock(conn)
        row = conn.execute(
            "SELECT a.stage, a.email, a.full_name, a.cv_purged_at, j.title FROM applicants a "
            "JOIN job_openings j ON j.id = a.job_id WHERE a.id=?", (applicant_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Applicant not found")
        old = row["stage"]
        if payload.stage not in _STAGE_NEXT[old]:
            raise HTTPException(409, "invalid_stage_transition")
        if row["cv_purged_at"] and payload.stage != "rejected":
            raise HTTPException(409, "cv_purged")
        if payload.notify:
            if row["cv_purged_at"]:
                raise HTTPException(409, "cv_purged")
            if not privacy.emails_enabled(conn):
                raise HTTPException(400, "stage_emails_disabled")
            if payload.stage not in privacy.EMAIL_STAGES:
                raise HTTPException(400, "no_email_for_stage")
            if not privacy.valid_recipient(row["email"]):
                raise HTTPException(400, "invalid_recipient")
            message = privacy.render_email(conn, payload.stage, payload.notify_language, row["full_name"], row["title"])
            if payload.preview_hash != privacy.message_hash(message):
                raise HTTPException(409, "preview_outdated")
        note = "" if row["cv_purged_at"] else payload.note  # a removed CV's record stays frozen
        privacy.cancel_pending_emails(conn, applicant_id)  # a newer move supersedes a queued email
        conn.execute(
            "UPDATE applicants SET stage=?, updated_at=?, row_version=row_version+1 WHERE id=?",
            (payload.stage, now, applicant_id),
        )
        if payload.stage in privacy.TERMINAL_STAGES:
            privacy.start_retention_for_applicant(conn, applicant_id)
        history = conn.execute(
            "INSERT INTO applicant_stage_history "
            "(applicant_id, old_stage, new_stage, note, changed_by, changed_at, notify_status, notify_language, "
            "notify_subject, notify_body) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *",
            (applicant_id, old, payload.stage, note, user.name, now,
             "pending" if payload.notify else "", payload.notify_language if payload.notify else "",
             message["subject"] if payload.notify else "", message["body"] if payload.notify else ""),
        ).fetchone()
    if payload.notify:
        background.add_task(privacy.send_stage_email, history["id"])
    return dict(history)


@router.get("/applicants/{applicant_id}/stage-email-preview")
def stage_email_preview(
    applicant_id: int,
    stage: str = Query(..., pattern="^(interview|offer|rejected)$"),
    lang: str = Query("en", pattern="^(en|ar)$"),
    _: CurrentUser = Depends(_hr_staff),
):
    row = _get_applicant_with_job(applicant_id)
    with db() as conn:
        title = conn.execute("SELECT title FROM job_openings WHERE id=?", (row["job_id"],)).fetchone()["title"]
        message = privacy.render_email(conn, stage, lang, row["full_name"], title)
        enabled = privacy.emails_enabled(conn)
    return {"to": row["email"], "valid_recipient": privacy.valid_recipient(row["email"]),
            "enabled": enabled and email_configured(), "hash": privacy.message_hash(message), **message}


@router.post("/applicants/{applicant_id}/purge-cv")
def purge_applicant_cv(applicant_id: int, payload: PurgeCvIn, user: CurrentUser = Depends(_manager)):
    with db() as conn:
        lock(conn)
        if not privacy.purge_cv(conn, applicant_id, str(user.id), payload.reason):
            exists = conn.execute("SELECT 1 FROM applicants WHERE id=?", (applicant_id,)).fetchone()
            raise HTTPException(409 if exists else 404, "already_removed" if exists else "Applicant not found")
    return {"id": applicant_id, "cv_removed": True}


@router.delete("/applicants/{applicant_id}", status_code=204)
def delete_applicant(
    applicant_id: int,
    reason: str = Query("manual", pattern="^(manual|erasure_request)$"),
    all_for_email: bool = False,
    user: CurrentUser = Depends(_manager),
):
    with db() as conn:
        lock(conn)
        found = conn.execute("SELECT id, job_id, email FROM applicants WHERE id=?", (applicant_id,)).fetchone()
        if found is None:
            raise HTTPException(404, "Applicant not found")
        targets = [found]
        if all_for_email and found["email"]:
            targets = conn.execute(
                "SELECT id, job_id, email FROM applicants WHERE email=?", (found["email"],)
            ).fetchall()
        for target in targets:
            conn.execute("DELETE FROM applicants WHERE id=?", (target["id"],))
            privacy.log_event(conn, "deleted", target["id"], target["job_id"], str(user.id), reason)


@router.get("/applicants/{applicant_id}/feedback")
def list_feedback(applicant_id: int, user: CurrentUser = Depends(_hr_or_head)):
    applicant = _get_applicant_with_job(applicant_id)
    _ensure_department(user, applicant["job_department"])
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM interview_feedback WHERE applicant_id=? ORDER BY id DESC", (applicant_id,)
        ).fetchall()
    return [{**dict(row), "ratings": _load_json(row["ratings"], [])} for row in rows]


@router.post("/applicants/{applicant_id}/feedback", status_code=201)
def create_feedback(applicant_id: int, payload: FeedbackIn, user: CurrentUser = Depends(_hr_or_head)):
    applicant = _get_applicant_with_job(applicant_id)
    _ensure_department(user, applicant["job_department"])
    ratings = [item.model_dump() for item in payload.ratings]
    average = round(sum(item["score_1_5"] for item in ratings) / len(ratings), 2) if ratings else 0.0
    with db() as conn:
        lock(conn)  # CV removal / deletion can't slip in between the check and the insert
        current = conn.execute("SELECT cv_purged_at FROM applicants WHERE id=?", (applicant_id,)).fetchone()
        if current is None:
            raise HTTPException(404, "Applicant not found")
        if current["cv_purged_at"]:
            raise HTTPException(409, "cv_purged")
        row = conn.execute(
            "INSERT INTO interview_feedback "
            "(applicant_id, interviewer, result, ratings, avg_rating, comment, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING *",
            (applicant_id, user.name, payload.result, _json(ratings), average, payload.comment, _now()),
        ).fetchone()
    return {**dict(row), "ratings": ratings}


@router.get("/taxonomy")
def list_taxonomy(_: CurrentUser = Depends(_hr_staff)):
    with db() as conn:
        rows = conn.execute("SELECT * FROM skills_taxonomy ORDER BY category, canonical").fetchall()
    return [{**dict(row), "aliases": _load_json(row["aliases"], []), "is_active": bool(row["is_active"])} for row in rows]


@router.post("/taxonomy")
def upsert_taxonomy(payload: TaxonomyIn, _: CurrentUser = Depends(_manager)):
    with db() as conn:
        lock(conn)
        exists = conn.execute("SELECT 1 FROM skills_taxonomy WHERE id=?", (payload.id,)).fetchone()
        if exists:
            row = conn.execute(
                "UPDATE skills_taxonomy SET canonical=?, category=?, aliases=?, is_active=? WHERE id=? RETURNING *",
                (payload.canonical, payload.category, _json(payload.aliases), int(payload.is_active), payload.id),
            ).fetchone()
        else:
            row = conn.execute(
                "INSERT INTO skills_taxonomy (id, canonical, category, aliases, is_active) "
                "VALUES (?, ?, ?, ?, ?) RETURNING *",
                (payload.id, payload.canonical, payload.category, _json(payload.aliases), int(payload.is_active)),
            ).fetchone()
    return {**dict(row), "aliases": _load_json(row["aliases"], []), "is_active": bool(row["is_active"])}


@router.post("/parse-preview")
def parse_preview(payload: ParsePreviewIn, _: CurrentUser = Depends(_hr_staff)):
    if not payload.notice_attested:
        raise HTTPException(400, "notice_required")
    try:
        extracted = extract_text(base64.b64decode(payload.cv_attachment, validate=True), payload.cv_name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    parsed = _parse_with_taxonomy(extracted.text).to_dict()
    for key in _PARSED_PRIVATE:
        parsed.pop(key, None)
    extraction = {"pages": extracted.pages, "needs_manual_review": extracted.needs_manual_review,
                  "warnings": extracted.warnings}
    return {"extraction": extraction, "parsed": parsed}


@router.get("/policy")
def recruitment_policy(_: CurrentUser = Depends(_hr_or_head)):
    """What the UI needs to show the notice, retention and email options."""
    with db() as conn:
        days = privacy.retention_days(conn)
        enabled = privacy.emails_enabled(conn)
    return {
        "notice_version": privacy.NOTICE_VERSION, "notice_channels": list(privacy.NOTICE_CHANNELS),
        "retention_days": days, "stage_emails_enabled": enabled and email_configured(),
        "email_stages": list(privacy.EMAIL_STAGES),
    }


@router.get("/retention")
def get_retention(_: CurrentUser = Depends(_manager)):
    now = privacy.utc_str(privacy.utc_now())
    with db() as conn:
        due = conn.execute(
            "SELECT COUNT(*) FROM applicants WHERE erase_after IS NOT NULL AND erase_after <= ?", (now,)
        ).fetchone()[0]
        return {"days": privacy.retention_days(conn), "min_days": privacy.MIN_DAYS, "max_days": privacy.MAX_DAYS,
                "due_now": due, "last_run": privacy.last_run(conn)}


@router.put("/retention")
def put_retention(payload: RetentionIn, _: CurrentUser = Depends(_manager)):
    try:
        privacy.set_retention_days(payload.days)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return get_retention(_)


@router.post("/retention/run")
def run_retention(dry_run: bool = True, user: CurrentUser = Depends(_manager)):
    return privacy.sweep(dry_run=dry_run, actor=str(user.id))


@router.get("/email-settings")
def get_email_settings(_: CurrentUser = Depends(_manager)):
    with db() as conn:
        return {"enabled": privacy.emails_enabled(conn), "templates": privacy.email_templates(conn),
                "email_configured": email_configured(), "stages": list(privacy.EMAIL_STAGES)}


@router.put("/email-settings")
def put_email_settings(payload: EmailSettingsIn, _: CurrentUser = Depends(_manager)):
    try:
        return privacy.save_email_settings(payload.enabled, payload.templates)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/stats")
def recruitment_stats(_: CurrentUser = Depends(_hr_staff)):
    with db() as conn:
        open_jobs = conn.execute("SELECT COUNT(*) FROM job_openings WHERE status='open'").fetchone()[0]
        total_applicants = conn.execute("SELECT COUNT(*) FROM applicants").fetchone()[0]
        stages = conn.execute("SELECT stage, COUNT(*) AS count FROM applicants GROUP BY stage").fetchall()
        jobs = conn.execute(
            "SELECT j.id AS job_id, j.title, COUNT(a.id) AS applicant_count, AVG(a.score) AS avg_score "
            "FROM job_openings j LEFT JOIN applicants a ON a.job_id=j.id GROUP BY j.id, j.title ORDER BY j.id"
        ).fetchall()
    return {
        "open_jobs": open_jobs,
        "total_applicants": total_applicants,
        "applicants_per_stage": {row["stage"]: row["count"] for row in stages},
        "jobs": [
            {**dict(row), "avg_score": round(row["avg_score"], 2) if row["avg_score"] is not None else None}
            for row in jobs
        ],
    }
