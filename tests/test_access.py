from tests.helpers import make_event, make_token


def test_ingest_requires_the_service_key(client):
    body = {"events": [make_event()]}
    assert client.post("/api/v1/audit/events", json=body).status_code == 401
    assert client.post("/api/v1/audit/events", json=body,
                       headers={"X-Audit-Service-Key": "wrong"}).status_code == 401


def test_ingest_rejects_a_user_token(client):
    # A logged-in user (even a super admin) cannot write audit records directly.
    response = client.post("/api/v1/audit/events", json={"events": [make_event()]},
                           headers={"Authorization": make_token()})
    assert response.status_code == 401


def test_reads_require_a_token(client):
    assert client.get("/api/v1/audit/logs").status_code == 401


def test_reads_are_super_admin_only(client, ingest):
    ingest(make_event())
    for role in ("admin", "employee", "manager"):
        response = client.get("/api/v1/audit/logs", headers={"Authorization": make_token(role=role)})
        assert response.status_code == 403, role


def test_expired_session_is_rejected(client, monkeypatch):
    from app.service import auth_service
    monkeypatch.setattr(auth_service, "_validate_with_user_manager", lambda _header: 401)
    response = client.get("/api/v1/audit/logs", headers={"Authorization": make_token()})
    assert response.status_code == 401


def test_super_admin_role_variants_are_accepted(client):
    for role in ("SUPER ADMIN", "super admin", "SuperAdmin", "ROLE_SUPER ADMIN"):
        response = client.get("/api/v1/audit/logs", headers={"Authorization": make_token(role=role)})
        assert response.status_code == 200, role


def test_tenants_are_isolated(client, ingest):
    ingest(make_event(client_id="101", description="acme event"),
           make_event(client_id="202", description="globex event"))

    acme = client.get("/api/v1/audit/logs", headers={"Authorization": make_token(client_id="101")}).json()
    globex = client.get("/api/v1/audit/logs", headers={"Authorization": make_token(client_id="202")}).json()

    assert [r["description"] for r in acme["results"]["result"]] == ["acme event"]
    assert [r["description"] for r in globex["results"]["result"]] == ["globex event"]
    # Both tenants start their own numbering at AUD-000001 ...
    assert acme["results"]["result"][0]["audit_id"] == "AUD-000001"
    assert globex["results"]["result"][0]["audit_id"] == "AUD-000001"
    # ... and one tenant cannot open the other's record through its number.
    other = client.get("/api/v1/audit/logs/AUD-000002", headers={"Authorization": make_token(client_id="202")})
    assert other.status_code == 404
