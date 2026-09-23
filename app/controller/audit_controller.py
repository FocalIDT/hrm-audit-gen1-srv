from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from starlette.responses import StreamingResponse

from app.config.mysql import SessionLocal, db_dependency
from app.model.access_token import AccessToken
from app.model.audit_model import AuditEventBatchIn, AuditLogFilter
from app.model.generic_response import GenericResponse
from app.repository.audit_log_repository import audit_log_repository
from app.service.audit_ingest_service import audit_ingest_service
from app.service.audit_query_service import audit_query_service
from app.service.audit_report_service import audit_report_service
from app.service.auth_service import require_service_key, require_super_admin
from app.service.employee_history_service import employee_history_service
from app.utils.formatters import format_audit_number
from app.utils.hashing import utc_now

router = APIRouter(prefix="/api/v1/audit", tags=["Audit Log"])


def _filters(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
        employee_id: Optional[int] = Query(default=None),
        performed_by: Optional[str] = Query(default=None, description="Performer email"),
        performed_by_role: Optional[str] = Query(default=None, description="Performer role / designation"),
        module: Optional[str] = Query(default=None),
        category: Optional[str] = Query(default=None),
        action: Optional[str] = Query(default=None),
        status: Optional[str] = Query(default=None),
        request_id: Optional[str] = Query(default=None),
        reference_id: Optional[str] = Query(default=None),
        search: Optional[str] = Query(default=None, max_length=200,
                                      description="Employee name/ID, audit ID, request/reference ID or "
                                                  "description"),
) -> AuditLogFilter:
    return AuditLogFilter(date_from=date_from, date_to=date_to, employee_id=employee_id,
                          performed_by=performed_by, performed_by_role=performed_by_role, module=module,
                          category=category, action=action, status=status, request_id=request_id,
                          reference_id=reference_id, search=search)


def _profile(
        employee_name: Optional[str] = Query(default=None),
        employee_code: Optional[str] = Query(default=None),
        designation: Optional[str] = Query(default=None),
        department: Optional[str] = Query(default=None),
        joining_date: Optional[date] = Query(default=None),
        basic_salary: Optional[float] = Query(default=None),
        employment_type: Optional[str] = Query(default=None),
        employment_status: Optional[str] = Query(default=None),
) -> dict:
    return {
        "employee_name": employee_name, "employee_code": employee_code, "designation": designation,
        "department": department, "joining_date": joining_date.isoformat() if joining_date else None,
        "basic_salary": basic_salary, "employment_type": employment_type, "employment_status": employment_status,
    }


def _pdf(content: bytes, filename: str) -> Response:
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ── write (trusted services only) ────────────────────────────────────────────

@router.post("/events", status_code=201, dependencies=[Depends(require_service_key)])
def ingest_events(batch: AuditEventBatchIn, db: db_dependency):
    result = audit_ingest_service.ingest(db, batch.events)
    return GenericResponse.success(message="Audit events recorded", results=result, status_code=201).to_dict()


# ── read (super admins of the tenant) ────────────────────────────────────────

@router.get("/logs")
def list_audit_logs(db: db_dependency,
                    token: AccessToken = Depends(require_super_admin),
                    filters: AuditLogFilter = Depends(_filters),
                    page: int = Query(default=1, ge=1),
                    limit: int = Query(default=10, ge=1, le=100)):
    results = audit_query_service.list_logs(db, token, filters, page, limit)
    return GenericResponse.success(message="Audit logs fetched", results=results).to_dict()


@router.get("/logs/export")
def export_audit_logs(token: AccessToken = Depends(require_super_admin),
                      filters: AuditLogFilter = Depends(_filters)):
    # The request-scoped session is closed before a StreamingResponse is sent,
    # so the stream owns its own session.
    def stream():
        db = SessionLocal()
        try:
            yield from audit_query_service.export_csv(db, token, filters)
        finally:
            db.close()

    filename = f"audit-log-{utc_now():%Y%m%d-%H%M%S}.csv"
    return StreamingResponse(stream(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/logs/{audit_ref}")
def get_audit_log(audit_ref: str, db: db_dependency, token: AccessToken = Depends(require_super_admin)):
    results = audit_query_service.get_detail(db, token, audit_ref)
    return GenericResponse.success(message="Audit record fetched", results=results).to_dict()


@router.get("/logs/{audit_ref}/report")
def download_audit_log_report(audit_ref: str, db: db_dependency,
                              token: AccessToken = Depends(require_super_admin)):
    record = audit_query_service.get_record(db, token, audit_ref)
    related = audit_log_repository.get_related(db, token.client_id, record)
    content = audit_report_service.audit_record_pdf(record, related)
    return _pdf(content, f"{format_audit_number(record.audit_number)}.pdf")


@router.get("/filters")
def get_filter_options(db: db_dependency, token: AccessToken = Depends(require_super_admin)):
    results = audit_query_service.filter_options(db, token)
    return GenericResponse.success(message="Audit filter options fetched", results=results).to_dict()


@router.get("/employees/{employee_id}/history")
def get_employee_history(employee_id: int, db: db_dependency,
                         token: AccessToken = Depends(require_super_admin),
                         profile: dict = Depends(_profile)):
    history = employee_history_service.get_history(db, token, employee_id)
    results = employee_history_service.apply_profile(history, profile)
    return GenericResponse.success(message="Employee history fetched", results=results).to_dict()


@router.get("/employees/{employee_id}/history/report")
def download_employee_history_report(employee_id: int, db: db_dependency,
                                     token: AccessToken = Depends(require_super_admin),
                                     profile: dict = Depends(_profile)):
    history = employee_history_service.get_history(db, token, employee_id)
    history = employee_history_service.apply_profile(history, profile)
    content = audit_report_service.employee_history_pdf(history)
    code = history["employee"].get("employee_code") or f"employee-{employee_id}"
    return _pdf(content, f"employee-history-{code}.pdf")


@router.get("/integrity/verify")
def verify_integrity(db: db_dependency, token: AccessToken = Depends(require_super_admin)):
    results = audit_query_service.verify_integrity(db, token)
    message = "Audit trail is intact" if results["is_valid"] else "Audit trail integrity check failed"
    return GenericResponse.success(message=message, results=results).to_dict()
