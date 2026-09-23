import json
from datetime import datetime, timezone
from typing import Any, Optional

from app.entity.audit_log_entity import AuditLog, AuditLogChange


def format_audit_number(number: Optional[int]) -> Optional[str]:
    return None if number is None else f"AUD-{int(number):06d}"


def as_utc_iso(value: Optional[datetime]) -> Optional[str]:
    """Stored timestamps are naive UTC; tag them so browsers don't read them as local time."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def load_details(record: AuditLog) -> dict:
    if not record.details:
        return {}
    try:
        value = json.loads(record.details)
        return value if isinstance(value, dict) else {"value": value}
    except (TypeError, ValueError):
        return {}


def format_change(change: AuditLogChange) -> dict:
    return {
        "field_key": change.field_key,
        "field_label": change.field_label,
        "old_value": change.old_value,
        "new_value": change.new_value,
        "value_type": change.value_type,
    }


def format_audit_summary(record: AuditLog) -> dict:
    """Row shape for the audit log table."""
    return {
        "id": record.id,
        "audit_id": format_audit_number(record.audit_number),
        "occurred_at": as_utc_iso(record.occurred_at),
        "module": record.module,
        "category": record.category,
        "action": record.action,
        "event_type": record.event_type,
        "description": record.description,
        "status": record.status,
        "employee_id": record.employee_id,
        "employee_code": record.employee_code,
        "employee_name": record.employee_name,
        "performed_by_name": record.performed_by_name,
        "performed_by_email": record.performed_by_email,
        "performed_by_role": record.performed_by_role,
        "reference_type": record.reference_type,
        "reference_id": record.reference_id,
        "request_id": record.request_id,
        "has_changes": bool(record.changes),
    }


def format_audit_detail(record: AuditLog, related: Optional[list] = None) -> dict:
    data: dict[str, Any] = format_audit_summary(record)
    data.update({
        "tenant_id": record.tenant_id,
        "correlation_id": record.correlation_id,
        "performed_by_user_id": record.performed_by_user_id,
        "performed_by_employee_id": record.performed_by_employee_id,
        "performed_by_system_role": record.performed_by_system_role,
        "reason": record.reason,
        "remarks": record.remarks,
        "effective_date": record.effective_date.isoformat() if record.effective_date else None,
        "payroll_period": record.payroll_period,
        "details": load_details(record),
        "ip_address": record.ip_address,
        "user_agent": record.user_agent,
        "http_method": record.http_method,
        "endpoint": record.endpoint,
        "source_service": record.source_service,
        "record_hash": record.record_hash,
        "changes": [format_change(change) for change in record.changes],
        "related": [format_audit_summary(item) for item in (related or [])],
    })
    return data
