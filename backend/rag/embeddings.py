import logging
import httpx
import numpy as np
from config.settings import settings

logger = logging.getLogger(__name__)

_embedding_client = None


def _get_client():
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = httpx.Client(timeout=120.0)
    return _embedding_client


def get_embedding(text: str, prefix: str = "search_document:") -> list[float] | None:
    if not settings.EMBEDDING_BASE_URL:
        return None
    headers = {
        "Content-Type": "application/json",
    }
    if settings.EMBEDDING_API_KEY:
        headers["Authorization"] = f"Bearer {settings.EMBEDDING_API_KEY}"
    payload = {
        "model": settings.EMBEDDING_MODEL,
        "input": [prefix + text],
    }
    try:
        client = _get_client()
        resp = client.post(f"{settings.EMBEDDING_BASE_URL}/embeddings", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        logger.error("Failed to get embedding: %s", e)
        return None


def get_embeddings_batch(texts: list[str], prefix: str = "search_document:") -> np.ndarray | None:
    if not texts:
        return None
    if not settings.EMBEDDING_BASE_URL:
        return None
    headers = {
        "Content-Type": "application/json",
    }
    if settings.EMBEDDING_API_KEY:
        headers["Authorization"] = f"Bearer {settings.EMBEDDING_API_KEY}"
    prefixed = [prefix + t for t in texts]
    payload = {
        "model": settings.EMBEDDING_MODEL,
        "input": prefixed,
    }
    try:
        client = _get_client()
        resp = client.post(f"{settings.EMBEDDING_BASE_URL}/embeddings", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        return np.array([item["embedding"] for item in sorted_data], dtype=np.float32)
    except Exception as e:
        logger.error("Failed to get embeddings batch: %s", e)
        return None
