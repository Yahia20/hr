import io
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from ..db import db
from ..penalties import MATRIX_DATA, PENALTY_MAP
from ..schemas import Violation, ViolationIn

router = APIRouter(prefix="/violations", tags=["violations"])


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
):
    clauses = ["1=1"]
    params: list = []
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
def get_proof(vid: int):
    """Fetch a single violation's proof image (base64) on demand."""
    with db() as conn:
        row = conn.execute("SELECT proof_image FROM violations WHERE id = ?", (vid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Violation not found")
    return {"id": vid, "proof_image": row["proof_image"] or ""}


@router.post("", response_model=Violation, status_code=201)
def create_violation(payload: ViolationIn):
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
                payload.comment, payload.submitted_by, payload.proof_image,
                now,
            ),
        )
        row = dict(cur.fetchone())
    row["has_proof"] = bool(row.pop("proof_image", ""))
    return row


@router.delete("/{vid}", status_code=204)
def delete_violation(vid: int):
    with db() as conn:
        conn.execute("DELETE FROM violations WHERE id = ?", (vid,))


@router.get("/preview")
def preview_next(employee_name: str = Query(...), category: str = Query(...), incident: str = Query(...)):
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
):
    rows = list_violations(employee, date_from, date_to, incident, penalty)
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
            r["id"], r["employee_name"], r["category"], r["incident"],
            r["penalty_color"], r["penalty_label"],
            r["deduction_hours"], r["deduction_days"], r["freeze_months"],
            r["comment"], r["submitted_by"], r["created_at"],
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
