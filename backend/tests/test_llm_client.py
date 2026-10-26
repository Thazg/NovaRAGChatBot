import asyncio
import json
import pytest

from rag import llm_client


class FakeStreamResponse:
    def __init__(self, status_code: int, chunks: list[bytes], body: bytes = b"") -> None:
        self.status_code = status_code
        self._chunks = chunks
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk

    async def aread(self) -> bytes:
        return self._body


class FakeAsyncClient:
    def __init__(self, response: FakeStreamResponse, capture: dict) -> None:
        self.response = response
        self.capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def stream(self, method: str, url: str, **kwargs):
        self.capture.update({"method": method, "url": url, **kwargs})
        return self.response


async def _collect(generator) -> str:
    return "".join([token async for token in generator])


def test_groq_stream_parses_tokens_and_sends_deterministic_seed(monkeypatch) -> None:
    capture: dict = {}
    events = (
        "data: " + json.dumps({"choices": [{"delta": {"content": "Hello "}}]}) + "\n\n"
        "data: " + json.dumps({"choices": [{"delta": {"content": "Nova"}}]}) + "\n\n"
        "data: [DONE]\n\n"
    ).encode()
    response = FakeStreamResponse(200, [events[:40], events[40:]])
    monkeypatch.setattr(llm_client.settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm_client.settings, "GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setattr(
        llm_client.httpx,
        "AsyncClient",
        lambda **_kwargs: FakeAsyncClient(response, capture),
    )

    output = asyncio.run(_collect(llm_client._stream_groq("question")))

    assert output == "Hello Nova"
    assert capture["json"]["model"] == "openai/gpt-oss-20b"
    assert capture["json"]["seed"] == llm_client.settings.LLM_SEED
    assert capture["headers"]["Authorization"] == "Bearer test-key"


def test_groq_stream_returns_public_errors_for_missing_key_and_http_failures(monkeypatch) -> None:
    monkeypatch.setattr(llm_client.settings, "GROQ_API_KEY", "")
    with pytest.raises(llm_client.LLMStreamError, match="GROQ_API_KEY not set"):
        asyncio.run(_collect(llm_client._stream_groq("q")))

    monkeypatch.setattr(llm_client.settings, "GROQ_API_KEY", "test-key")
    for status, expected in [(401, "Invalid Groq API key"), (429, "too many requests"), (503, "HTTP 503")]:
        response = FakeStreamResponse(status, [], b"provider-internal-detail")
        monkeypatch.setattr(
            llm_client.httpx,
            "AsyncClient",
            lambda response=response, **_kwargs: FakeAsyncClient(response, {}),
        )
        with pytest.raises(llm_client.LLMStreamError, match=expected) as exc:
            asyncio.run(_collect(llm_client._stream_groq("q")))
        assert "provider-internal-detail" not in str(exc.value)


def test_stream_tokens_routes_to_configured_provider(monkeypatch) -> None:
    async def fake_groq(_prompt: str):
        yield "groq"

    async def fake_ollama(_prompt: str):
        yield "ollama"

    monkeypatch.setattr(llm_client, "_stream_groq", fake_groq)
    monkeypatch.setattr(llm_client, "_stream_ollama", fake_ollama)
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "groq")
    assert asyncio.run(_collect(llm_client.stream_tokens("q"))) == "groq"
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "ollama")
    assert asyncio.run(_collect(llm_client.stream_tokens("q"))) == "ollama"


def test_provider_eof_without_completion_is_not_a_successful_answer(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "GROQ_API_KEY", "test-key")
    response = FakeStreamResponse(200, [b'data: {"choices":[{"delta":{"content":"partial answer"}}]}\n\n'])
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient(response, {}))
    with pytest.raises(llm_client.LLMStreamError, match="before completion"):
        asyncio.run(_collect(llm_client._stream_groq("question")))


def test_groq_usage_only_frame_does_not_discard_the_generated_answer(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "GROQ_API_KEY", "test-key")
    wire = (b'data:{"choices":[{"delta":{"content":"answer"}}]}\n\n'
            b'data: {"choices":[],"usage":{"completion_tokens":1}}\n\n'
            b'data: [DONE]\n\n')
    response = FakeStreamResponse(200, [wire])
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient(response, {}))
    assert asyncio.run(_collect(llm_client._stream_groq("question"))) == "answer"


def test_ollama_final_json_without_newline_and_split_utf8_is_complete(monkeypatch):
    wire = (json.dumps({"message": {"content": "Tiếng Việt"}}, ensure_ascii=False)
            + '\n{"done":true}').encode("utf-8")
    # Byte-sized delivery deliberately splits multibyte Vietnamese characters.
    response = FakeStreamResponse(200, [wire[index:index + 1] for index in range(len(wire))])
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient(response, {}))
    assert asyncio.run(_collect(llm_client._stream_ollama("question"))) == "Tiếng Việt"


@pytest.mark.parametrize("payload", [b'not json', b'[]', b'{"choices":null}', b'{"choices":[{"delta":{"content":42}}]}'])
def test_malformed_provider_event_cannot_be_silently_acknowledged(monkeypatch, payload):
    monkeypatch.setattr(llm_client.settings, "GROQ_API_KEY", "test-key")
    response = FakeStreamResponse(200, [b'data: ' + payload + b'\n\ndata: [DONE]\n\n'])
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient(response, {}))
    with pytest.raises(llm_client.LLMStreamError):
        asyncio.run(_collect(llm_client._stream_groq("question")))
