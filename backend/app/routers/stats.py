from collections import Counter

from fastapi import APIRouter, Depends

from ..auth import ROLE_HR_MANAGER, ROLE_HR_OFFICER, CurrentUser, require_role
from ..db import db

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/dashboard")
def dashboard(_: CurrentUser = Depends(require_role(ROLE_HR_MANAGER, ROLE_HR_OFFICER))):
    with db() as conn:
        total_v = conn.execute("SELECT COUNT(*) FROM violations").fetchone()[0]
        total_e = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        total_d = conn.execute("SELECT COALESCE(SUM(deduction_days), 0) FROM violations").fetchone()[0]
        # Count distinct employees currently frozen, not the number of freeze
        # penalties — two active freezes on one person is still one frozen employee.
        active_freezes = conn.execute(
            """SELECT COUNT(DISTINCT employee_name) FROM violations
               WHERE freeze_months > 0
                 AND datetime(created_at, '+' || freeze_months || ' months') > datetime('now')"""
        ).fetchone()[0]

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
                """SELECT strftime('%Y-%m', created_at) AS month, COUNT(*) AS count
                   FROM violations GROUP BY month ORDER BY month"""
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
