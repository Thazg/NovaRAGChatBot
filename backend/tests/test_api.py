from fastapi.testclient import TestClient

from api.routes import health
from app import app


client = TestClient(app)


def test_liveness_is_public_and_versioned() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["backend"] == "running"
    assert response.json()["version"]
    assert float(response.headers["X-Response-Time-Ms"]) >= 0
    assert response.headers["X-Request-ID"]


def test_request_id_is_preserved() -> None:
    response = client.get("/health", headers={"X-Request-ID": "portfolio-check"})

    assert response.headers["X-Request-ID"] == "portfolio-check"
    assert response.headers["Server-Timing"].startswith("app;dur=")


def test_health_reports_bm25_even_when_embedding_endpoint_exists(monkeypatch) -> None:
    monkeypatch.setattr(health.settings, "RETRIEVAL_MODE", "bm25")
    monkeypatch.setattr(health.settings, "EMBEDDING_BASE_URL", "https://embedding.example/v1")

    payload = client.get("/health").json()

    assert payload["retrieval"] == "bm25"
    assert payload["embedding_model"] is None


def test_private_routes_require_authentication() -> None:
    response = client.get("/conversation")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_production_frontend_origin_passes_cors_preflight() -> None:
    response = client.options(
        "/auth/login",
        headers={
            "Origin": "https://novachatbot.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "https://novachatbot.vercel.app"


def test_project_preview_origin_passes_cors_preflight() -> None:
    preview_origin = "https://nova-ai-agent-preview-123-thazg-s-projects.vercel.app"
    response = client.options(
        "/auth/login",
        headers={
            "Origin": preview_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == preview_origin


def test_unrelated_vercel_origin_is_rejected_by_cors() -> None:
    response = client.options(
        "/auth/login",
        headers={
            "Origin": "https://unrelated-project.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400
    assert "Access-Control-Allow-Origin" not in response.headers


def test_untrusted_origin_cannot_use_cookie_auth_endpoints() -> None:
    response = client.post(
        "/auth/refresh",
        headers={"Origin": "https://attacker.example"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Untrusted request origin"}


def test_readiness_reports_provider_state(monkeypatch) -> None:
    async def fake_probe():
        return ({
            "status": "ready",
            "ready": True,
            "backend": "running",
            "llm_provider": "groq",
            "provider_status": "reachable",
        }, 200)

    monkeypatch.setattr(health, "_probe_provider", fake_probe)
    monkeypatch.setattr(health, "_READINESS_CACHE", None)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.headers["X-Readiness-Cache"] == "MISS"


def test_readiness_fails_when_required_infrastructure_is_unavailable(monkeypatch) -> None:
    async def fake_probe():
        return ({
            "status": "ready",
            "ready": True,
            "backend": "running",
            "llm_provider": "groq",
            "provider_status": "reachable",
        }, 200)

    monkeypatch.setattr(health, "_probe_provider", fake_probe)
    monkeypatch.setattr(
        health,
        "_probe_infrastructure",
        lambda: ({"database": "unavailable", "redis": "ready", "index_workers": 1}, False),
    )
    monkeypatch.setattr(health, "_READINESS_CACHE", None)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["ready"] is False
    assert response.json()["infrastructure"]["database"] == "unavailable"


def test_object_storage_is_required_for_shared_index_workers(monkeypatch) -> None:
    from services import remote_storage

    class FakeStorage:
        def head_bucket(self, **kwargs):
            assert kwargs["Bucket"]

    monkeypatch.setattr(remote_storage, "_get_client", lambda: FakeStorage())
    assert health._probe_object_storage(required=True) == ("ready", True)
    monkeypatch.setattr(remote_storage, "_get_client", lambda: None)
    assert health._probe_object_storage(required=True) == ("unavailable", False)
    assert health._probe_object_storage(required=False) == ("optional-local-mode", True)


def test_required_malware_scanner_must_answer_ping(monkeypatch) -> None:
    class FakeScanner:
        def __init__(self, response: bytes) -> None:
            self.response = response

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def sendall(self, payload: bytes) -> None:
            assert payload == b"zPING\0"

        def recv(self, _size: int) -> bytes:
            return self.response

    monkeypatch.setattr(health.settings, "MALWARE_SCAN_REQUIRED", True)
    monkeypatch.setattr(health.settings, "CLAMAV_HOST", "scanner.internal")
    monkeypatch.setattr(health.socket, "create_connection", lambda *_args, **_kwargs: FakeScanner(b"PONG\0"))
    assert health._probe_malware_scanner() == ("ready", True)
    monkeypatch.setattr(health.socket, "create_connection", lambda *_args, **_kwargs: FakeScanner(b"ERROR\0"))
    assert health._probe_malware_scanner() == ("unavailable", False)
