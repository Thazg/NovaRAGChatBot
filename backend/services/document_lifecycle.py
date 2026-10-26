"""Permanent deletion barriers, independent of index publication.

Writers hold the per-user index lock. Readers resolve this small record before
using cached evidence so a failed index write cannot expose a deleted upload.
Storage IDs are never reused; tombstones must survive reindex and clear-all.
"""
import json


def deleted_documents(user_id: str) -> set[str]:
    from rag.vector_store import _index_dir, _remote_enabled
    path = _index_dir(user_id) / "deleted_documents.json"
    local = set(json.loads(path.read_bytes())) if path.exists() else set()
    if _remote_enabled():
        from services.remote_storage import download_bytes
        data = download_bytes(f"index/{user_id}/deleted_documents.json", required=True)
        local.update(json.loads(data) if data else [])
    return local


def mark_deleted(user_id: str, names: set[str]) -> None:
    from rag.vector_store import _index_dir, _remote_enabled, _atomic_write
    deleted = deleted_documents(user_id) | names
    data = json.dumps(sorted(deleted)).encode()
    if _remote_enabled():
        from services.remote_storage import upload_bytes
        if not upload_bytes(f"index/{user_id}/deleted_documents.json", data):
            raise RuntimeError("Could not persist document deletion; no upload was removed")
    _atomic_write(_index_dir(user_id) / "deleted_documents.json", data)


def storage_name(node: dict) -> str:
    metadata = node.get("metadata", {})
    return metadata.get("storage_name") or metadata.get("file_name", "")
