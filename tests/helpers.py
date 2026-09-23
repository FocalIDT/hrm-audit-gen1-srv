import uuid
from datetime import datetime, timezone

import jwt

SERVICE_HEADERS = {"X-Audit-Service-Key": "test-service-key"}


def make_token(role: str = "SUPER ADMIN", client_id: str = "101", email: str = "admin@acme.test") -> str:
    claims = {"sub": email, "role": role, "client_id": client_id, "tenant_id": "t-1", "user_id": 7,
              "first_name": "Admin", "last_name": "User", "exp": 4102444800}
    return "Bearer " + jwt.encode(claims, "irrelevant-for-tests", algorithm="HS256")


def make_event(**overrides) -> dict:
    event = {
        "event_uuid": str(uuid.uuid4()),
        "correlation_id": None,
        "client_id": "101",
        "occurred_at": datetime(2026, 8, 24, 5, 0, 0, tzinfo=timezone.utc).isoformat(),
        "module": "Employee",
        "category": "Employee",
        "action": "Employee Updated",
        "event_type": "EMPLOYEE_UPDATED",
        "description": "Employee information modified",
        "status": "Success",
        "actor": {"user_id": "7", "name": "Hr Person", "email": "hr@acme.test", "role": "HR Manager",
                  "system_role": "admin"},
        "subject": {"employee_id": 42, "employee_code": "EMP-0042", "employee_name": "John Perera"},
        "changes": [],
        "details": {},
        "ip_address": "192.168.1.45",
        "user_agent": "pytest",
        "http_method": "PUT",
        "endpoint": "/api/v1/employee/update/42",
        "source_service": "orchestrator",
    }
    event.update(overrides)
    return event
