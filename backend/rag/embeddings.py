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


def _validated_rows(payload: dict, count: int) -> np.ndarray:
    """Reject malformed vectors/indices before they can corrupt dense rows."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or len(data) != count:
        raise ValueError("Embedding response has an invalid row count")
    by_index = {}
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Embedding response contains an invalid row")
        index, vector = item.get("index"), item.get("embedding")
        if type(index) is not int or index not in range(count) or index in by_index:
            raise ValueError("Embedding response indices do not match the inputs")
        if not isinstance(vector, list) or not vector or any(type(value) not in (int, float) for value in vector):
            raise ValueError("Embedding response contains an invalid vector")
        by_index[index] = vector
    with np.errstate(over="ignore", invalid="ignore"):
        rows = np.asarray([by_index[index] for index in range(count)], dtype=np.float32)
    if rows.ndim != 2 or rows.shape[1] == 0 or not np.isfinite(rows).all():
        raise ValueError("Embedding vectors must have equal non-empty finite dimensions")
    return rows


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
        return _validated_rows(data, 1)[0].tolist()
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
        return _validated_rows(data, len(texts))
    except Exception as e:
        logger.error("Failed to get embeddings batch: %s", e)
        return None
