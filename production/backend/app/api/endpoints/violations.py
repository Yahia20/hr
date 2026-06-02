from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from ...db.session import get_db
from ...schemas.violation import ViolationCreate, ViolationResponse
from ...crud.violation import create_violation
from ...crud.setting import get_all_settings
from ...utils.penalty import calculate_next_penalty, build_penalty_label, PENALTY_MAP
from ...utils.email import send_violation_email
from ...models.employee import Employee
from ...models.violation import Violation
from ...api.deps import get_current_user
from ...core.config import settings as app_settings

router = APIRouter()


@router.post("/", response_model=ViolationResponse)
def log_violation(
    v: ViolationCreate,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    penalty_color = (
        "Investigation"
        if v.force_investigation
        else calculate_next_penalty(db, v.employee_name, v.category, v.incident)
    )

    applied_days = (
        v.deduction_override
        if v.deduction_override >= 0
        else PENALTY_MAP[penalty_color]["deduction_days"]
    )

    violation_data = {
        "employee_name": v.employee_name,
        "category": v.category,
        "incident": v.incident,
        "penalty_color": penalty_color,
        "penalty_label": build_penalty_label(penalty_color, applied_days),
        "deduction_days": applied_days,
        "freeze_months": PENALTY_MAP[penalty_color]["freeze_months"],
        "comment": v.comment or "",
        "submitted_by": v.submitted_by,
        "proof_image": v.proof_image or "",
        "created_at": datetime.utcnow(),
    }

    created = create_violation(db, violation_data)

    emp = db.query(Employee).filter(Employee.name == v.employee_name).first()
    real_emp_email = emp.email if emp else ""
    real_manager_email = emp.manager_email if emp else ""

    db_settings = get_all_settings(db)
    should_notify = db_settings.get("notify_violation", "true") == "true"

    if should_notify:
        smtp_config = {
            "server": db_settings.get("smtp_server") or app_settings.SMTP_SERVER,
            "port": db_settings.get("smtp_port") or str(app_settings.SMTP_PORT),
            "user": db_settings.get("smtp_user") or app_settings.SMTP_USER,
            "password": db_settings.get("smtp_password") or app_settings.SMTP_PASSWORD,
        }
        send_violation_email(
            emp_email=real_emp_email,
            manager_email=real_manager_email,
            emp_name=v.employee_name,
            category=v.category,
            incident=v.incident,
            penalty_color=penalty_color,
            comment=v.comment or "",
            applied_days=applied_days,
            proof_b64=v.proof_image,
            smtp_config=smtp_config,
        )

    return created


@router.get("/")
def get_all_violations(
    employee_name: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    penalty_level: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    query = db.query(Violation)
    if employee_name:
        query = query.filter(Violation.employee_name == employee_name)
    if penalty_level:
        query = query.filter(Violation.penalty_color == penalty_level)
    if date_from:
        try:
            query = query.filter(Violation.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Violation.created_at <= datetime.fromisoformat(date_to))
        except ValueError:
            pass
    return query.order_by(Violation.created_at.desc()).all()
