from pydantic import BaseModel
from typing import Optional


class EmployeeCreate(BaseModel):
    name: str
    email: str
    department: Optional[str] = ""
    manager_email: Optional[str] = ""


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None
    manager_email: Optional[str] = None


class EmployeeResponse(BaseModel):
    id: int
    name: str
    email: str
    department: str
    manager_email: str

    class Config:
        from_attributes = True
