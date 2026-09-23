import re
from datetime import datetime, time, timedelta
from typing import Iterable, List, Optional, Sequence

from sqlalchemy import and_, distinct, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session

from app.entity.audit_log_entity import AuditChainHead, AuditLog
from app.model.audit_model import AuditLogFilter
from app.utils.hashing import utc_now

_AUDIT_NUMBER_RE = re.compile(r"^\s*(?:AUD-?)?0*(\d{1,12})\s*$", re.IGNORECASE)


def parse_audit_number(value: str) -> Optional[int]:
    """'AUD-000125', 'aud125' or '125' -> 125; anything else -> None."""
    match = _AUDIT_NUMBER_RE.match(value or "")
    return int(match.group(1)) if match else None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class AuditLogRepository:

    # ── writes ───────────────────────────────────────────────────────────────

    @staticmethod
    def lock_chain_head(db: Session, client_id: str) -> AuditChainHead:
        """Return the tenant's chain head, locked for the rest of the transaction."""
        head = (db.query(AuditChainHead)
                .filter(AuditChainHead.client_id == client_id)
                .with_for_update()
                .first())
        if head is not None:
            return head
        try:
            with db.begin_nested():
                db.add(AuditChainHead(client_id=client_id, last_number=0, last_hash=None,
                                      updated_at=utc_now()))
        except IntegrityError:
            # Another writer created it first; fall through and lock theirs.
            pass
        return (db.query(AuditChainHead)
                .filter(AuditChainHead.client_id == client_id)
                .with_for_update()
                .one())

    @staticmethod
    def existing_event_uuids(db: Session, event_uuids: Sequence[str]) -> set:
        if not event_uuids:
            return set()
        rows = db.query(AuditLog.event_uuid).filter(AuditLog.event_uuid.in_(list(event_uuids))).all()
        return {row[0] for row in rows}

    # ── reads ────────────────────────────────────────────────────────────────

    @staticmethod
    def filtered_query(db: Session, client_id: str, filters: AuditLogFilter) -> Query:
        query = db.query(AuditLog).filter(AuditLog.client_id == client_id)

        if filters.date_from:
            query = query.filter(AuditLog.occurred_at >= datetime.combine(filters.date_from, time.min))
        if filters.date_to:
            # Inclusive of the whole "to" day.
            query = query.filter(
                AuditLog.occurred_at < datetime.combine(filters.date_to + timedelta(days=1), time.min))
        if filters.employee_id is not None:
            query = query.filter(AuditLog.employee_id == filters.employee_id)
        if filters.performed_by:
            query = query.filter(AuditLog.performed_by_email == filters.performed_by)
        if filters.performed_by_role:
            query = query.filter(AuditLog.performed_by_role == filters.performed_by_role)
        if filters.module:
            query = query.filter(AuditLog.module == filters.module)
        if filters.category:
            query = query.filter(AuditLog.category == filters.category)
        if filters.action:
            query = query.filter(AuditLog.action == filters.action)
        if filters.status:
            query = query.filter(AuditLog.status == filters.status)
        if filters.request_id:
            query = query.filter(AuditLog.request_id == filters.request_id.strip())
        if filters.reference_id:
            query = query.filter(AuditLog.reference_id == filters.reference_id.strip())

        search = (filters.search or "").strip()
        if search:
            like = f"%{_escape_like(search)}%"
            clauses = [
                AuditLog.employee_name.ilike(like, escape="\\"),
                AuditLog.employee_code.ilike(like, escape="\\"),
                AuditLog.description.ilike(like, escape="\\"),
                AuditLog.action.ilike(like, escape="\\"),
                AuditLog.reference_id.ilike(like, escape="\\"),
                AuditLog.request_id.ilike(like, escape="\\"),
                AuditLog.performed_by_name.ilike(like, escape="\\"),
            ]
            number = parse_audit_number(search)
            if number is not None:
                clauses.append(AuditLog.audit_number == number)
                clauses.append(AuditLog.employee_id == number)
            query = query.filter(or_(*clauses))
        return query

    @staticmethod
    def get_by_audit_ref(db: Session, client_id: str, audit_ref: str) -> Optional[AuditLog]:
        number = parse_audit_number(audit_ref)
        if number is None:
            return None
        return (db.query(AuditLog)
                .filter(AuditLog.client_id == client_id, AuditLog.audit_number == number)
                .first())

    @staticmethod
    def get_related(db: Session, client_id: str, record: AuditLog) -> List[AuditLog]:
        if not record.correlation_id:
            return []
        return (db.query(AuditLog)
                .filter(AuditLog.client_id == client_id,
                        AuditLog.correlation_id == record.correlation_id,
                        AuditLog.id != record.id)
                .order_by(AuditLog.audit_number.asc())
                .all())

    @staticmethod
    def distinct_values(db: Session, client_id: str, column) -> List[str]:
        rows = (db.query(distinct(column))
                .filter(AuditLog.client_id == client_id, column.isnot(None), column != "")
                .order_by(column.asc())
                .all())
        return [row[0] for row in rows]

    @staticmethod
    def module_actions(db: Session, client_id: str) -> List[tuple]:
        return (db.query(AuditLog.module, AuditLog.action)
                .filter(AuditLog.client_id == client_id)
                .group_by(AuditLog.module, AuditLog.action)
                .order_by(AuditLog.module.asc(), AuditLog.action.asc())
                .all())

    @staticmethod
    def performers(db: Session, client_id: str) -> List[tuple]:
        return (db.query(AuditLog.performed_by_email, func.max(AuditLog.performed_by_name),
                         func.max(AuditLog.performed_by_role))
                .filter(AuditLog.client_id == client_id, AuditLog.performed_by_email.isnot(None),
                        AuditLog.performed_by_email != "")
                .group_by(AuditLog.performed_by_email)
                .order_by(func.max(AuditLog.performed_by_name).asc())
                .all())

    @staticmethod
    def employees(db: Session, client_id: str) -> List[tuple]:
        return (db.query(AuditLog.employee_id, func.max(AuditLog.employee_name), func.max(AuditLog.employee_code))
                .filter(AuditLog.client_id == client_id, AuditLog.employee_id.isnot(None))
                .group_by(AuditLog.employee_id)
                .order_by(func.max(AuditLog.employee_name).asc())
                .all())

    @staticmethod
    def employee_events(db: Session, client_id: str, employee_id: int,
                        event_types: Optional[Iterable[str]] = None,
                        modules: Optional[Iterable[str]] = None) -> List[AuditLog]:
        query = db.query(AuditLog).filter(AuditLog.client_id == client_id, AuditLog.employee_id == employee_id)
        conditions = []
        if event_types:
            conditions.append(AuditLog.event_type.in_(list(event_types)))
        if modules:
            conditions.append(AuditLog.module.in_(list(modules)))
        if conditions:
            query = query.filter(or_(*conditions))
        return query.order_by(AuditLog.occurred_at.asc(), AuditLog.audit_number.asc()).all()

    @staticmethod
    def module_counts_for_employee(db: Session, client_id: str, employee_id: int) -> List[tuple]:
        return (db.query(AuditLog.module, func.count(AuditLog.id))
                .filter(and_(AuditLog.client_id == client_id, AuditLog.employee_id == employee_id))
                .group_by(AuditLog.module)
                .all())

    @staticmethod
    def iter_chain(db: Session, client_id: str, batch_size: int = 1000):
        """Yield the tenant's records in chain order without loading them all at once."""
        last_number = 0
        while True:
            batch = (db.query(AuditLog)
                     .filter(AuditLog.client_id == client_id, AuditLog.audit_number > last_number)
                     .order_by(AuditLog.audit_number.asc())
                     .limit(batch_size)
                     .all())
            if not batch:
                return
            yield from batch
            last_number = batch[-1].audit_number
            db.expunge_all()

    @staticmethod
    def chain_head(db: Session, client_id: str) -> Optional[AuditChainHead]:
        return db.query(AuditChainHead).filter(AuditChainHead.client_id == client_id).first()


audit_log_repository = AuditLogRepository()
