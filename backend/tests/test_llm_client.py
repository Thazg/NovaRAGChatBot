import asyncio
import json

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
    assert "GROQ_API_KEY not set" in asyncio.run(_collect(llm_client._stream_groq("q")))

    monkeypatch.setattr(llm_client.settings, "GROQ_API_KEY", "test-key")
    for status, expected in [(401, "Invalid Groq API key"), (429, "too many requests"), (503, "HTTP 503")]:
        response = FakeStreamResponse(status, [], b"provider-internal-detail")
        monkeypatch.setattr(
            llm_client.httpx,
            "AsyncClient",
            lambda response=response, **_kwargs: FakeAsyncClient(response, {}),
        )
        output = asyncio.run(_collect(llm_client._stream_groq("q")))
        assert expected in output
        assert "provider-internal-detail" not in output


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
