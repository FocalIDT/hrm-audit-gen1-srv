from collections import defaultdict
from typing import List

from sqlalchemy.orm import Session

from app.config.logging_config import get_logger
from app.entity.audit_log_entity import AuditLog, AuditLogChange
from app.model.audit_model import AuditEventIn
from app.repository.audit_log_repository import audit_log_repository
from app.utils.hashing import canonical_json, compute_record_hash, to_utc_naive_seconds, utc_now

logger = get_logger(class_name=__name__)


def _clean(value, limit: int = None):
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    return value[:limit] if limit else value


class AuditIngestService:

    @classmethod
    def _build_record(cls, event: AuditEventIn) -> tuple[AuditLog, list[AuditLogChange]]:
        actor, subject = event.actor, event.subject
        record = AuditLog(
            client_id=event.client_id.strip(),
            tenant_id=_clean(event.tenant_id, 64),
            event_uuid=event.event_uuid,
            correlation_id=_clean(event.correlation_id, 64),
            occurred_at=to_utc_naive_seconds(event.occurred_at),
            module=event.module,
            category=event.category,
            action=event.action.strip(),
            event_type=event.event_type.strip().upper(),
            description=_clean(event.description, 500),
            status=event.status.value,
            performed_by_user_id=_clean(actor.user_id, 64),
            performed_by_employee_id=actor.employee_id,
            performed_by_name=_clean(actor.name, 255),
            performed_by_email=_clean(actor.email, 255),
            performed_by_role=_clean(actor.role or actor.system_role, 150),
            performed_by_system_role=_clean(actor.system_role, 60),
            employee_id=subject.employee_id,
            employee_code=_clean(subject.employee_code, 50),
            employee_name=_clean(subject.employee_name, 255),
            reason=_clean(event.reason),
            remarks=_clean(event.remarks),
            reference_type=_clean(event.reference_type, 100),
            reference_id=_clean(event.reference_id, 100),
            request_id=_clean(event.request_id, 100),
            effective_date=event.effective_date,
            payroll_period=_clean(event.payroll_period, 20),
            details=canonical_json(event.details) if event.details else None,
            ip_address=_clean(event.ip_address, 64),
            user_agent=_clean(event.user_agent, 512),
            http_method=_clean(event.http_method, 10),
            endpoint=_clean(event.endpoint, 255),
            source_service=_clean(event.source_service, 60),
            created_at=utc_now(),
        )
        changes = [
            AuditLogChange(
                field_key=change.field_key,
                field_label=change.field_label,
                old_value=change.old_value,
                new_value=change.new_value,
                value_type=change.value_type.value,
                sort_order=index,
            )
            for index, change in enumerate(event.changes)
        ]
        return record, changes

    @classmethod
    def ingest(cls, db: Session, events: List[AuditEventIn]) -> dict:
        """Append events to their tenants' chains. Idempotent on event_uuid."""
        stored, duplicates = 0, 0
        seen = audit_log_repository.existing_event_uuids(db, [event.event_uuid for event in events])

        by_client: dict[str, list[AuditEventIn]] = defaultdict(list)
        for event in events:
            by_client[event.client_id.strip()].append(event)

        try:
            # Sorted so two concurrent multi-tenant batches lock heads in the same order.
            for client_id in sorted(by_client):
                head = audit_log_repository.lock_chain_head(db, client_id)
                for event in sorted(by_client[client_id], key=lambda e: to_utc_naive_seconds(e.occurred_at)):
                    if event.event_uuid in seen:
                        duplicates += 1
                        continue
                    seen.add(event.event_uuid)

                    record, changes = cls._build_record(event)
                    record.audit_number = int(head.last_number or 0) + 1
                    record.prev_hash = head.last_hash
                    record.record_hash = compute_record_hash(record, changes)
                    record.changes = changes
                    db.add(record)

                    head.last_number = record.audit_number
                    head.last_hash = record.record_hash
                    head.updated_at = record.created_at
                    stored += 1
            db.commit()
        except Exception:
            db.rollback()
            raise

        logger.info(f"Audit ingest: stored={stored} duplicates={duplicates}")
        return {"stored": stored, "duplicates": duplicates}


audit_ingest_service = AuditIngestService()
