from typing import Optional
from pydantic import BaseModel, Field


class EmployeeIn(BaseModel):
    name: str = Field(..., min_length=1)
    email: str
    department: str = ""
    manager_email: str = ""


class Employee(EmployeeIn):
    id: int


class ViolationIn(BaseModel):
    employee_name: str
    category: str
    incident: str
    submitted_by: str = Field(..., min_length=1)
    comment: str = ""
    proof_image: str = ""
    force_investigation: bool = False
    override_days: Optional[float] = None


class Violation(BaseModel):
    id: int
    employee_name: str
    category: str
    incident: str
    penalty_color: str
    penalty_label: str
    deduction_hours: float
    deduction_days: float
    freeze_months: int
    comment: str
    submitted_by: str
    # proof_image is intentionally NOT returned in list responses — base64 blobs
    # bloat payloads (~600 KB each). Use GET /violations/{id}/proof to fetch one.
    has_proof: bool = False
    created_at: str
