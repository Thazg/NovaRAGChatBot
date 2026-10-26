import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from api.routes import chat
from app import app


@pytest.mark.parametrize("overrides", [
    {"session_id": "../other-session"}, {"session_id": ""}, {"session_id": "a" * 37},
    {"question": ""}, {"question": "a" * 8001}, {"instructions": "a" * 4001},
    {"language": "unknown"}, {"document_name": "a" * 181},
])
def test_chat_rejects_invalid_inputs_before_storage_or_provider_work(monkeypatch, overrides):
    monkeypatch.setattr("app.verify_token", lambda _token: {"user_id": "owner"})
    monkeypatch.setattr("app.user_exists", lambda _user: True)
    def unexpected(*_args, **_kwargs):
        raise AssertionError("Invalid requests must be rejected before retrieval or mutation")
    monkeypatch.setattr(chat, "_retrieve_nodes", unexpected)
    monkeypatch.setattr(chat, "append_session_message", unexpected)
    monkeypatch.setattr(chat, "get_session_history", unexpected)
    response = TestClient(app).post("/chat/stream", headers={"Authorization": "Bearer test"}, json={
        "session_id": "session", "question": "What is the evidence?", **overrides,
    })
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_question_mentioning_hello_is_retrieved_instead_of_short_circuited(monkeypatch):
    calls = []
    async def retrieve(question, *_args):
        calls.append(question)
        return [{"content": "Hello world is a programming example.", "metadata": {"file_name": "notes.txt"}}]
    async def tokens(_prompt):
        yield "The document describes a programming example [E1]."
    monkeypatch.setattr(chat, "_retrieve_nodes", retrieve)
    monkeypatch.setattr(chat, "get_retriever", lambda *_: None)
    monkeypatch.setattr(chat, "get_session_history", lambda *_: [])
    monkeypatch.setattr(chat, "append_session_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "stream_tokens", tokens)
    async def send():
        response = await chat.chat_stream(
            Request({"type": "http", "state": {"user_id": "owner"}}),
            chat.ChatRequest(session_id="session", question="Explain hello world in this document"),
        )
        return "".join([part async for part in response.body_iterator])
    wire = asyncio.run(send())
    assert calls == ["Explain hello world in this document"]
    assert "programming example" in wire
    assert "evidence" in wire
    assert "[DONE]" in wire


@pytest.mark.parametrize("question", ["summarize", "What is Python?", "How does it compare?"])
def test_chat_uses_shared_user_only_rewrite_policy(monkeypatch, question):
    observed = []
    prior = [{"role": "user", "content": "Explain BM25 retrieval"},
             {"role": "assistant", "content": "UNVERIFIED_ASSISTANT_OUTPUT"}]
    async def retrieve(raw, rewritten, *_args):
        observed.append(rewritten)
        return []
    async def tokens(_prompt):
        yield "No supporting passages were found."
    monkeypatch.setattr(chat, "_retrieve_nodes", retrieve)
    monkeypatch.setattr(chat, "get_retriever", lambda *_: None)
    monkeypatch.setattr(chat, "get_session_history", lambda *_: prior)
    monkeypatch.setattr(chat, "append_session_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "stream_tokens", tokens)
    async def send():
        response = await chat.chat_stream(Request({"type": "http", "state": {"user_id": "owner"}}),
            chat.ChatRequest(session_id="rewrite-api", question=question))
        return [part async for part in response.body_iterator]
    asyncio.run(send())
    assert "UNVERIFIED_ASSISTANT_OUTPUT" not in observed[0]
    if question == "How does it compare?":
        assert "BM25 retrieval" in observed[0]
    else:
        assert observed == [question]


def test_chat_with_conflicting_conversation_id_returns_conflict(monkeypatch):
    from services.postgres_store import ConversationIdConflict
    monkeypatch.setattr("app.verify_token", lambda _token: {"user_id": "owner"})
    monkeypatch.setattr("app.user_exists", lambda _user: True)
    def conflicting_id(*_args, **_kwargs):
        raise ConversationIdConflict()
    monkeypatch.setattr(chat, "append_session_message", conflicting_id)
    response = TestClient(app).post("/chat/stream", headers={"Authorization": "Bearer test"}, json={
        "session_id": "session", "question": "Hello",
    })
    assert response.status_code == 409
    assert response.json() == {"detail": "Conversation ID is unavailable"}


def test_retrieval_preserves_pending_account_conflict(monkeypatch):
    from services.account_lifecycle import AccountDeletionPending
    def pending(*_args, **_kwargs):
        raise AccountDeletionPending()
    monkeypatch.setattr(chat, "retrieve_context", pending)
    with pytest.raises(AccountDeletionPending):
        asyncio.run(chat._retrieve_nodes("question", "question", "owner"))


@pytest.mark.parametrize(("question", "language", "expected"), [
    ("Hi!", "auto", "Hi!"), ("Xin chào!", "auto", "Chào bạn!"),
    ("Hello", "vietnamese", "Chào bạn!"),
])
def test_standalone_greeting_remains_local_and_respects_language(monkeypatch, question, language, expected):
    monkeypatch.setattr(chat, "append_session_message", lambda *_args, **_kwargs: None)
    def unexpected(*_args):
        raise AssertionError("Standalone greetings must not invoke retrieval")
    monkeypatch.setattr(chat, "_retrieve_nodes", unexpected)
    async def send():
        response = await chat.chat_stream(
            Request({"type": "http", "state": {"user_id": "owner"}}),
            chat.ChatRequest(session_id="session", question=question, language=language),
        )
        return [part async for part in response.body_iterator]
    events = asyncio.run(send())
    assert json.loads(events[0][6:])["token"].startswith(expected)
    assert events[-1] == "data: [DONE]\n\n"
