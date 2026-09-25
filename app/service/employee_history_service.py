"""Employee history derived from the audit trail (the "Audit Log - Employee History" page).

Everything here is reconstructed from recorded events, so it answers "what
changed and when" even for fields the employee record itself overwrites. For
employees whose early history predates the audit log, the first recorded
change's previous value is used as a baseline with an unknown start date; the
orchestrator fills that in from the employee's joining date.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Optional

from sqlalchemy.orm import Session

from app.entity.audit_log_entity import AuditLog
from app.enum.audit_enum import (CAREER_EVENT_TYPES, EVENT_DESIGNATION_CHANGED, EVENT_EMPLOYEE_CREATED,
                                 EVENT_EMPLOYEE_PROMOTED, EVENT_SALARY_INCREMENT, FIELD_BASIC_SALARY,
                                 FIELD_DEPARTMENT, FIELD_DESIGNATION, REQUEST_MODULES, SALARY_EVENT_TYPES)
from app.model.access_token import AccessToken
from app.repository.audit_log_repository import audit_log_repository
from app.utils.formatters import as_utc_iso, format_audit_number, load_details

_FINAL_REQUEST_STATUSES = {"approved", "rejected", "disapproved", "withdrawn", "completed", "closed",
                           "cancelled", "replied", "deleted"}


def _to_number(value: Optional[str]) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(Decimal(str(value).replace(",", "").strip()))
    except (InvalidOperation, ValueError):
        return None


def _pct(old: Optional[float], new: Optional[float]) -> Optional[float]:
    if old in (None, 0) or new is None:
        return None
    return round((new - old) / old * 100, 1)


def _is_final(status) -> bool:
    """'Leave Approved' / 'Rejected' / 'WFH Request Withdrawn' -> True."""
    words = str(status or "").split()
    return bool(words) and words[-1].lower() in _FINAL_REQUEST_STATUSES


def _is_increment(record: AuditLog) -> bool:
    change = _changes_by_key(record).get(FIELD_BASIC_SALARY)
    old, new = (_to_number(change.old_value), _to_number(change.new_value)) if change else (None, None)
    return old is not None and new is not None and new > old


def _merge_same_day_promotions(events: list[AuditLog]) -> list:
    """Treat a designation change and a salary increase on the same day as one promotion.

    The UI saves both fields together, but HR often saves the new designation and
    the new salary separately, producing a "Designation Changed" and a "Salary
    Increment" record instead of one "Promotion". Audit records are immutable, so
    the pair is combined here, when the history is built. The combined event takes
    the place of the later of the two, keeping the timeline in order.
    """
    designations = [e for e in events if e.event_type == EVENT_DESIGNATION_CHANGED]
    increments = [e for e in events if e.event_type == EVENT_SALARY_INCREMENT and _is_increment(e)]
    replace: dict[int, SimpleNamespace] = {}
    drop: set[int] = set()
    for designation in designations:
        day = _event_date(designation)
        salary = next((e for e in increments if id(e) not in drop and _event_date(e) == day), None)
        if salary is None:
            continue
        first, later = sorted((designation, salary), key=lambda e: (e.occurred_at, e.audit_number))
        replace[id(later)] = SimpleNamespace(
            event_type=EVENT_EMPLOYEE_PROMOTED,
            action="Promotion",
            changes=[*designation.changes, *salary.changes],
            audit_number=designation.audit_number,
            related_audit_numbers=[salary.audit_number],
            occurred_at=later.occurred_at,
            effective_date=day,
            performed_by_role=designation.performed_by_role or salary.performed_by_role,
            performed_by_name=designation.performed_by_name or salary.performed_by_name,
            reference_id=designation.reference_id or salary.reference_id,
            reason=designation.reason or salary.reason,
        )
        drop.update({id(first), id(designation), id(salary)})
    merged = []
    for event in events:
        if id(event) in replace:
            merged.append(replace[id(event)])
        elif id(event) not in drop:
            merged.append(event)
    return merged


def _event_date(record: AuditLog) -> date:
    return record.effective_date or record.occurred_at.date()


def _changes_by_key(record: AuditLog) -> dict:
    return {change.field_key: change for change in record.changes}


class EmployeeHistoryService:

    @classmethod
    def _career_and_salary(cls, events: list[AuditLog]) -> tuple[list, list, list]:
        segments: list[dict] = []
        salary_points: list[dict] = []
        promotions: list[dict] = []
        current_salary: Optional[float] = None
        current_department: Optional[str] = None

        for record in _merge_same_day_promotions(events):
            changes = _changes_by_key(record)
            when = _event_date(record)
            salary_change = changes.get(FIELD_BASIC_SALARY)
            designation_change = changes.get(FIELD_DESIGNATION)
            department_change = changes.get(FIELD_DEPARTMENT)
            is_created = record.event_type == EVENT_EMPLOYEE_CREATED

            old_salary = _to_number(salary_change.old_value) if salary_change else None
            new_salary = _to_number(salary_change.new_value) if salary_change else None
            salary_before = old_salary if old_salary is not None else current_salary

            if department_change is not None:
                department_before = department_change.old_value or current_department
                current_department = department_change.new_value or current_department
            else:
                department_before = current_department

            # Salary series.
            if salary_change is not None:
                if not salary_points and old_salary is not None and not is_created:
                    salary_points.append({"date": None, "salary": old_salary, "action": "Baseline",
                                          "audit_id": None})
                if new_salary is not None:
                    salary_points.append({"date": when.isoformat(), "salary": new_salary,
                                          "action": record.action,
                                          "audit_id": format_audit_number(record.audit_number)})
                    current_salary = new_salary

            # Career segments.
            if designation_change is not None and designation_change.new_value:
                if not segments and designation_change.old_value and not is_created:
                    segments.append({
                        "designation": designation_change.old_value,
                        "department": department_before,
                        "start_date": None,
                        "end_date": None,
                        "salary": salary_before,
                        "audit_id": None,
                    })
                if segments:
                    segments[-1]["end_date"] = when.isoformat()
                segments.append({
                    "designation": designation_change.new_value,
                    "department": current_department,
                    "start_date": when.isoformat(),
                    "end_date": None,
                    "salary": current_salary,
                    "audit_id": format_audit_number(record.audit_number),
                })
            elif segments:
                # A salary or department change within the current role.
                segments[-1]["salary"] = current_salary
                segments[-1]["department"] = current_department or segments[-1]["department"]

            if record.event_type == EVENT_EMPLOYEE_PROMOTED:
                promotions.append({
                    "audit_id": format_audit_number(record.audit_number),
                    "effective_date": when.isoformat(),
                    "action": record.action,
                    "previous_role": designation_change.old_value if designation_change else None,
                    "new_role": designation_change.new_value if designation_change else None,
                    "previous_salary": old_salary,
                    "new_salary": new_salary,
                    "increment_pct": _pct(old_salary, new_salary),
                    "approved_by": record.performed_by_role or record.performed_by_name,
                    "approved_by_name": record.performed_by_name,
                    "reference_id": record.reference_id,
                    "reason": record.reason,
                    # Set when the promotion was saved as separate designation and salary changes.
                    "related_audit_ids": [format_audit_number(n)
                                          for n in getattr(record, "related_audit_numbers", [])],
                })

        previous_salary = None
        for segment in segments:
            segment["increment_pct"] = _pct(previous_salary, segment["salary"])
            if segment["salary"] is not None:
                previous_salary = segment["salary"]
        if segments:
            segments[-1]["is_current"] = True
        for segment in segments[:-1]:
            segment["is_current"] = False

        segments.reverse()   # newest first, as displayed
        promotions.reverse()
        return segments, salary_points, promotions

    @classmethod
    def _requests(cls, events: list[AuditLog]) -> list[dict]:
        grouped: dict[tuple, dict] = {}
        for record in events:
            key = (record.module, record.request_id or record.reference_id or f"audit-{record.audit_number}")
            details = load_details(record)
            entry = grouped.get(key)
            if entry is None:
                entry = grouped[key] = {
                    "module": record.module,
                    "request_id": record.request_id or record.reference_id,
                    "request_type": details.get("request_type") or details.get("leave_type") or record.module,
                    "requested_at": as_utc_iso(record.occurred_at),
                    "details": record.description,
                    "events": 0,
                }
            entry["events"] += 1
            status = details.get("status") or record.action
            entry["status"] = status
            entry["last_action"] = record.action
            entry["last_updated_at"] = as_utc_iso(record.occurred_at)
            entry["responsible_person"] = record.performed_by_name
            entry["remarks"] = record.remarks or entry.get("remarks")
            entry["completed_at"] = as_utc_iso(record.occurred_at) if _is_final(status) else None
        return sorted(grouped.values(), key=lambda item: item["requested_at"] or "", reverse=True)

    @classmethod
    def get_history(cls, db: Session, token: AccessToken, employee_id: int) -> dict:
        client_id = token.client_id
        event_types = set(CAREER_EVENT_TYPES) | set(SALARY_EVENT_TYPES)
        career_events = audit_log_repository.employee_events(db, client_id, employee_id, event_types=event_types)
        request_events = audit_log_repository.employee_events(db, client_id, employee_id, modules=REQUEST_MODULES)
        latest = audit_log_repository.employee_events(db, client_id, employee_id)

        timeline, salary_points, promotions = cls._career_and_salary(career_events)

        known_salaries = [point["salary"] for point in salary_points if point["salary"] is not None]
        first_salary = known_salaries[0] if known_salaries else None
        current_salary = known_salaries[-1] if known_salaries else None

        subject = latest[-1] if latest else None
        return {
            "employee": {
                "employee_id": employee_id,
                "employee_name": subject.employee_name if subject else None,
                "employee_code": subject.employee_code if subject else None,
                "current_designation": timeline[0]["designation"] if timeline else None,
                "current_department": timeline[0]["department"] if timeline else None,
                "current_salary": current_salary,
            },
            "career_timeline": timeline,
            "salary_history": salary_points,
            "promotions": promotions,
            "summary": {
                "first_recorded_salary": first_salary,
                "current_salary": current_salary,
                "overall_salary_increase_pct": _pct(first_salary, current_salary),
                "total_promotions": len(promotions),
                "total_events": len(latest),
            },
            "requests": cls._requests(request_events),
            "activity_by_module": {
                module: count
                for module, count in audit_log_repository.module_counts_for_employee(db, client_id, employee_id)
            },
        }


    @classmethod
    def apply_profile(cls, history: dict, profile: dict) -> dict:
        """Overlay the employee's live profile onto the audit-derived history.

        The audit trail knows what changed; the employee record knows the
        present state and the joining date. The live values win for "current"
        fields, and the joining date anchors the first (baseline) period.
        """
        profile = {key: value for key, value in (profile or {}).items() if value not in (None, "")}
        if not profile:
            return history

        employee = history["employee"]
        joining_date = profile.get("joining_date")
        salary = _to_number(profile.get("basic_salary"))

        for key, target in (("employee_name", "employee_name"), ("employee_code", "employee_code"),
                            ("designation", "current_designation"), ("department", "current_department"),
                            ("employment_type", "employment_type"), ("employment_status", "employment_status")):
            if profile.get(key):
                employee[target] = profile[key]
        if joining_date:
            employee["joining_date"] = joining_date
        if salary is not None:
            employee["current_salary"] = salary

        timeline = history["career_timeline"]
        if timeline:
            baseline = timeline[-1]
            if baseline["start_date"] is None and joining_date:
                baseline["start_date"] = joining_date
            current = timeline[0]
            if salary is not None and current.get("salary") is None:
                current["salary"] = salary
            if profile.get("department") and not current.get("department"):
                current["department"] = profile["department"]
        elif profile.get("designation"):
            timeline.append({
                "designation": profile["designation"],
                "department": profile.get("department"),
                "start_date": joining_date,
                "end_date": None,
                "salary": salary,
                "increment_pct": None,
                "is_current": True,
                "audit_id": None,
            })

        points = history["salary_history"]
        if points and points[0]["date"] is None and joining_date:
            points[0]["date"] = joining_date
        if not points and salary is not None:
            points.append({"date": joining_date, "salary": salary, "action": "Current", "audit_id": None})

        known = [point["salary"] for point in points if point["salary"] is not None]
        summary = history["summary"]
        summary["first_recorded_salary"] = known[0] if known else summary.get("first_recorded_salary")
        summary["current_salary"] = salary if salary is not None else summary.get("current_salary")
        summary["overall_salary_increase_pct"] = _pct(summary["first_recorded_salary"], summary["current_salary"])
        return history


employee_history_service = EmployeeHistoryService()
