"""Tamper-evidence for audit records.

Each record's hash covers every stored business field plus the previous
record's hash of the same tenant. Changing, deleting or reordering any row
therefore breaks verification from that row onwards.

Everything hashed must round-trip through the database unchanged, which is why
timestamps are truncated to whole seconds (MySQL DATETIME has no fractional
part by default) and details are hashed as the exact JSON text that is stored.
"""
import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def to_utc_naive_seconds(value: datetime) -> datetime:
    """Normalise to naive UTC with no microseconds - the form stored in MySQL."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0)


def _iso(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def compute_record_hash(record: Any, changes: Iterable[Any]) -> str:
    """Hash an AuditLog-like object (entity or namespace) and its change rows."""
    payload = {
        "client_id": record.client_id,
        "tenant_id": record.tenant_id,
        "audit_number": int(record.audit_number),
        "event_uuid": record.event_uuid,
        "correlation_id": record.correlation_id,
        "occurred_at": _iso(record.occurred_at),
        "module": record.module,
        "category": record.category,
        "action": record.action,
        "event_type": record.event_type,
        "description": record.description,
        "status": record.status,
        "performed_by_user_id": record.performed_by_user_id,
        "performed_by_employee_id": record.performed_by_employee_id,
        "performed_by_name": record.performed_by_name,
        "performed_by_email": record.performed_by_email,
        "performed_by_role": record.performed_by_role,
        "performed_by_system_role": record.performed_by_system_role,
        "employee_id": record.employee_id,
        "employee_code": record.employee_code,
        "employee_name": record.employee_name,
        "reason": record.reason,
        "remarks": record.remarks,
        "reference_type": record.reference_type,
        "reference_id": record.reference_id,
        "request_id": record.request_id,
        "effective_date": _iso(record.effective_date),
        "payroll_period": record.payroll_period,
        "details": record.details,
        "ip_address": record.ip_address,
        "user_agent": record.user_agent,
        "http_method": record.http_method,
        "endpoint": record.endpoint,
        "source_service": record.source_service,
        "changes": [
            [c.field_key, c.field_label, c.old_value, c.new_value, c.value_type, int(c.sort_order)]
            for c in sorted(changes, key=lambda c: int(c.sort_order))
        ],
        "prev_hash": record.prev_hash,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    """Current time as naive UTC seconds (the stored form)."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
