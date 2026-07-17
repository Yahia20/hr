from datetime import datetime

from fastapi import APIRouter, Depends

from ..auth import ROLE_HR_MANAGER, ROLE_HR_OFFICER, CurrentUser, require_role
from ..db import db

router = APIRouter(prefix="/stats", tags=["stats"])


def _add_months(dt: datetime, months: int) -> datetime:
    """dt + N months, clamping the day to the target month's length (e.g.
    Jan 31 + 1 month → Feb 28). Computed in Python so freeze-expiry works the
    same on SQLite and PostgreSQL (no backend-specific date arithmetic in SQL)."""
    m = dt.month - 1 + months
    year, month = dt.year + m // 12, m % 12 + 1
    for day in (dt.day, 31, 30, 29, 28):
        try:
            return dt.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    return dt.replace(year=year, month=month, day=1)


@router.get("/dashboard")
def dashboard(_: CurrentUser = Depends(require_role(ROLE_HR_MANAGER, ROLE_HR_OFFICER))):
    with db() as conn:
        total_v = conn.execute("SELECT COUNT(*) FROM violations").fetchone()[0]
        total_e = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        total_d = conn.execute("SELECT COALESCE(SUM(deduction_days), 0) FROM violations").fetchone()[0]
        # Count distinct employees currently frozen, not the number of freeze
        # penalties — two active freezes on one person is still one frozen
        # employee. The "still active?" check is done in Python so it doesn't
        # depend on backend-specific SQL date arithmetic.
        frozen = conn.execute(
            "SELECT employee_name, created_at, freeze_months FROM violations WHERE freeze_months > 0"
        ).fetchall()
        now_dt = datetime.now()
        frozen_employees = set()
        for r in frozen:
            try:
                started = datetime.strptime(r["created_at"][:19], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                continue
            if _add_months(started, int(r["freeze_months"])) > now_dt:
                frozen_employees.add(r["employee_name"])
        active_freezes = len(frozen_employees)

        by_color = dict(conn.execute(
            "SELECT penalty_color, COUNT(*) FROM violations GROUP BY penalty_color"
        ).fetchall())

        by_category = dict(conn.execute(
            "SELECT category, COUNT(*) FROM violations GROUP BY category"
        ).fetchall())

        top_incidents = [
            dict(row) for row in conn.execute(
                """SELECT incident, COUNT(*) AS count FROM violations
                   GROUP BY incident ORDER BY count DESC LIMIT 5"""
            ).fetchall()
        ]

        monthly = [
            dict(row) for row in conn.execute(
                """SELECT substr(created_at, 1, 7) AS month, COUNT(*) AS count
                   FROM violations GROUP BY substr(created_at, 1, 7) ORDER BY month"""
            ).fetchall()
        ]

        recent = [
            dict(row) for row in conn.execute(
                """SELECT id, employee_name, category, incident, penalty_color,
                          penalty_label, deduction_hours, deduction_days,
                          freeze_months, comment, submitted_by, created_at,
                          (proof_image != '') AS has_proof
                   FROM violations ORDER BY created_at DESC LIMIT 5"""
            ).fetchall()
        ]

    return {
        "totals": {
            "violations": total_v,
            "employees": total_e,
            "deduction_days": float(total_d or 0),
            "active_freezes": active_freezes,
        },
        "by_color": by_color,
        "by_category": by_category,
        "top_incidents": top_incidents,
        "monthly": monthly,
        "recent": recent,
    }
