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


def test_private_routes_require_authentication() -> None:
    response = client.get("/conversation")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


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
