import io
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from ..auth import (
    ROLE_DEPT_HEAD,
    ROLE_EMPLOYEE,
    ROLE_HR_MANAGER,
    ROLE_HR_OFFICER,
    CurrentUser,
    require_role,
    require_user,
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_date(value: Optional[str], name: str) -> None:
    if value and not _DATE_RE.match(value):
        raise HTTPException(400, f"{name} must be formatted YYYY-MM-DD")


def _xlsx_safe(value):
    """Neutralise Excel formula injection: a cell starting with =, +, -, @ or a
    control char would otherwise be evaluated as a formula when opened."""
    if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value

from ..db import db
from ..penalties import MATRIX_DATA, PENALTY_MAP
from ..schemas import Violation, ViolationIn

router = APIRouter(prefix="/violations", tags=["violations"])

_hr_staff = require_role(ROLE_HR_MANAGER, ROLE_HR_OFFICER)


def _scope_clause(user: CurrentUser) -> tuple[str, list]:
    """Horizontal access control: department heads only see their own
    department's violations; employees only see their own record."""
    if user.role == ROLE_DEPT_HEAD:
        return "employee_name IN (SELECT name FROM employees WHERE department = ?)", [user.department]
    if user.role == ROLE_EMPLOYEE:
        return "employee_name IN (SELECT name FROM employees WHERE email = ?)", [user.email]
    return "", []


def _next_penalty(emp_name: str, category: str, incident: str) -> str:
    meta = MATRIX_DATA[category][incident]
    escalation = meta["escalation"]
    reset_days = meta["reset"]
    cutoff = (datetime.now() - timedelta(days=reset_days)).strftime("%Y-%m-%d %H:%M:%S")

    with db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) FROM violations
               WHERE employee_name = ?
                 AND incident = ?
                 AND created_at >= ?
                 AND penalty_color != 'Investigation'""",
            (emp_name, incident, cutoff),
        ).fetchone()
    count = row[0] if row else 0
    idx = min(count, len(escalation) - 1)
    return escalation[idx]


@router.get("", response_model=list[Violation])
def list_violations(
    employee: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    incident: Optional[str] = None,
    penalty: Optional[str] = None,
    user: CurrentUser = Depends(require_user),
):
    _check_date(date_from, "date_from")
    _check_date(date_to, "date_to")
    clauses = ["1=1"]
    params: list = []
    scope_sql, scope_params = _scope_clause(user)
    if scope_sql:
        clauses.append(scope_sql)
        params.extend(scope_params)
    if employee:
        clauses.append("employee_name = ?")
        params.append(employee)
    if date_from:
        clauses.append("created_at >= ?")
        params.append(f"{date_from} 00:00:00")
    if date_to:
        clauses.append("created_at <= ?")
        params.append(f"{date_to} 23:59:59")
    if incident:
        clauses.append("incident = ?")
        params.append(incident)
    if penalty:
        clauses.append("penalty_color = ?")
        params.append(penalty)

    # Select every column EXCEPT the heavy base64 proof_image; expose a boolean
    # flag instead so the grid stays small (a single image can be ~600 KB).
    sql = (
        "SELECT id, employee_name, category, incident, penalty_color, penalty_label, "
        "deduction_hours, deduction_days, freeze_months, comment, submitted_by, "
        "created_at, (proof_image != '') AS has_proof "
        f"FROM violations WHERE {' AND '.join(clauses)} ORDER BY created_at DESC"
    )
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [{**dict(r), "has_proof": bool(r["has_proof"])} for r in rows]


@router.get("/{vid}/proof")
def get_proof(vid: int, _: CurrentUser = Depends(_hr_staff)):
    """Fetch a single violation's proof image (base64) on demand."""
    with db() as conn:
        row = conn.execute("SELECT proof_image FROM violations WHERE id = ?", (vid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Violation not found")
    return {"id": vid, "proof_image": row["proof_image"] or ""}


@router.post("", response_model=Violation, status_code=201)
def create_violation(payload: ViolationIn, user: CurrentUser = Depends(_hr_staff)):
    if payload.category not in MATRIX_DATA or payload.incident not in MATRIX_DATA[payload.category]:
        raise HTTPException(400, "Unknown category or incident")

    color = "Investigation" if payload.force_investigation else _next_penalty(
        payload.employee_name, payload.category, payload.incident
    )
    p = PENALTY_MAP[color]

    applied = (
        payload.override_days
        if payload.override_days is not None and payload.override_days >= 0
        else p["deduction_days"]
    )
    if applied != p["deduction_days"] and color != "Investigation":
        label = f"{color} Card \u2014 {applied} Days Deduction (Override)"
    else:
        label = p["label"]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO violations
               (employee_name, category, incident, penalty_color, penalty_label,
                deduction_hours, deduction_days, freeze_months,
                comment, submitted_by, proof_image, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING *""",
            (
                payload.employee_name, payload.category, payload.incident,
                color, label,
                p["deduction_hours"], applied, p["freeze_months"],
                payload.comment, user.name, payload.proof_image,
                now,
            ),
        )
        row = dict(cur.fetchone())
    row["has_proof"] = bool(row.pop("proof_image", ""))
    return row


@router.delete("/{vid}", status_code=204)
def delete_violation(vid: int, _: CurrentUser = Depends(require_role(ROLE_HR_MANAGER))):
    with db() as conn:
        conn.execute("DELETE FROM violations WHERE id = ?", (vid,))


@router.get("/preview")
def preview_next(
    employee_name: str = Query(...),
    category: str = Query(...),
    incident: str = Query(...),
    _: CurrentUser = Depends(_hr_staff),
):
    if category not in MATRIX_DATA or incident not in MATRIX_DATA[category]:
        raise HTTPException(400, "Unknown category or incident")
    color = _next_penalty(employee_name, category, incident)
    meta = MATRIX_DATA[category][incident]
    return {"penalty_color": color, "penalty": PENALTY_MAP[color], "escalation": meta["escalation"], "reset": meta["reset"]}


@router.get("/export")
def export_violations(
    employee: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    incident: Optional[str] = None,
    penalty: Optional[str] = None,
    user: CurrentUser = Depends(_hr_staff),
):
    rows = list_violations(employee, date_from, date_to, incident, penalty, user)
    wb = Workbook()
    ws = wb.active
    ws.title = "Violations"
    headers = [
        "ID", "Employee", "Category", "Incident", "Penalty Color", "Penalty Label",
        "Deduction Hours", "Deduction Days", "Freeze Months", "Comment",
        "Submitted By", "Created At",
    ]
    ws.append(headers)
    for r in rows:
        ws.append([
            r["id"], _xlsx_safe(r["employee_name"]), _xlsx_safe(r["category"]), _xlsx_safe(r["incident"]),
            r["penalty_color"], _xlsx_safe(r["penalty_label"]),
            r["deduction_hours"], r["deduction_days"], r["freeze_months"],
            _xlsx_safe(r["comment"]), _xlsx_safe(r["submitted_by"]), r["created_at"],
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"violations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
