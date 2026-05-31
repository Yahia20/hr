from sqlalchemy.orm import Session
from ..models.employee import Employee
from ..schemas.employee import EmployeeCreate, EmployeeUpdate


def create_employee(db: Session, emp: EmployeeCreate):
    db_emp = Employee(**emp.dict())
    db.add(db_emp)
    db.commit()
    db.refresh(db_emp)
    return db_emp


def get_employees(db: Session):
    return db.query(Employee).all()


def get_employee_by_id(db: Session, emp_id: int):
    return db.query(Employee).filter(Employee.id == emp_id).first()


def update_employee(db: Session, emp_id: int, data: EmployeeUpdate):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        return None
    for field, val in data.dict(exclude_unset=True).items():
        setattr(emp, field, val)
    db.commit()
    db.refresh(emp)
    return emp


def delete_employee_by_id(db: Session, emp_id: int) -> bool:
    deleted = db.query(Employee).filter(Employee.id == emp_id).delete()
    db.commit()
    return deleted > 0


def delete_employee(db: Session, name: str):
    deleted = db.query(Employee).filter(Employee.name == name).delete()
    db.commit()
    return deleted
