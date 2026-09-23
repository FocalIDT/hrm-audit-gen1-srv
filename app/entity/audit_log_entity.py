from sqlalchemy import (BIGINT, BigInteger, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import relationship

from app.config.mysql import Base

# BIGINT on MySQL; INTEGER on SQLite (tests), where only INTEGER PRIMARY KEY auto-increments.
_PK = BigInteger().with_variant(Integer, "sqlite")


class AuditLog(Base):
    """One immutable audit record.

    Rows are only ever inserted. Every row carries the hash of the previous row
    of the same tenant (prev_hash) and a hash over its own content
    (record_hash), so any later UPDATE/DELETE breaks the chain and is caught by
    GET /api/v1/audit/integrity/verify.
    """
    __tablename__ = "audit_logs"

    id = Column(_PK, primary_key=True, autoincrement=True)

    # Tenant. Taken from the acting user's JWT client_id, never from user input.
    client_id = Column(String(64), nullable=False)
    tenant_id = Column(String(64), nullable=True)
    # Per-tenant running number shown as AUD-000125.
    audit_number = Column(BIGINT, nullable=False)

    # Idempotency key from the emitter, so a retried delivery is stored once.
    event_uuid = Column(String(36), nullable=False, unique=True)
    # Events produced by the same HTTP request share this id (e.g. a promotion
    # and the salary change it carried).
    correlation_id = Column(String(64), nullable=True, index=True)

    occurred_at = Column(DateTime, nullable=False)
    module = Column(String(40), nullable=False)
    category = Column(String(40), nullable=False)
    action = Column(String(100), nullable=False)
    event_type = Column(String(60), nullable=False)
    description = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="Success")

    # WHO performed it.
    performed_by_user_id = Column(String(64), nullable=True)
    performed_by_employee_id = Column(BIGINT, nullable=True)
    performed_by_name = Column(String(255), nullable=True)
    performed_by_email = Column(String(255), nullable=True)
    # Display role: the performer's designation when known ("HR Manager"),
    # otherwise their system role ("Super Admin").
    performed_by_role = Column(String(150), nullable=True)
    performed_by_system_role = Column(String(60), nullable=True)

    # WHICH employee was affected.
    employee_id = Column(BIGINT, nullable=True)
    employee_code = Column(String(50), nullable=True)
    employee_name = Column(String(255), nullable=True)

    # WHY / REFERENCE.
    reason = Column(Text, nullable=True)
    remarks = Column(Text, nullable=True)
    reference_type = Column(String(100), nullable=True)
    reference_id = Column(String(100), nullable=True)
    request_id = Column(String(100), nullable=True)
    effective_date = Column(Date, nullable=True)
    payroll_period = Column(String(20), nullable=True)

    # Module-specific details (leave type, days, EPF amounts, file name...).
    details = Column(Text, nullable=True)

    # Source.
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    http_method = Column(String(10), nullable=True)
    endpoint = Column(String(255), nullable=True)
    source_service = Column(String(60), nullable=True)

    prev_hash = Column(String(64), nullable=True)
    record_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False)

    changes = relationship("AuditLogChange", order_by="AuditLogChange.sort_order", lazy="selectin",
                           back_populates="audit_log")

    __table_args__ = (
        UniqueConstraint("client_id", "audit_number", name="uq_audit_logs_client_number"),
        Index("ix_audit_logs_client_occurred", "client_id", "occurred_at"),
        Index("ix_audit_logs_client_employee", "client_id", "employee_id", "occurred_at"),
        Index("ix_audit_logs_client_module", "client_id", "module"),
        Index("ix_audit_logs_client_action", "client_id", "action"),
        Index("ix_audit_logs_client_reference", "client_id", "reference_id"),
        Index("ix_audit_logs_client_request", "client_id", "request_id"),
    )


class AuditLogChange(Base):
    """A single field change (previous value -> new value) of an audit record."""
    __tablename__ = "audit_log_changes"

    id = Column(_PK, primary_key=True, autoincrement=True)
    audit_log_id = Column(BIGINT, ForeignKey("audit_logs.id"), nullable=False, index=True)
    field_key = Column(String(100), nullable=False)
    field_label = Column(String(150), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    value_type = Column(String(20), nullable=False, default="text")
    sort_order = Column(Integer, nullable=False, default=0)

    audit_log = relationship("AuditLog", back_populates="changes")


class AuditChainHead(Base):
    """Per-tenant head of the hash chain and the running audit number.

    Inserts lock this row (SELECT ... FOR UPDATE), which serialises writers of
    the same tenant so numbers stay gap-free and the chain stays linear.
    """
    __tablename__ = "audit_chain_heads"

    client_id = Column(String(64), primary_key=True)
    last_number = Column(BIGINT, nullable=False, default=0)
    last_hash = Column(String(64), nullable=True)
    updated_at = Column(DateTime, nullable=True)
