import base64
import binascii
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

# 5 MB of raw image data, as base64 (4/3 expansion + padding slack).
MAX_PROOF_B64_CHARS = 7_200_000


class EmployeeIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    department: str = Field("", max_length=120)
    manager_email: str = Field("", max_length=254)

    @field_validator("name", "department")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("manager_email")
    @classmethod
    def _manager_email_valid(cls, v: str) -> str:
        v = v.strip()
        if v and ("@" not in v or " " in v):
            raise ValueError("manager_email must be a valid email address")
        return v


class Employee(EmployeeIn):
    id: int


class ViolationIn(BaseModel):
    employee_name: str = Field(..., min_length=1, max_length=120)
    category: str = Field(..., min_length=1, max_length=120)
    incident: str = Field(..., min_length=1, max_length=120)
    submitted_by: str = Field(..., min_length=1, max_length=120)
    comment: str = Field("", max_length=2000)
    proof_image: str = Field("", max_length=MAX_PROOF_B64_CHARS)
    force_investigation: bool = False
    override_days: Optional[float] = Field(None, ge=0, le=365)

    @field_validator("proof_image")
    @classmethod
    def _valid_base64(cls, v: str) -> str:
        if not v:
            return v
        try:
            base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("proof_image must be valid base64")
        return v


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
