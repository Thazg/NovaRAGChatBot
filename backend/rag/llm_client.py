"""Unified LLM client supporting Ollama (local) and Groq (cloud-free)."""

from __future__ import annotations

import json
import codecs
import logging
from typing import AsyncIterator

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

class LLMStreamError(RuntimeError):
    """Public provider failure; never a successful answer token."""


_CHAT_TIMEOUT = httpx.Timeout(300.0, connect=30.0)


async def stream_tokens(prompt: str) -> AsyncIterator[str]:
    if settings.LLM_PROVIDER == "groq":
        async for token in _stream_groq(prompt):
            yield token
    else:
        async for token in _stream_ollama(prompt):
            yield token


async def _provider_lines(response):
    """Decode split UTF-8 and accept a final JSON line without a newline."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    buffer = ""
    try:
        async for chunk in response.aiter_bytes():
            buffer += decoder.decode(chunk)
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if line.strip():
                    yield line.strip()
        buffer += decoder.decode(b"", final=True)
    except UnicodeDecodeError as exc:
        raise LLMStreamError("AI provider returned invalid UTF-8") from exc
    if buffer.strip():
        yield buffer.strip()


def _provider_event(payload, provider):
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise LLMStreamError(f"{provider} returned a malformed stream event") from exc
    if not isinstance(data, dict):
        raise LLMStreamError(f"{provider} returned a malformed stream event")
    if data.get("error"):
        raise LLMStreamError(f"{provider} reported a stream error")
    return data


async def _stream_ollama(prompt: str) -> AsyncIterator[str]:
    payload = {
        "model": settings.MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": settings.TEMPERATURE,
            "top_k": settings.LLM_TOP_K,
            "top_p": settings.LLM_TOP_P,
            "seed": settings.LLM_SEED,
            "num_ctx": settings.NUM_CTX,
            "num_predict": settings.MAX_TOKENS,
        },
    }

    url = f"{settings.OLLAMA_URL.rstrip('/')}/api/chat"

    try:
        async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    logger.error("Ollama HTTP %s: %s", response.status_code, body[:300])
                    raise LLMStreamError(f"Ollama HTTP {response.status_code}")

                async for line in _provider_lines(response):
                    data = _provider_event(line, "Ollama")
                    message = data.get("message") or {}
                    if not isinstance(message, dict):
                        raise LLMStreamError("Ollama returned a malformed message")
                    token = message.get("content")
                    if token is not None and not isinstance(token, str):
                        raise LLMStreamError("Ollama returned a malformed token")
                    if token:
                        yield token
                    if data.get("done") is True:
                        return

                raise LLMStreamError("Ollama response ended before completion")
    except LLMStreamError:
        raise
    except httpx.HTTPError as exc:
        logger.warning("Ollama stream failed: %s", type(exc).__name__)
        raise LLMStreamError("Ollama connection was interrupted") from exc


async def _stream_groq(prompt: str) -> AsyncIterator[str]:
    api_key = settings.GROQ_API_KEY
    if not api_key:
        raise LLMStreamError("GROQ_API_KEY not set")

    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "temperature": settings.TEMPERATURE,
        "max_tokens": settings.MAX_TOKENS,
        "top_p": settings.LLM_TOP_P,
        "seed": settings.LLM_SEED,
    }

    try:
        async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
            async with client.stream(
                "POST",
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status_code == 401:
                    raise LLMStreamError("Invalid Groq API key")
                if response.status_code == 429:
                    raise LLMStreamError("AI provider received too many requests")
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    logger.error("Groq HTTP %s: %s", response.status_code, body[:300])
                    raise LLMStreamError(f"AI provider HTTP {response.status_code}")

                async for line in _provider_lines(response):
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].lstrip(" ")
                    if data_str.strip() == "[DONE]":
                        return
                    data = _provider_event(data_str, "Groq")
                    choices = data.get("choices", [])
                    if not isinstance(choices, list):
                        raise LLMStreamError("Groq returned malformed choices")
                    # Usage-only events have an empty choices list and must not
                    # turn a successfully generated response into an IndexError.
                    if not choices:
                        continue
                    choice = choices[0]
                    if not isinstance(choice, dict) or not isinstance(choice.get("delta", {}), dict):
                        raise LLMStreamError("Groq returned a malformed delta")
                    token = choice.get("delta", {}).get("content")
                    if token is not None and not isinstance(token, str):
                        raise LLMStreamError("Groq returned a malformed token")
                    if token:
                        yield token
                raise LLMStreamError("AI provider response ended before completion")
    except LLMStreamError:
        raise
    except httpx.HTTPError as exc:
        logger.warning("Groq stream failed: %s", type(exc).__name__)
        raise LLMStreamError("AI provider connection was interrupted") from exc


async def warmup_model() -> None:
    """Warmup for Ollama (keeps model in memory). No-op for Groq."""
    if settings.LLM_PROVIDER != "ollama":
        return
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            await client.post(
                f"{settings.OLLAMA_URL.rstrip('/')}/api/generate",
                json={
                    "model": settings.MODEL_NAME,
                    "prompt": "",
                    "keep_alive": settings.OLLAMA_KEEP_ALIVE,
                },
            )
            logger.info("Ollama model '%s' warmed up.", settings.MODEL_NAME)
    except Exception as exc:
        logger.warning("Ollama warmup skipped: %s", exc)
