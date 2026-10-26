import asyncio
import json

import pytest
from fastapi import HTTPException
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from starlette.requests import Request

from api.routes import chat, documents
from rag import load, prompts
from rag.chunking import split_documents
from services import conversation_store, remote_storage


def request(user="owner"):
    return Request({"type": "http", "state": {"user_id": user}})


def write_pdf(path):
    writer = PdfWriter()
    for text in ("Alpha evidence on the first page.", "Beta evidence on the second page."):
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 250 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as output:
        writer.write(output)


def test_pdf_ingestion_keeps_page_numbers_and_evidence_budget(tmp_path, monkeypatch):
    path = tmp_path / "paper.pdf"
    write_pdf(path)
    nodes = split_documents(load.load_pdf(path))
    assert [node["metadata"]["page"] for node in nodes] == [1, 2]
    assert "Beta evidence" in nodes[1]["content"]
    context, evidence = prompts.build_context_and_evidence(nodes)
    assert [item["id"] for item in evidence] == ["E1", "E2"]
    assert evidence[1]["page"] == 2
    assert evidence[1]["content"] in context
    monkeypatch.setattr(prompts.settings, "MAX_CONTEXT_CHARS", len(context) - 1)
    context, evidence = prompts.build_context_and_evidence(nodes)
    assert len(context) <= prompts.settings.MAX_CONTEXT_CHARS
    assert evidence[-1]["content"] in context


def test_line_numbers_follow_extracted_text_and_survive_normalization(monkeypatch):
    text, spans = load.normalize_pdf_with_lines("First line.\nretrieval-\naugmented evidence.\n\nFinal line.")
    assert text == "First line. retrievalaugmented evidence. Final line."
    document = load.Document(text=text, metadata={"file_name": "paper.pdf", "page": 3, "_line_spans": spans})
    nodes = split_documents([document])
    assert nodes[0]["metadata"]["line_start"] == 1
    assert nodes[0]["metadata"]["line_end"] == 5
    assert nodes[0]["metadata"]["page"] == 3
    assert {span["line"] for span in nodes[0]["metadata"]["line_spans"]} == {1, 2, 3, 5}
    assert "_line_spans" not in nodes[0]["metadata"]
    monkeypatch.setattr(prompts.settings, "MAX_CHUNK_CHARS", 12)
    _, evidence = prompts.build_context_and_evidence(nodes)
    assert evidence[0]["line_start"] == 1
    assert evidence[0]["line_end"] == 1


def test_evidence_survives_history_and_regeneration_does_not_duplicate_user(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation_store, "BASE_DIR", tmp_path)
    monkeypatch.setattr(remote_storage, "upload_file", lambda *args: False)
    monkeypatch.setattr(remote_storage, "download_file", lambda *args: False)
    nodes = [{"content": "Beta evidence on page two.", "metadata": {"file_name": "paper.pdf", "storage_name": "stored.pdf", "page": 2, "chunk_index": 1}}]
    async def retrieve(*args):
        return nodes
    async def tokens(prompt):
        assert "Evidence ID: E1; Page: 2" in prompt
        yield "Beta evidence [E1]."
    monkeypatch.setattr(chat, "_retrieve_nodes", retrieve)
    monkeypatch.setattr(chat, "get_retriever", lambda *args: type("Store", (), {"documents": nodes})())
    monkeypatch.setattr(chat, "stream_tokens", tokens)
    async def send(regenerate=False):
        response = await chat.chat_stream(request(), chat.ChatRequest(session_id="session", question="Where is beta evidence?", regenerate=regenerate))
        return [part async for part in response.body_iterator]
    events = asyncio.run(send())
    evidence = json.loads(events[0][6:])["evidence"]
    assert evidence[0]["document_id"] == "stored.pdf"
    assert evidence[0]["page"] == 2
    assert events[-1] == "data: [DONE]\n\n"
    assert conversation_store.get_conversation("session", "owner")["messages"][-1]["retrievedDocs"] == evidence
    asyncio.run(send(regenerate=True))
    messages = conversation_store.get_conversation("session", "owner")["messages"]
    assert [item["role"] for item in messages] == ["user", "assistant"]
    # If the failed POST never reached the server, regenerate must not remove
    # the previous, unrelated answer while creating the missing user turn.
    previous_answer = messages[-1]["content"]
    conversation_store.prepare_regeneration("session", "owner", question="A newer question")
    assert conversation_store.get_conversation("session", "owner")["messages"][-1]["content"] == previous_answer


@pytest.mark.parametrize("tokens", [["one"], ["one", " two"], ["one", " two", " three"], ["one", " two", " three", " four"]])
def test_failed_provider_does_not_emit_done_and_is_persisted_as_interrupted(tmp_path, monkeypatch, tokens):
    monkeypatch.setattr(conversation_store, "BASE_DIR", tmp_path)
    monkeypatch.setattr(remote_storage, "upload_file", lambda *args: False)
    monkeypatch.setattr(remote_storage, "download_file", lambda *args: False)
    async def retrieve(*args):
        return []
    async def provider_tokens(prompt):
        for token in tokens:
            yield token
        raise RuntimeError("provider disconnected")
    monkeypatch.setattr(chat, "_retrieve_nodes", retrieve)
    monkeypatch.setattr(chat, "get_retriever", lambda *args: None)
    monkeypatch.setattr(chat, "stream_tokens", provider_tokens)
    async def run():
        response = await chat.chat_stream(request(), chat.ChatRequest(session_id="failed", question="What does the paper establish?"))
        return "".join([event async for event in response.body_iterator])
    wire = asyncio.run(run())
    assert "[DONE]" not in wire
    assert '"error"' in wire
    message = conversation_store.get_conversation("failed", "owner")["messages"][-1]
    assert message["interrupted"] is True
    assert message["content"] == "".join(tokens)


@pytest.mark.parametrize("citation,success", [("E1", True), ("E99", False)])
def test_unknown_evidence_ids_cannot_complete_a_grounded_answer(tmp_path, monkeypatch, citation, success):
    monkeypatch.setattr(conversation_store, "BASE_DIR", tmp_path / "sessions")
    monkeypatch.setattr(chat.settings, "REDIS_URL", "")
    monkeypatch.setattr(chat.settings, "B2_KEY_ID", "")
    monkeypatch.setattr(chat.settings, "B2_APP_KEY", "")
    monkeypatch.setattr(remote_storage, "upload_file", lambda *args: False)
    monkeypatch.setattr(remote_storage, "download_file", lambda *args: False)
    nodes = [{"content": "Supported evidence.", "metadata": {"file_name": "notes.txt", "chunk_index": 1}}]
    async def retrieve(*args):
        return nodes
    async def tokens(prompt):
        assert "Earlier assistant answers are not evidence" in prompt
        assert "untrusted document excerpts" in prompt
        assert "A missing mention is not proof" in prompt
        yield f"A claim [{citation}]."
    monkeypatch.setattr(chat, "_retrieve_nodes", retrieve)
    monkeypatch.setattr(chat, "get_retriever", lambda *args: type("Store", (), {"documents": nodes})())
    monkeypatch.setattr(chat, "stream_tokens", tokens)
    async def send():
        response = await chat.chat_stream(request(), chat.ChatRequest(session_id="citation-test", question="What does the evidence say?"))
        return "".join([part async for part in response.body_iterator])
    wire = asyncio.run(send())
    assert ("[DONE]" in wire) is success
    saved = conversation_store.get_conversation("citation-test", "owner")["messages"][-1]
    assert saved["content"] == f"A claim [{citation}]."
    assert bool(saved.get("interrupted")) is not success


def test_account_deletion_during_generation_prevents_late_history_and_done(tmp_path, monkeypatch):
    from services import account_lifecycle
    monkeypatch.setattr(conversation_store, "BASE_DIR", tmp_path / "sessions")
    monkeypatch.setattr(account_lifecycle, "BASE_DIR", tmp_path / "barriers")
    monkeypatch.setattr(chat.settings, "REDIS_URL", "")
    monkeypatch.setattr(chat.settings, "B2_KEY_ID", "")
    monkeypatch.setattr(chat.settings, "B2_APP_KEY", "")
    monkeypatch.setattr(remote_storage, "upload_file", lambda *args: False)
    monkeypatch.setattr(remote_storage, "download_file", lambda *args: False)
    async def retrieve(*args):
        return []
    async def tokens(prompt):
        account_lifecycle.mark_deleting("owner")
        yield "Late model answer."
    monkeypatch.setattr(chat, "_retrieve_nodes", retrieve)
    monkeypatch.setattr(chat, "get_retriever", lambda *args: None)
    monkeypatch.setattr(chat, "stream_tokens", tokens)
    async def send():
        response = await chat.chat_stream(request(), chat.ChatRequest(session_id="deleting", question="Explain the document."))
        return "".join([part async for part in response.body_iterator])
    wire = asyncio.run(send())
    assert "[DONE]" not in wire
    assert '"error"' in wire
    messages = conversation_store._load_store("owner")["deleting"]["messages"]
    assert [message["role"] for message in messages] == ["user"]
