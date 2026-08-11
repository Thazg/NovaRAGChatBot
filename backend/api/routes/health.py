import asyncio
import time

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config.settings import settings

router = APIRouter()
_STARTED_AT = time.monotonic()
_READINESS_LOCK = asyncio.Lock()
_READINESS_CACHE: tuple[float, dict, int] | None = None


@router.get("")
@router.get("/")
@router.head("")
@router.head("/")
def health_check():
    if settings.LLM_PROVIDER == "groq":
        api_key_set = bool(settings.GROQ_API_KEY)
        if not api_key_set:
            overall = "degraded"
        else:
            overall = "healthy"
        return {
            "status": overall,
            "backend": "running",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "uptime_seconds": round(time.monotonic() - _STARTED_AT, 1),
            "llm_provider": "groq",
            "groq_api_key_set": api_key_set,
            "groq_model": settings.GROQ_MODEL,
            "embedding_model": settings.EMBEDDING_MODEL if settings.EMBEDDING_BASE_URL else None,
            "retrieval": "hybrid" if settings.EMBEDDING_BASE_URL else "bm25",
        }

    return {
        "status": "healthy",
        "backend": "running",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": round(time.monotonic() - _STARTED_AT, 1),
        "llm_provider": "ollama",
        "ollama": "configured",
        "model": settings.MODEL_NAME,
        "embedding_model": settings.EMBEDDING_MODEL if settings.EMBEDDING_BASE_URL else None,
        "retrieval": "hybrid" if settings.EMBEDDING_BASE_URL else "bm25",
    }


async def _probe_provider() -> tuple[dict, int]:
    base = {
        "backend": "running",
        "version": settings.APP_VERSION,
        "llm_provider": settings.LLM_PROVIDER,
        "checked_at": int(time.time()),
    }

    if settings.LLM_PROVIDER == "groq":
        if not settings.GROQ_API_KEY:
            return ({
                **base,
                "status": "degraded",
                "ready": False,
                "provider_status": "not_configured",
                "message": "GROQ_API_KEY is not configured.",
            }, 503)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=5.0)) as client:
                response = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                )
            if response.status_code == 200:
                model_ids = {
                    model.get("id")
                    for model in response.json().get("data", [])
                    if isinstance(model, dict)
                }
                model_available = settings.GROQ_MODEL in model_ids
                return ({
                    **base,
                    "status": "ready" if model_available else "degraded",
                    "ready": model_available,
                    "provider_status": "reachable",
                    "model": settings.GROQ_MODEL,
                    "model_available": model_available,
                    "message": "AI provider is ready." if model_available else "Configured model is unavailable.",
                }, 200 if model_available else 503)

            status = "unauthorized" if response.status_code in (401, 403) else "error"
            return ({
                **base,
                "status": "degraded",
                "ready": False,
                "provider_status": status,
                "provider_http_status": response.status_code,
                "message": "AI provider rejected the readiness check.",
            }, 503)
        except httpx.TimeoutException:
            provider_status = "timeout"
        except httpx.HTTPError:
            provider_status = "unreachable"

        return ({
            **base,
            "status": "degraded",
            "ready": False,
            "provider_status": provider_status,
            "message": "AI provider cannot be reached.",
        }, 503)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
            response = await client.get(f"{settings.OLLAMA_URL.rstrip('/')}/api/tags")
        ready = response.status_code == 200
        return ({
            **base,
            "status": "ready" if ready else "degraded",
            "ready": ready,
            "provider_status": "reachable" if ready else "error",
            "model": settings.MODEL_NAME,
            "message": "Ollama is ready." if ready else "Ollama returned an error.",
        }, 200 if ready else 503)
    except httpx.HTTPError:
        return ({
            **base,
            "status": "degraded",
            "ready": False,
            "provider_status": "unreachable",
            "model": settings.MODEL_NAME,
            "message": "Ollama cannot be reached.",
        }, 503)


@router.get("/ready")
async def readiness_check(refresh: bool = False):
    """Verify that the configured LLM provider and model are actually usable."""
    global _READINESS_CACHE
    now = time.monotonic()
    if not refresh and _READINESS_CACHE and now - _READINESS_CACHE[0] < settings.READINESS_CACHE_SECONDS:
        _, payload, status_code = _READINESS_CACHE
        return JSONResponse(payload, status_code=status_code, headers={"X-Readiness-Cache": "HIT"})

    async with _READINESS_LOCK:
        now = time.monotonic()
        if not refresh and _READINESS_CACHE and now - _READINESS_CACHE[0] < settings.READINESS_CACHE_SECONDS:
            _, payload, status_code = _READINESS_CACHE
            return JSONResponse(payload, status_code=status_code, headers={"X-Readiness-Cache": "HIT"})
        payload, status_code = await _probe_provider()
        _READINESS_CACHE = (time.monotonic(), payload, status_code)
        return JSONResponse(payload, status_code=status_code, headers={"X-Readiness-Cache": "MISS"})
