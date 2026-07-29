import base64
import binascii
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

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
    # Ignored: submitted_by is derived server-side from the session user.
    submitted_by: str = Field("", max_length=120)
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


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)
    remember_me: bool = False


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(..., min_length=20, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=200)


class UserIn(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=120)
    role: str = Field(..., pattern="^(hr_manager|hr_officer|dept_head|employee)$")
    department: str = Field("", max_length=120)
    password: str = Field(..., min_length=8, max_length=200)


class UserUpdateIn(BaseModel):
    # Both optional: update whichever fields are supplied (at least one required,
    # enforced in the route). role is validated against the same allow-list as UserIn.
    role: Optional[str] = Field(None, pattern="^(hr_manager|hr_officer|dept_head|employee)$")
    department: Optional[str] = Field(None, max_length=120)


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    department: str
    is_active: int = 1


# Attachments a manager may open inline; keep the allowlist tight.
ALLOWED_ATTACHMENT_MIME = {"image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"}


def _real_date(v: str) -> str:
    """Reject calendar-invalid dates (e.g. 2026-02-31, 2026-99-99) that a
    format-only check would accept — the value must be a real day, YYYY-MM-DD."""
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValueError("must be a real date formatted YYYY-MM-DD")
    return v


class PermissionIn(BaseModel):
    employee_name: str = Field(..., min_length=1, max_length=120)
    permission_date: str = Field(..., min_length=10, max_length=10)
    note: str = Field("", max_length=500)
    attachment: str = Field("", max_length=MAX_PROOF_B64_CHARS)
    attachment_name: str = Field("", max_length=200)
    attachment_mime: str = Field("", max_length=100)

    @field_validator("permission_date")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        return _real_date(v)

    @field_validator("attachment")
    @classmethod
    def _valid_b64(cls, v: str) -> str:
        if not v:
            return v
        try:
            base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("attachment must be valid base64")
        return v

    @field_validator("attachment_mime")
    @classmethod
    def _valid_mime(cls, v: str) -> str:
        if v and v not in ALLOWED_ATTACHMENT_MIME:
            raise ValueError("unsupported attachment type")
        return v


# Expiry-tracked documents. Every category shares one shape: a start/end date,
# an optional attachment, and a title/owner. See routers/documents.py.
DOCUMENT_CATEGORIES = {"iqama", "contract", "rent", "vehicle", "license"}


class DocumentIn(BaseModel):
    category: str = Field(..., min_length=1, max_length=30)
    owner: str = Field("", max_length=120)
    title: str = Field("", max_length=200)
    start_date: str = Field(..., min_length=10, max_length=10)
    end_date: str = Field(..., min_length=10, max_length=10)
    note: str = Field("", max_length=500)
    attachment: str = Field("", max_length=MAX_PROOF_B64_CHARS)
    attachment_name: str = Field("", max_length=200)
    attachment_mime: str = Field("", max_length=100)

    @field_validator("category")
    @classmethod
    def _valid_category(cls, v: str) -> str:
        if v not in DOCUMENT_CATEGORIES:
            raise ValueError("unsupported document category")
        return v

    @field_validator("owner", "title")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("start_date", "end_date")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        return _real_date(v)

    @field_validator("attachment")
    @classmethod
    def _valid_b64(cls, v: str) -> str:
        if not v:
            return v
        try:
            base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("attachment must be valid base64")
        return v

    @field_validator("attachment_mime")
    @classmethod
    def _valid_mime(cls, v: str) -> str:
        if v and v not in ALLOWED_ATTACHMENT_MIME:
            raise ValueError("unsupported attachment type")
        return v

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class DocumentUpdateIn(BaseModel):
    """Partial update for a renewal or a correction: change owner/title/dates/note
    and optionally swap the attachment. Every field is optional; only the supplied
    ones are applied. An empty-string attachment clears the existing one.
    `category` is not editable — a record stays in the list it was filed under."""
    owner: Optional[str] = Field(None, max_length=120)
    title: Optional[str] = Field(None, max_length=200)
    start_date: Optional[str] = Field(None, min_length=10, max_length=10)
    end_date: Optional[str] = Field(None, min_length=10, max_length=10)
    note: Optional[str] = Field(None, max_length=500)
    attachment: Optional[str] = Field(None, max_length=MAX_PROOF_B64_CHARS)
    attachment_name: Optional[str] = Field(None, max_length=200)
    attachment_mime: Optional[str] = Field(None, max_length=100)

    @field_validator("owner", "title")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v is not None else v

    @field_validator("start_date", "end_date")
    @classmethod
    def _valid_date(cls, v: Optional[str]) -> Optional[str]:
        return _real_date(v) if v is not None else v

    @field_validator("attachment")
    @classmethod
    def _valid_b64(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        try:
            base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("attachment must be valid base64")
        return v

    @field_validator("attachment_mime")
    @classmethod
    def _valid_mime(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in ALLOWED_ATTACHMENT_MIME:
            raise ValueError("unsupported attachment type")
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
