from tests.helpers import make_event


def _change(key, label, old, new, value_type="text"):
    return {"field_key": key, "field_label": label, "old_value": old, "new_value": new, "value_type": value_type}


def _career(ingest):
    """John: created as Junior (80k), promoted to SE (150k), promoted to Senior SE (200k)."""
    ingest(
        make_event(action="Employee Created", event_type="EMPLOYEE_CREATED",
                   occurred_at="2022-03-15T04:00:00+00:00", effective_date="2022-03-15",
                   changes=[_change("designation", "Designation", None, "Junior Software Engineer"),
                            _change("department", "Department", None, "Engineering"),
                            _change("basic_salary", "Basic Salary", None, "80000", "currency")]),
        make_event(action="Promotion", event_type="EMPLOYEE_PROMOTED", category="Promotion",
                   occurred_at="2023-09-15T04:00:00+00:00", effective_date="2023-09-15", reference_id="PR-00018",
                   changes=[_change("designation", "Designation", "Junior Software Engineer", "Software Engineer"),
                            _change("basic_salary", "Basic Salary", "80000", "150000", "currency")]),
        make_event(action="Promotion", event_type="EMPLOYEE_PROMOTED", category="Promotion",
                   occurred_at="2026-09-01T04:00:00+00:00", effective_date="2026-09-01", reference_id="PR-00025",
                   changes=[_change("designation", "Designation", "Software Engineer", "Senior Software Engineer"),
                            _change("basic_salary", "Basic Salary", "150000", "200000", "currency")]),
        make_event(module="Leave", category="Leave", action="Leave Requested", event_type="LEAVE_REQUESTED",
                   request_id="12", occurred_at="2026-08-01T04:00:00+00:00",
                   details={"leave_type": "Annual Leave", "status": "Pending"}),
        make_event(module="Leave", category="Leave", action="Leave Approved", event_type="LEAVE_APPROVED",
                   request_id="12", occurred_at="2026-08-02T04:00:00+00:00",
                   actor={"name": "Mary Manager", "email": "m@acme.test", "role": "Manager"},
                   details={"leave_type": "Annual Leave", "status": "Approved"}),
    )


def test_career_timeline_salary_growth_and_promotions(client, ingest, admin_headers):
    _career(ingest)
    response = client.get("/api/v1/audit/employees/42/history", headers=admin_headers)
    assert response.status_code == 200, response.text
    history = response.json()["results"]

    timeline = history["career_timeline"]
    assert [t["designation"] for t in timeline] == [
        "Senior Software Engineer", "Software Engineer", "Junior Software Engineer"]
    assert timeline[0]["is_current"] is True and timeline[0]["end_date"] is None
    assert timeline[1]["start_date"] == "2023-09-15" and timeline[1]["end_date"] == "2026-09-01"
    assert [t["salary"] for t in timeline] == [200000.0, 150000.0, 80000.0]
    assert [t["increment_pct"] for t in timeline] == [33.3, 87.5, None]
    assert timeline[2]["department"] == "Engineering"

    assert [p["salary"] for p in history["salary_history"]] == [80000.0, 150000.0, 200000.0]

    promotions = history["promotions"]
    assert [p["reference_id"] for p in promotions] == ["PR-00025", "PR-00018"]
    assert promotions[0]["previous_role"] == "Software Engineer"
    assert promotions[0]["increment_pct"] == 33.3
    assert promotions[0]["approved_by"] == "HR Manager"

    assert history["summary"]["overall_salary_increase_pct"] == 150.0
    assert history["summary"]["total_promotions"] == 2
    assert history["employee"]["current_designation"] == "Senior Software Engineer"

    [leave] = history["requests"]
    assert leave["request_type"] == "Annual Leave"
    assert leave["status"] == "Approved"
    assert leave["responsible_person"] == "Mary Manager"
    assert leave["events"] == 2 and leave["completed_at"] is not None
    assert history["activity_by_module"] == {"Employee": 3, "Leave": 2}


def test_history_without_creation_event_uses_baseline_and_profile(client, ingest, admin_headers):
    # The employee existed before auditing started: only a later designation change is known.
    ingest(make_event(action="Designation Changed", event_type="DESIGNATION_CHANGED",
                      occurred_at="2026-05-01T04:00:00+00:00",
                      changes=[_change("designation", "Designation", "Analyst", "Senior Analyst")]))
    history = client.get("/api/v1/audit/employees/42/history",
                         params={"joining_date": "2021-01-10", "basic_salary": 120000,
                                 "department": "Finance", "employee_name": "John Perera"},
                         headers=admin_headers).json()["results"]

    timeline = history["career_timeline"]
    assert [t["designation"] for t in timeline] == ["Senior Analyst", "Analyst"]
    assert timeline[1]["start_date"] == "2021-01-10"     # anchored on the joining date
    assert timeline[0]["salary"] == 120000.0
    assert history["employee"]["joining_date"] == "2021-01-10"
    assert history["employee"]["current_salary"] == 120000.0


def test_history_with_no_events_falls_back_to_profile(client, admin_headers):
    history = client.get("/api/v1/audit/employees/5/history",
                         params={"designation": "Accountant", "basic_salary": 90000, "joining_date": "2024-02-01"},
                         headers=admin_headers).json()["results"]
    assert history["career_timeline"][0]["designation"] == "Accountant"
    assert history["salary_history"] == [{"date": "2024-02-01", "salary": 90000.0, "action": "Current",
                                          "audit_id": None}]


def test_history_pdf(client, ingest, admin_headers):
    _career(ingest)
    response = client.get("/api/v1/audit/employees/42/history/report", headers=admin_headers)
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert "EMP-0042" in response.headers["content-disposition"]


def _baseline(ingest):
    ingest(make_event(action="Employee Created", event_type="EMPLOYEE_CREATED",
                      occurred_at="2024-01-10T04:00:00+00:00", effective_date="2024-01-10",
                      changes=[_change("designation", "Designation", None, "Software Engineer"),
                               _change("basic_salary", "Basic Salary", None, "150000", "currency")]))


def _designation(when, old, new, **extra):
    return make_event(action="Designation Changed", event_type="DESIGNATION_CHANGED", occurred_at=when,
                      effective_date=when[:10],
                      changes=[_change("designation", "Designation", old, new)], **extra)


def _salary(when, old, new, action="Salary Increment", event_type="SALARY_INCREMENT"):
    return make_event(module="Payroll", category="Salary", action=action, event_type=event_type,
                      occurred_at=when, effective_date=when[:10],
                      changes=[_change("basic_salary", "Basic Salary", old, new, "currency")])


def _history(client, admin_headers):
    return client.get("/api/v1/audit/employees/42/history", headers=admin_headers).json()["results"]


def test_same_day_designation_then_salary_counts_as_a_promotion(client, ingest, admin_headers):
    _baseline(ingest)
    ingest(_designation("2026-09-01T04:00:00+00:00", "Software Engineer", "Senior Software Engineer",
                        reference_id="PR-00025"),
           _salary("2026-09-01T06:30:00+00:00", "150000", "200000"))
    history = _history(client, admin_headers)

    [promotion] = history["promotions"]
    assert promotion["previous_role"] == "Software Engineer"
    assert promotion["new_role"] == "Senior Software Engineer"
    assert (promotion["previous_salary"], promotion["new_salary"]) == (150000.0, 200000.0)
    assert promotion["increment_pct"] == 33.3
    assert promotion["effective_date"] == "2026-09-01"
    assert promotion["reference_id"] == "PR-00025"
    assert promotion["audit_id"] == "AUD-000002" and promotion["related_audit_ids"] == ["AUD-000003"]
    assert history["summary"]["total_promotions"] == 1

    timeline = history["career_timeline"]
    assert [(t["designation"], t["salary"], t["increment_pct"]) for t in timeline] == [
        ("Senior Software Engineer", 200000.0, 33.3), ("Software Engineer", 150000.0, None)]
    assert [p["salary"] for p in history["salary_history"]] == [150000.0, 200000.0]


def test_same_day_salary_then_designation_keeps_the_old_role_salary(client, ingest, admin_headers):
    _baseline(ingest)
    ingest(_salary("2026-09-01T04:00:00+00:00", "150000", "200000"),
           _designation("2026-09-01T06:30:00+00:00", "Software Engineer", "Senior Software Engineer"))
    history = _history(client, admin_headers)
    assert len(history["promotions"]) == 1
    timeline = history["career_timeline"]
    # The raise belongs to the new role, not to the role the employee held that morning.
    assert [(t["designation"], t["salary"]) for t in timeline] == [
        ("Senior Software Engineer", 200000.0), ("Software Engineer", 150000.0)]


def test_changes_on_different_days_or_a_salary_cut_are_not_promotions(client, ingest, admin_headers):
    _baseline(ingest)
    ingest(_designation("2026-09-01T04:00:00+00:00", "Software Engineer", "Tech Lead"),
           _salary("2026-09-02T04:00:00+00:00", "150000", "180000"),
           _designation("2026-09-10T04:00:00+00:00", "Tech Lead", "Architect"),
           _salary("2026-09-10T05:00:00+00:00", "180000", "170000", "Salary Decrement", "SALARY_DECREMENT"))
    assert _history(client, admin_headers)["promotions"] == []
