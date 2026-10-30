import csv
import io

from sqlalchemy import text

from app.config.mysql import engine
from tests.helpers import make_event


def test_ingest_numbers_sequentially_and_is_idempotent(client, ingest, admin_headers):
    first, second = make_event(), make_event()
    assert ingest(first, second) == {"stored": 2, "duplicates": 0}
    assert ingest(first) == {"stored": 0, "duplicates": 1}

    rows = client.get("/api/v1/audit/logs", headers=admin_headers).json()["results"]["result"]
    assert sorted(r["audit_id"] for r in rows) == ["AUD-000001", "AUD-000002"]


def test_unknown_module_is_rejected(client):
    from tests.helpers import SERVICE_HEADERS
    response = client.post("/api/v1/audit/events", json={"events": [make_event(module="Nope")]},
                           headers=SERVICE_HEADERS)
    assert response.status_code == 422


def test_list_filters_and_search(client, ingest, admin_headers):
    ingest(
        make_event(module="Leave", category="Leave", action="Leave Approved", request_id="LR-9",
                   occurred_at="2026-08-24T05:10:00+00:00"),
        make_event(module="Payroll", category="Salary", action="Salary Increment",
                   occurred_at="2026-08-22T05:10:00+00:00"),
        make_event(module="Employee", category="Employee", action="Employee Updated",
                   subject={"employee_id": 7, "employee_code": "EMP-0007", "employee_name": "Sarah Silva"},
                   occurred_at="2026-08-20T05:10:00+00:00"),
    )

    def actions(**params):
        response = client.get("/api/v1/audit/logs", params=params, headers=admin_headers)
        assert response.status_code == 200, response.text
        return [row["action"] for row in response.json()["results"]["result"]]

    assert actions() == ["Leave Approved", "Salary Increment", "Employee Updated"]  # newest first
    assert actions(module="Payroll") == ["Salary Increment"]
    assert actions(category="Leave") == ["Leave Approved"]
    assert actions(action="Employee Updated") == ["Employee Updated"]
    assert actions(date_from="2026-08-22", date_to="2026-08-22") == ["Salary Increment"]
    assert actions(employee_id=7) == ["Employee Updated"]
    assert actions(request_id="LR-9") == ["Leave Approved"]
    assert actions(search="sarah") == ["Employee Updated"]
    assert actions(search="AUD-000002") == ["Salary Increment"]
    assert actions(search="EMP-0007") == ["Employee Updated"]
    assert actions(performed_by_role="HR Manager", status="Success")[0] == "Leave Approved"
    # LIKE wildcards in the search box are literals, not patterns.
    assert actions(search="%") == []


def test_pagination(client, ingest, admin_headers):
    ingest(*[make_event() for _ in range(12)])
    page = client.get("/api/v1/audit/logs", params={"page": 2, "limit": 5}, headers=admin_headers).json()
    assert page["results"]["pagination"] == {"total_items": 12, "total_pages": 3, "current_page": 2,
                                             "page_size": 5}
    assert len(page["results"]["result"]) == 5


def test_detail_with_changes_and_related_events(client, ingest, admin_headers):
    ingest(
        make_event(action="Promotion", event_type="EMPLOYEE_PROMOTED", module="Employee", category="Promotion",
                   correlation_id="req-1", reason="Performance Promotion", reference_type="Promotion Request",
                   reference_id="PR-00025",
                   changes=[
                       {"field_key": "designation", "field_label": "Designation",
                        "old_value": "Software Engineer", "new_value": "Senior Software Engineer"},
                       {"field_key": "basic_salary", "field_label": "Basic Salary", "old_value": "150000",
                        "new_value": "200000", "value_type": "currency"},
                   ]),
        make_event(action="Employee Updated", correlation_id="req-1"),
    )
    response = client.get("/api/v1/audit/logs/AUD-000001", headers=admin_headers)
    assert response.status_code == 200
    detail = response.json()["results"]
    assert detail["reason"] == "Performance Promotion"
    assert detail["reference_id"] == "PR-00025"
    assert [c["field_label"] for c in detail["changes"]] == ["Designation", "Basic Salary"]
    assert detail["changes"][1] == {"field_key": "basic_salary", "field_label": "Basic Salary",
                                    "old_value": "150000", "new_value": "200000", "value_type": "currency"}
    assert [r["audit_id"] for r in detail["related"]] == ["AUD-000002"]
    assert detail["occurred_at"].endswith("+00:00")
    # The plain number and the numeric id resolve to the same record.
    assert client.get("/api/v1/audit/logs/1", headers=admin_headers).json()["results"]["audit_id"] == "AUD-000001"
    assert client.get("/api/v1/audit/logs/AUD-999999", headers=admin_headers).status_code == 404


def test_filter_options(client, ingest, admin_headers):
    ingest(make_event(module="Leave", category="Leave", action="Leave Approved"))
    options = client.get("/api/v1/audit/filters", headers=admin_headers).json()["results"]
    assert "Leave" in options["modules"] and "PAYE" in options["categories"]
    assert options["actions_by_module"] == {"Leave": ["Leave Approved"]}
    assert options["performer_roles"] == ["HR Manager"]
    assert options["employees"] == [{"employee_id": 42, "employee_name": "John Perera",
                                     "employee_code": "EMP-0042"}]


def test_csv_export(client, ingest, admin_headers):
    ingest(make_event(description="=HYPERLINK(\"http://evil\")",
                      changes=[{"field_key": "role", "field_label": "Designation", "old_value": "A",
                                "new_value": "B"}]))
    response = client.get("/api/v1/audit/logs/export", headers=admin_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.text.lstrip("﻿"))))
    assert rows[0][0] == "Audit ID"
    assert rows[1][0] == "AUD-000001"
    assert rows[1][9].startswith("'=")          # formula neutralised
    assert rows[1][10] == "Designation: A"
    assert rows[1][11] == "Designation: B"


def test_pdf_report(client, ingest, admin_headers):
    ingest(make_event(changes=[{"field_key": "x", "field_label": "X", "old_value": "<b>", "new_value": "&"}]))
    response = client.get("/api/v1/audit/logs/AUD-000001/report", headers=admin_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_integrity_verification_detects_tampering(client, ingest, admin_headers):
    ingest(*[make_event(description=f"event {i}") for i in range(3)])
    ok = client.get("/api/v1/audit/integrity/verify", headers=admin_headers).json()["results"]
    assert ok == {"is_valid": True, "records_checked": 3, "first_invalid_audit_id": None, "problem": None}

    with engine.begin() as conn:
        conn.execute(text("UPDATE audit_logs SET description = 'rewritten' WHERE audit_number = 2"))
    tampered = client.get("/api/v1/audit/integrity/verify", headers=admin_headers).json()["results"]
    assert tampered["is_valid"] is False
    assert tampered["first_invalid_audit_id"] == "AUD-000002"


def test_integrity_verification_detects_deleted_rows(client, ingest, admin_headers):
    ingest(*[make_event() for _ in range(3)])
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_logs WHERE audit_number = 3"))
    result = client.get("/api/v1/audit/integrity/verify", headers=admin_headers).json()["results"]
    assert result["is_valid"] is False
    assert result["problem"] == "records at the end of the chain are missing"


def test_pdf_report_lists_assigned_employees(client, ingest, admin_headers):
    from app.service import audit_report_service as reports
    captured = []
    real_grid = reports._grid
    reports._grid = lambda rows, widths, header=True: captured.append(rows) or real_grid(rows, widths, header)
    try:
        ingest(make_event(module="System Configuration", category="Leave", action="Leave Workflow Assigned",
                          event_type="LEAVE_WORKFLOW_ASSIGNED",
                          details={"workflow": "Standard", "employee_count": 2,
                                   "assigned_employees": [{"name": "John Perera", "number": "2"},
                                                          {"name": "Sarah Silva", "number": "5"}]}))
        response = client.get("/api/v1/audit/logs/AUD-000001/report", headers=admin_headers)
    finally:
        reports._grid = real_grid
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    assert [["Employee No.", "Employee Name"], ["2", "John Perera"], ["5", "Sarah Silva"]] in captured
    additional = next(rows for rows in captured if rows[0] == ["Item", "Value"])
    assert all(row[0] != "Assigned Employees" for row in additional)
