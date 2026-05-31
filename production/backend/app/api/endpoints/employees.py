from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...db.session import get_db
from ...schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeResponse
from ...crud.employee import (
    create_employee, get_employees, get_employee_by_id,
    update_employee, delete_employee_by_id,
)
from ...api.deps import get_current_user
from ...models.violation import Violation

router = APIRouter()


@router.get("/", response_model=list[EmployeeResponse])
def api_get_employees(db: Session = Depends(get_db), _: dict = Depends(get_current_user)):
    return get_employees(db)


@router.post("/", response_model=EmployeeResponse)
def api_create_employee(
    emp: EmployeeCreate,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    return create_employee(db, emp)


@router.put("/{emp_id}", response_model=EmployeeResponse)
def api_update_employee(
    emp_id: int,
    emp: EmployeeUpdate,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    updated = update_employee(db, emp_id, emp)
    if not updated:
        raise HTTPException(status_code=404, detail="Employee not found")
    return updated


@router.delete("/{emp_id}")
def api_delete_employee(
    emp_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    if not delete_employee_by_id(db, emp_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"message": "Employee deleted"}


@router.get("/{emp_id}/violations")
def api_get_employee_violations(
    emp_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    emp = get_employee_by_id(db, emp_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    violations = (
        db.query(Violation)
        .filter(Violation.employee_name == emp.name)
        .order_by(Violation.created_at.desc())
        .all()
    )
    return {
        "employee": {
            "id": emp.id,
            "name": emp.name,
            "email": emp.email,
            "department": emp.department,
            "manager_email": emp.manager_email,
        },
        "violations": [
            {
                "id": v.id,
                "incident": v.incident,
                "category": v.category,
                "penalty_color": v.penalty_color,
                "penalty_label": v.penalty_label,
                "deduction_days": v.deduction_days,
                "freeze_months": v.freeze_months,
                "comment": v.comment,
                "proof_image": v.proof_image,
                "submitted_by": v.submitted_by,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in violations
        ],
    }
