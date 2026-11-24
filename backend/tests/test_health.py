"""Health endpoint, request-ID and error-format tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app


def make_client(**kwargs: bool) -> TestClient:
    return TestClient(create_app(), **kwargs)


def test_health_returns_ok() -> None:
    response = make_client().get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "Zhero API"
    # Must not claim a database is healthy before one is wired in.
    assert body["database"] == "not_configured"


def test_health_reports_database_ok_when_configured(
    client: TestClient, db_engine, monkeypatch
) -> None:
    from app.api.routes import health as health_module
    from app.core.config import Settings, get_settings

    monkeypatch.setattr(health_module, "get_engine", lambda: db_engine)
    client.app.dependency_overrides[get_settings] = lambda: Settings(database_url="configured")
    assert client.get("/api/v1/health").json()["database"] == "ok"


def test_health_reports_database_unavailable_on_failure(client: TestClient, monkeypatch) -> None:
    from app.api.routes import health as health_module
    from app.core.config import Settings, get_settings

    def boom():
        raise RuntimeError("down")

    monkeypatch.setattr(health_module, "get_engine", boom)
    client.app.dependency_overrides[get_settings] = lambda: Settings(database_url="configured")
    assert client.get("/api/v1/health").json()["database"] == "unavailable"


def test_request_id_is_generated() -> None:
    response = make_client().get("/api/v1/health")
    assert response.headers["X-Request-ID"]


def test_request_id_is_echoed() -> None:
    response = make_client().get("/api/v1/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_unknown_route_returns_structured_error() -> None:
    response = make_client().get("/api/v1/nope", headers={"X-Request-ID": "rid-1"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "request_id": "rid-1"}
    }


def test_unhandled_error_hides_internals() -> None:
    app: FastAPI = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail /srv/app/file.py")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "secret" not in response.text
    assert "/srv/" not in response.text
    assert body["error"]["request_id"]


def test_openapi_available_in_development() -> None:
    client = make_client()
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
