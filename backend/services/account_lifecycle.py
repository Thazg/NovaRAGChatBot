"""Monotonic write barrier for retryable account cleanup.

The UUID-only marker deliberately survives removal of per-user artifacts. It
prevents old streams/jobs from recreating data, and is not an account record.
All mutations acquire the same user lock before checking it.
"""
import inspect
import json
from functools import wraps
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1] / "storage" / "account-deletions"


class AccountDeletionPending(RuntimeError):
    pass


def deletion_pending(user_id: str) -> bool:
    from rag.vector_store import _remote_enabled
    path = BASE_DIR / f"{user_id}.json"
    if path.exists():
        return True
    if _remote_enabled():
        from services.remote_storage import download_bytes
        data = download_bytes(f"account-deletions/{user_id}.json", required=True)
        if data is not None:
            if json.loads(data) != {"deleting": True}:
                raise RuntimeError("Invalid account deletion barrier")
            return True
    return False


def ensure_writable(user_id: str) -> None:
    if deletion_pending(user_id):
        raise AccountDeletionPending("Account deletion is pending. Retry deleting the account.")


def mark_deleting(user_id: str) -> None:
    from rag.vector_store import _atomic_write, _remote_enabled
    data = b'{"deleting": true}'
    if _remote_enabled():
        from services.remote_storage import upload_bytes
        if not upload_bytes(f"account-deletions/{user_id}.json", data):
            raise RuntimeError("Could not persist account deletion barrier")
    _atomic_write(BASE_DIR / f"{user_id}.json", data)


def account_mutation(function):
    """Serialize account access with cleanup, reusing a held thread lease."""
    signature = inspect.signature(function)

    @wraps(function)
    def guarded(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        user_id = bound.arguments["user_id"]
        from services.index_jobs import _user_index_lock
        with _user_index_lock(user_id):
            ensure_writable(user_id)
            return function(*args, **kwargs)
    return guarded


def account_lock(function):
    """Serialize read-side cache hydration with deletion, without forcing writes."""
    signature = inspect.signature(function)
    @wraps(function)
    def guarded(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        from services.index_jobs import _user_index_lock
        with _user_index_lock(bound.arguments["user_id"]):
            return function(*args, **kwargs)
    return guarded
