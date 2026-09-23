from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.enum.audit_enum import AuditCategory, AuditModule, AuditStatus, ChangeValueType

_MODULES = {m.value for m in AuditModule}
_CATEGORIES = {c.value for c in AuditCategory}


def _clip(value: Optional[str], limit: int) -> Optional[str]:
    if value is None:
        return None
    value = str(value)
    return value if len(value) <= limit else value[: limit - 1] + "…"


class AuditChangeIn(BaseModel):
    field_key: str = Field(..., max_length=100)
    field_label: str = Field(..., max_length=150)
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    value_type: ChangeValueType = ChangeValueType.TEXT

    @field_validator("old_value", "new_value", mode="before")
    @classmethod
    def _stringify(cls, value):
        if value is None or isinstance(value, str):
            return value
        return str(value)


class AuditActor(BaseModel):
    user_id: Optional[str] = None
    employee_id: Optional[int] = None
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    system_role: Optional[str] = None


class AuditSubject(BaseModel):
    employee_id: Optional[int] = None
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None


class AuditEventIn(BaseModel):
    """One event as sent by the orchestrator (or another trusted service)."""
    event_uuid: str = Field(..., min_length=8, max_length=36)
    correlation_id: Optional[str] = Field(None, max_length=64)
    client_id: str = Field(..., min_length=1, max_length=64)
    tenant_id: Optional[str] = Field(None, max_length=64)
    occurred_at: datetime

    module: str
    category: str
    action: str = Field(..., min_length=1, max_length=100)
    event_type: str = Field(..., min_length=1, max_length=60)
    description: Optional[str] = None
    status: AuditStatus = AuditStatus.SUCCESS

    actor: AuditActor = Field(default_factory=AuditActor)
    subject: AuditSubject = Field(default_factory=AuditSubject)

    reason: Optional[str] = None
    remarks: Optional[str] = None
    reference_type: Optional[str] = Field(None, max_length=100)
    reference_id: Optional[str] = Field(None, max_length=100)
    request_id: Optional[str] = Field(None, max_length=100)
    effective_date: Optional[date] = None
    payroll_period: Optional[str] = Field(None, max_length=20)

    changes: List[AuditChangeIn] = Field(default_factory=list, max_length=200)
    details: Dict[str, Any] = Field(default_factory=dict)

    ip_address: Optional[str] = Field(None, max_length=64)
    user_agent: Optional[str] = None
    http_method: Optional[str] = Field(None, max_length=10)
    endpoint: Optional[str] = None
    source_service: Optional[str] = Field(None, max_length=60)

    @field_validator("module")
    @classmethod
    def _known_module(cls, value: str) -> str:
        if value not in _MODULES:
            raise ValueError(f"Unknown audit module '{value}'")
        return value

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        if value not in _CATEGORIES:
            raise ValueError(f"Unknown audit category '{value}'")
        return value

    @field_validator("description")
    @classmethod
    def _clip_description(cls, value):
        return _clip(value, 500)

    @field_validator("user_agent")
    @classmethod
    def _clip_user_agent(cls, value):
        return _clip(value, 512)

    @field_validator("endpoint")
    @classmethod
    def _clip_endpoint(cls, value):
        return _clip(value, 255)


class AuditEventBatchIn(BaseModel):
    events: List[AuditEventIn] = Field(..., min_length=1, max_length=500)


class AuditLogFilter(BaseModel):
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    employee_id: Optional[int] = None
    performed_by: Optional[str] = None       # performer email
    performed_by_role: Optional[str] = None  # display role ("HR Manager", "Super Admin")
    module: Optional[str] = None
    category: Optional[str] = None
    action: Optional[str] = None
    status: Optional[str] = None
    request_id: Optional[str] = None
    reference_id: Optional[str] = None
    search: Optional[str] = None
