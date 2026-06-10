import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..auth import (
    ROLE_DEPT_HEAD,
    ROLE_HR_MANAGER,
    ROLE_HR_OFFICER,
    CurrentUser,
    require_role,
)
from ..db import db
from ..schemas import Employee, EmployeeIn

logger = logging.getLogger("hr.employees")

router = APIRouter(prefix="/employees", tags=["employees"])

_hr_staff = require_role(ROLE_HR_MANAGER, ROLE_HR_OFFICER)


@router.get("", response_model=list[Employee])
def list_employees(user: CurrentUser = Depends(require_role(ROLE_HR_MANAGER, ROLE_HR_OFFICER, ROLE_DEPT_HEAD))):
    with db() as conn:
        if user.role == ROLE_DEPT_HEAD:
            rows = conn.execute(
                "SELECT * FROM employees WHERE department = ? ORDER BY name", (user.department,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM employees ORDER BY name").fetchall()
        return [dict(r) for r in rows]


@router.post("", response_model=Employee, status_code=201)
def create_employee(payload: EmployeeIn, _: CurrentUser = Depends(_hr_staff)):
    with db() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO employees (name, email, department, manager_email)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                       email = excluded.email,
                       department = excluded.department,
                       manager_email = excluded.manager_email
                   RETURNING *""",
                (payload.name, payload.email, payload.department, payload.manager_email),
            )
            row = cur.fetchone()
            return dict(row)
        except sqlite3.Error:
            # don't echo raw sqlite errors (schema/file details) to the client
            logger.exception("Failed to save employee %r", payload.name)
            raise HTTPException(400, "Could not save employee")


@router.delete("/{name}", status_code=204)
def delete_employee(name: str, _: CurrentUser = Depends(require_role(ROLE_HR_MANAGER))):
    with db() as conn:
        conn.execute("DELETE FROM employees WHERE name = ?", (name,))
