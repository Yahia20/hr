import base64
import binascii
import ipaddress
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


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    department: str
    is_active: int = 1


import re

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Attachments a manager may open inline; keep the allowlist tight.
ALLOWED_ATTACHMENT_MIME = {"image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"}


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
        if not _DATE_RE.match(v):
            raise ValueError("permission_date must be formatted YYYY-MM-DD")
        return v

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


class OfficeIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    radius_m: int = Field(150, ge=20, le=5000)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return v.strip()


class Office(OfficeIn):
    id: int


class OfficeNetworkIn(BaseModel):
    label: str = Field("", max_length=120)
    # An IP (203.0.113.7) or CIDR range (203.0.113.0/24); a bare IP is stored as
    # a /32 (or /128). Normalised to canonical form on the way in.
    cidr: str = Field(..., min_length=1, max_length=64)

    @field_validator("label")
    @classmethod
    def _strip_label(cls, v: str) -> str:
        return v.strip()

    @field_validator("cidr")
    @classmethod
    def _valid_cidr(cls, v: str) -> str:
        try:
            return str(ipaddress.ip_network(v.strip(), strict=False))
        except ValueError:
            raise ValueError("cidr must be a valid IP or CIDR, e.g. 203.0.113.7 or 203.0.113.0/24")


class OfficeNetwork(BaseModel):
    id: int
    label: str
    cidr: str


class ClockActionIn(BaseModel):
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    accuracy: Optional[float] = Field(None, ge=0)
    # WebAuthn assertion (navigator.credentials.get result, JSON-encoded by the
    # client). Required when biometric verification is enabled.
    assertion: Optional[dict] = None


class WebAuthnRegisterIn(BaseModel):
    credential: dict
    device_label: str = Field("", max_length=120)


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
