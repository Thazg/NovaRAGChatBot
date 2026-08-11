from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

from services.database import DATABASE_ENABLED

_STORE = Path(__file__).resolve().parents[1] / "storage" / "refresh_sessions.json"
_LOCK = threading.RLock()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load() -> dict[str, dict]:
    try:
        payload = json.loads(_STORE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _save(payload: dict[str, dict]) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    temporary = _STORE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, _STORE)


def issue(token: str, user_id: str, expires_at: float) -> None:
    token_hash = _token_hash(token)
    if DATABASE_ENABLED:
        from services.postgres_store import issue_refresh_session
        issue_refresh_session(token_hash, user_id, expires_at)
        return
    with _LOCK:
        payload = {
            key: value for key, value in _load().items()
            if float(value.get("expires_at", 0)) > time.time() and not value.get("revoked")
        }
        payload[token_hash] = {"user_id": user_id, "expires_at": expires_at, "revoked": False}
        _save(payload)


def consume(token: str, user_id: str) -> bool:
    token_hash = _token_hash(token)
    if DATABASE_ENABLED:
        from services.postgres_store import consume_refresh_session
        return consume_refresh_session(token_hash, user_id)
    with _LOCK:
        payload = _load()
        record = payload.get(token_hash)
        if (
            not record
            or record.get("user_id") != user_id
            or record.get("revoked")
            or float(record.get("expires_at", 0)) <= time.time()
        ):
            return False
        record["revoked"] = True
        _save(payload)
        return True


def revoke(token: str) -> None:
    if not token:
        return
    token_hash = _token_hash(token)
    if DATABASE_ENABLED:
        from services.postgres_store import revoke_refresh_session
        revoke_refresh_session(token_hash)
        return
    with _LOCK:
        payload = _load()
        if token_hash in payload:
            payload[token_hash]["revoked"] = True
            _save(payload)
