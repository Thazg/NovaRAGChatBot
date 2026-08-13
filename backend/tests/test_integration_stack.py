import re
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from api.routes import chat, documents
from app import app
from rag import rag_chain, vector_store
from services import auth, conversation_store


def test_real_upload_index_retrieval_sse_and_citation(monkeypatch) -> None:
    test_root = Path(__file__).with_name("_integration_stack")
    shutil.rmtree(test_root, ignore_errors=True)
    uploads = test_root / "uploads"
    indexes = test_root / "index"
    sessions = test_root / "sessions"
    users = test_root / "users.json"
    uploads.mkdir(parents=True)
    indexes.mkdir(parents=True)
    sessions.mkdir(parents=True)

    monkeypatch.setattr(auth, "USERS_FILE", users)
    monkeypatch.setattr(documents, "BASE_UPLOADS_DIR", uploads)
    monkeypatch.setattr(vector_store, "BASE_INDEX_DIR", indexes)
    monkeypatch.setattr(conversation_store, "BASE_DIR", sessions)

    async def deterministic_llm(_prompt: str):
        yield "Nova uses reciprocal rank fusion. "
        yield "(Source: portfolio.txt)"

    monkeypatch.setattr(chat, "stream_tokens", deterministic_llm)
    monkeypatch.setattr(documents, "stream_tokens", deterministic_llm)

    client = TestClient(app)
    origin = "http://127.0.0.1:5173"
    registration = client.post(
        "/auth/register",
        json={"username": "integration.user", "password": "strong-password"},
        headers={"Origin": origin},
    )
    assert registration.status_code == 200
    token = registration.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Origin": origin}

    uploaded = client.post(
        "/documents/upload",
        headers=headers,
        files={
            "file": (
                "portfolio.txt",
                b"Nova combines BM25 lexical search with FAISS dense retrieval using reciprocal rank fusion.",
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 202
    payload = uploaded.json()
    assert re.fullmatch(r"[0-9a-f]{32}\.txt", payload["id"])
    assert payload["indexed"] is False
    assert payload["job_id"]

    job = None
    for _ in range(100):
        job_response = client.get(f"/documents/jobs/{payload['job_id']}", headers=headers)
        assert job_response.status_code == 200
        job = job_response.json()
        if job["status"] in {"finished", "failed"}:
            break
        time.sleep(0.05)
    assert job and job["status"] == "finished", job
    assert job["result"]["chunks"] >= 1

    listed = client.get("/documents", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "portfolio.txt"
    assert listed.json()[0]["indexed"] is True
    assert "source_url" not in listed.json()[0]

    summary = client.post(
        "/documents/summarize",
        headers=headers,
        json={"filename": "portfolio.txt"},
    )
    assert summary.status_code == 200
    assert "Source: portfolio.txt" in summary.json()["summary"]

    nodes = rag_chain.retrieve_context("How is reciprocal rank fusion used?", registration.json()["user_id"], 5)
    assert nodes
    assert nodes[0]["metadata"]["file_name"] == "portfolio.txt"

    response = client.post(
        "/chat/stream",
        headers=headers,
        json={
            "session_id": "4ab4ef03-50ba-4782-95db-ecc55d64c53d",
            "question": "How does reciprocal rank fusion work?",
            "stream": True,
        },
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "Source: portfolio.txt" in response.text
    assert rag_chain.retrieve_context("BM25 lexical search", registration.json()["user_id"], 5)

    deleted = client.delete(f"/documents/{payload['id']}", headers=headers)
    assert deleted.status_code == 200
    assert client.get("/documents", headers=headers).json() == []

    rag_chain.unload_vector_store(registration.json()["user_id"])
    shutil.rmtree(test_root, ignore_errors=True)
