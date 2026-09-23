import csv
import io
from typing import Iterator

from sqlalchemy.orm import Session

from app.config.config import AUDIT_EXPORT_MAX_ROWS
from app.entity.audit_log_entity import AuditLog
from app.enum.audit_enum import AuditCategory, AuditModule, AuditStatus
from app.exception import NotFoundException
from app.model.access_token import AccessToken
from app.model.audit_model import AuditLogFilter
from app.repository.audit_log_repository import audit_log_repository
from app.utils.formatters import (as_utc_iso, format_audit_detail, format_audit_number, format_audit_summary)
from app.utils.hashing import compute_record_hash

CSV_COLUMNS = (
    "Audit ID", "Date & Time (UTC)", "Employee", "Employee ID", "Module", "Category", "Action",
    "Performed By", "User Role", "Description", "Previous Value", "New Value", "Reason", "Remarks",
    "Reference Type", "Reference ID", "Request ID", "Status", "IP Address", "User Agent",
)


def _csv_safe(value) -> str:
    """Neutralise spreadsheet formula injection (=, +, -, @ at the start of a cell)."""
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


class AuditQueryService:

    @classmethod
    def list_logs(cls, db: Session, token: AccessToken, filters: AuditLogFilter, page: int, limit: int) -> dict:
        query = audit_log_repository.filtered_query(db, token.client_id, filters)
        total = query.count()
        total_pages = max((total + limit - 1) // limit, 1)
        page = min(max(page, 1), total_pages)
        rows = (query.order_by(AuditLog.occurred_at.desc(), AuditLog.audit_number.desc())
                .offset((page - 1) * limit)
                .limit(limit)
                .all())
        return {
            "result": [format_audit_summary(row) for row in rows],
            "pagination": {
                "total_items": total,
                "total_pages": total_pages,
                "current_page": page,
                "page_size": limit,
            },
        }

    @classmethod
    def get_detail(cls, db: Session, token: AccessToken, audit_ref: str) -> dict:
        record = audit_log_repository.get_by_audit_ref(db, token.client_id, audit_ref)
        if record is None:
            raise NotFoundException(f"Audit record {audit_ref} was not found")
        related = audit_log_repository.get_related(db, token.client_id, record)
        return format_audit_detail(record, related)

    @classmethod
    def get_record(cls, db: Session, token: AccessToken, audit_ref: str) -> AuditLog:
        record = audit_log_repository.get_by_audit_ref(db, token.client_id, audit_ref)
        if record is None:
            raise NotFoundException(f"Audit record {audit_ref} was not found")
        return record

    @classmethod
    def filter_options(cls, db: Session, token: AccessToken) -> dict:
        client_id = token.client_id
        actions_by_module: dict[str, list[str]] = {}
        for module, action in audit_log_repository.module_actions(db, client_id):
            actions_by_module.setdefault(module, []).append(action)

        recorded_roles = audit_log_repository.distinct_values(db, client_id, AuditLog.performed_by_role)
        return {
            # Every module/category is offered, not only ones already recorded,
            # so a filter can be set before the first event of that kind exists.
            "modules": [m.value for m in AuditModule],
            "categories": [c.value for c in AuditCategory],
            "statuses": [s.value for s in AuditStatus],
            "actions": sorted({a for actions in actions_by_module.values() for a in actions}),
            "actions_by_module": actions_by_module,
            "performer_roles": recorded_roles,
            "performers": [
                {"email": email, "name": name or email, "role": role}
                for email, name, role in audit_log_repository.performers(db, client_id)
            ],
            "employees": [
                {"employee_id": employee_id, "employee_name": name, "employee_code": code}
                for employee_id, name, code in audit_log_repository.employees(db, client_id)
            ],
        }

    @classmethod
    def export_csv(cls, db: Session, token: AccessToken, filters: AuditLogFilter) -> Iterator[str]:
        query = (audit_log_repository.filtered_query(db, token.client_id, filters)
                 .order_by(AuditLog.occurred_at.desc(), AuditLog.audit_number.desc())
                 .limit(AUDIT_EXPORT_MAX_ROWS))

        buffer = io.StringIO()
        writer = csv.writer(buffer)

        def flush() -> str:
            value = buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
            return value

        # UTF-8 BOM so Excel opens names with non-ASCII characters correctly.
        writer.writerow(CSV_COLUMNS)
        yield "﻿" + flush()

        for record in query.yield_per(500):
            previous = "; ".join(f"{c.field_label}: {c.old_value if c.old_value is not None else '-'}"
                                 for c in record.changes)
            new = "; ".join(f"{c.field_label}: {c.new_value if c.new_value is not None else '-'}"
                            for c in record.changes)
            writer.writerow([_csv_safe(value) for value in (
                format_audit_number(record.audit_number), as_utc_iso(record.occurred_at),
                record.employee_name, record.employee_code, record.module, record.category, record.action,
                record.performed_by_name, record.performed_by_role, record.description, previous, new,
                record.reason, record.remarks, record.reference_type, record.reference_id, record.request_id,
                record.status, record.ip_address, record.user_agent,
            )])
            yield flush()

    @classmethod
    def verify_integrity(cls, db: Session, token: AccessToken) -> dict:
        """Recompute the tenant's hash chain and report the first broken link."""
        expected_prev = None
        expected_number = 1
        checked = 0
        for record in audit_log_repository.iter_chain(db, token.client_id):
            problem = None
            if record.audit_number != expected_number:
                problem = f"missing record(s) before {format_audit_number(record.audit_number)}"
            elif record.prev_hash != expected_prev:
                problem = "chain link does not match the previous record"
            elif compute_record_hash(record, record.changes) != record.record_hash:
                problem = "record content was modified after it was written"
            if problem:
                return {
                    "is_valid": False,
                    "records_checked": checked,
                    "first_invalid_audit_id": format_audit_number(record.audit_number),
                    "problem": problem,
                }
            expected_prev = record.record_hash
            expected_number = record.audit_number + 1
            checked += 1

        head = audit_log_repository.chain_head(db, token.client_id)
        if head is not None and (head.last_number or 0) != checked:
            return {
                "is_valid": False,
                "records_checked": checked,
                "first_invalid_audit_id": format_audit_number(checked + 1),
                "problem": "records at the end of the chain are missing",
            }
        return {"is_valid": True, "records_checked": checked, "first_invalid_audit_id": None, "problem": None}


audit_query_service = AuditQueryService()
