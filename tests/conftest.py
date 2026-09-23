import os
import sys
import tempfile
import pytest

_DB_FILE = os.path.join(tempfile.mkdtemp(prefix="audit-tests-"), "audit.db")
os.environ["AUDIT_DATABASE_URL"] = f"sqlite:///{_DB_FILE}"
os.environ["USER_MANAGER_URL"] = "http://user-manager.test/api/v1"
os.environ["AUDIT_SERVICE_KEY"] = "test-service-key"
os.environ["LOG_LEVEL"] = "WARNING"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import event  # noqa: E402

from app.config.mysql import Base, engine  # noqa: E402


# pysqlite's own transaction handling breaks SAVEPOINT; this is SQLAlchemy's
# documented recipe to let the database manage transactions itself.
@event.listens_for(engine, "connect")
def _sqlite_connect(dbapi_connection, _record):
    dbapi_connection.isolation_level = None


@event.listens_for(engine, "begin")
def _sqlite_begin(conn):
    conn.exec_driver_sql("BEGIN")


from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.service import auth_service  # noqa: E402
from tests.helpers import SERVICE_HEADERS, make_token  # noqa: E402

@pytest.fixture(autouse=True)
def fresh_database(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    auth_service._token_cache.clear()
    # Every token is "valid" as far as the user manager is concerned.
    monkeypatch.setattr(auth_service, "_validate_with_user_manager", lambda _header: 200)
    yield


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def ingest(client):
    def _ingest(*events):
        response = client.post("/api/v1/audit/events", json={"events": list(events)}, headers=SERVICE_HEADERS)
        assert response.status_code == 201, response.text
        return response.json()["results"]
    return _ingest


@pytest.fixture
def admin_headers():
    return {"Authorization": make_token()}
