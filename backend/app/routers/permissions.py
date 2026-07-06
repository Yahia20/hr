import logging
import os
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import (
    ROLE_HR_MANAGER,
    ROLE_HR_OFFICER,
    CurrentUser,
    require_role,
)
from ..db import db
from ..schemas import PermissionIn

logger = logging.getLogger("hr.permissions")

router = APIRouter(prefix="/permissions", tags=["permissions"])

_hr_staff = require_role(ROLE_HR_MANAGER, ROLE_HR_OFFICER)
_manager = require_role(ROLE_HR_MANAGER)

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

# Early-leave permissions each employee may take per calendar month.
MONTHLY_QUOTA = int(os.environ.get("PERMISSION_MONTHLY_QUOTA", "2"))


def _now() -> datetime:
    return datetime.now()


def _current_month() -> str:
    return _now().strftime("%Y-%m")


def _public(row: dict) -> dict:
    """A permission record without the heavy/private attachment bytes."""
    return {
        "id": row["id"],
        "employee_name": row["employee_name"],
        "permission_date": row["permission_date"],
        "note": row["note"],
        "has_attachment": bool(row["attachment"]),
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }


@router.get("")
def list_permissions(
    month: Optional[str] = Query(None),
    _: CurrentUser = Depends(_hr_staff),
):
    """Per-employee permission usage for a month: every employee on the roster
    with the permissions they've taken and how many remain."""
    month = month or _current_month()
    if not _MONTH_RE.match(month):
        raise HTTPException(400, "month must be formatted YYYY-MM")

    with db() as conn:
        employees = conn.execute(
            "SELECT name, department FROM employees ORDER BY name"
        ).fetchall()
        rows = conn.execute(
            "SELECT * FROM permissions WHERE month_key = ? ORDER BY permission_date DESC, id DESC",
            (month,),
        ).fetchall()

    by_emp: dict[str, list] = {}
    for r in rows:
        by_emp.setdefault(r["employee_name"], []).append(_public(dict(r)))

    result = []
    for e in employees:
        used = by_emp.get(e["name"], [])
        result.append({
            "employee_name": e["name"],
            "department": e["department"],
            "used": len(used),
            "remaining": max(MONTHLY_QUOTA - len(used), 0),
            "permissions": used,
        })
    return {"month": month, "quota": MONTHLY_QUOTA, "employees": result}


@router.post("", status_code=201)
def create_permission(payload: PermissionIn, user: CurrentUser = Depends(_hr_staff)):
    month_key = payload.permission_date[:7]
    with db() as conn:
        emp = conn.execute(
            "SELECT 1 FROM employees WHERE name = ?", (payload.employee_name,)
        ).fetchone()
        if emp is None:
            raise HTTPException(400, "unknown_employee")
        used = conn.execute(
            "SELECT COUNT(*) FROM permissions WHERE employee_name = ? AND month_key = ?",
            (payload.employee_name, month_key),
        ).fetchone()[0]
        if used >= MONTHLY_QUOTA:
            raise HTTPException(409, "quota_exceeded")
        cur = conn.execute(
            """INSERT INTO permissions
               (employee_name, permission_date, month_key, note,
                attachment, attachment_name, attachment_mime, created_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *""",
            (
                payload.employee_name, payload.permission_date, month_key, payload.note,
                payload.attachment, payload.attachment_name, payload.attachment_mime,
                user.name, _now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        return _public(dict(cur.fetchone()))


@router.delete("/{pid}", status_code=204)
def delete_permission(pid: int, _: CurrentUser = Depends(_manager)):
    with db() as conn:
        conn.execute("DELETE FROM permissions WHERE id = ?", (pid,))


@router.get("/{pid}/attachment")
def get_attachment(pid: int, _: CurrentUser = Depends(_manager)):
    """Fetch a permission's attachment (base64). HR Manager only — this is the
    "system administrator" gate the attachments must stay behind."""
    with db() as conn:
        row = conn.execute(
            "SELECT attachment, attachment_name, attachment_mime FROM permissions WHERE id = ?",
            (pid,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Permission not found")
    if not row["attachment"]:
        raise HTTPException(404, "No attachment")
    return {
        "id": pid,
        "attachment": row["attachment"],
        "attachment_name": row["attachment_name"],
        "attachment_mime": row["attachment_mime"] or "application/octet-stream",
    }
