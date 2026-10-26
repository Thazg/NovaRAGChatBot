import json
from contextlib import nullcontext

import pytest
from fastapi import HTTPException

from api.routes import documents
from config.settings import settings
from rag import rag_chain, vector_store
from services import document_lifecycle, remote_storage, index_jobs
from services.migrate_uploads import migrate_uploads


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "BASE_UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(vector_store, "BASE_INDEX_DIR", tmp_path / "indexes")
    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(settings, "B2_KEY_ID", "")
    monkeypatch.setattr(settings, "B2_APP_KEY", "")
    monkeypatch.setattr(remote_storage, "download_file", lambda *a: False)
    monkeypatch.setattr(remote_storage, "upload_file", lambda *a: False)
    monkeypatch.setattr(remote_storage, "delete_file", lambda *a: False)
    monkeypatch.setattr(remote_storage, "file_exists", lambda *a, **k: False)
    monkeypatch.setattr(remote_storage, "list_files", lambda *a, **k: [])
    monkeypatch.setattr(remote_storage, "list_file_info", lambda *a, **k: [])
    rag_chain.unload_vector_store("owner")
    directory = documents._user_uploads_dir("owner")
    yield directory
    rag_chain.unload_vector_store("owner")


def create_index(directory):
    (directory / "secret.txt").write_text("confidential nebula research", encoding="utf-8")
    documents._index_uploaded_file_locked(directory / "secret.txt", "owner")
    assert rag_chain.retrieve_context("nebula", "owner")


def test_failed_index_delete_is_hidden_immediately_and_retry_finishes(uploads, monkeypatch):
    create_index(uploads)
    persist = vector_store.HybridVectorStore.persist
    monkeypatch.setattr(vector_store.HybridVectorStore, "persist", lambda self: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(HTTPException) as error:
        documents._delete_document_locked("owner", "secret.txt")
    assert error.value.status_code == 500
    assert not (uploads / "secret.txt").exists()
    assert rag_chain.retrieve_context("nebula", "owner") == []
    # Even a direct reader of the old persisted snapshot observes the barrier.
    assert vector_store.load_vector_store("owner").documents == []
    monkeypatch.setattr(vector_store.HybridVectorStore, "persist", persist)
    assert documents._delete_document_locked("owner", "secret.txt") == {"status": "success"}
    assert documents._delete_document_locked("owner", "secret.txt") == {"status": "success"}
    # A delayed worker or restored cache must never revive the removed upload.
    (uploads / "secret.txt").write_text("confidential nebula research", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="deleted before"):
        documents._index_uploaded_file_locked(uploads / "secret.txt", "owner")
    documents._rebuild_full_index_locked("owner")
    assert rag_chain.retrieve_context("nebula", "owner") == []


def remote_adapter(monkeypatch):
    objects = {}
    monkeypatch.setattr(settings, "REDIS_URL", "redis://test")
    monkeypatch.setattr(index_jobs, "_user_index_lock", lambda user: nullcontext())
    monkeypatch.setattr(remote_storage, "download_bytes", lambda key, **kw: objects.get(key))
    def put(key, data):
        objects[key] = data
        return True
    monkeypatch.setattr(remote_storage, "upload_bytes", put)
    monkeypatch.setattr(remote_storage, "upload_file", lambda key, path: put(key, path.read_bytes()))
    monkeypatch.setattr(remote_storage, "file_exists", lambda key, **kw: key in objects)
    monkeypatch.setattr(remote_storage, "delete_file", lambda key: objects.pop(key, None) is not False)
    return objects


@pytest.mark.parametrize("mode", ["redis", "b2_only"])
def test_remote_delete_failure_is_retryable_and_blocks_other_replica(uploads, monkeypatch, tmp_path, mode):
    objects = remote_adapter(monkeypatch)
    if mode == "b2_only":
        monkeypatch.setattr(settings, "REDIS_URL", "")
        monkeypatch.setattr(settings, "B2_KEY_ID", "test-key")
        monkeypatch.setattr(settings, "B2_APP_KEY", "test-app-key")
    objects["uploads/owner/secret.txt"] = b"confidential nebula research"
    create_index(uploads)
    monkeypatch.setattr(remote_storage, "delete_file", lambda key: False)
    with pytest.raises(RuntimeError, match="delete durable"):
        documents._delete_document_locked("owner", "secret.txt")
    # Simulate a second host with neither local index nor local barriers.
    monkeypatch.setattr(vector_store, "BASE_INDEX_DIR", tmp_path / "replica")
    assert rag_chain.retrieve_context("nebula", "owner") == []
    monkeypatch.setattr(remote_storage, "delete_file", lambda key: objects.pop(key, None) is not False)
    assert documents._delete_document_locked("owner", "secret.txt")["status"] == "success"
    assert "uploads/owner/secret.txt" not in objects


def test_failure_to_publish_barrier_preserves_original_and_index(uploads, monkeypatch):
    objects = remote_adapter(monkeypatch)
    objects["uploads/owner/secret.txt"] = b"confidential nebula research"
    create_index(uploads)
    monkeypatch.setattr(remote_storage, "upload_bytes", lambda *args: False)
    with pytest.raises(RuntimeError, match="persist document deletion"):
        documents._delete_document_locked("owner", "secret.txt")
    assert (uploads / "secret.txt").exists()
    assert rag_chain.retrieve_context("nebula", "owner")


def test_clear_all_failure_is_hidden_and_retryable(uploads, monkeypatch):
    create_index(uploads)
    persist = vector_store.HybridVectorStore.persist
    monkeypatch.setattr(vector_store.HybridVectorStore, "persist", lambda self: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        documents._clear_all_documents_locked("owner")
    assert rag_chain.retrieve_context("nebula", "owner") == []
    monkeypatch.setattr(vector_store.HybridVectorStore, "persist", persist)
    documents._clear_all_documents_locked("owner")
    assert document_lifecycle.deleted_documents("owner") == {"secret.txt"}


def test_cutover_preserves_only_local_original_until_explicit_migration(uploads, monkeypatch):
    path = uploads / "only-copy.txt"
    path.write_text("valuable nebula evidence", encoding="utf-8")
    (uploads / "document_manifest.json").write_text(json.dumps({path.name: {"original_name": "My notes.txt"}}))
    objects = remote_adapter(monkeypatch)
    with pytest.raises(RuntimeError, match="require migration"):
        documents._rebuild_full_index_locked("owner")
    assert path.read_text() == "valuable nebula evidence"
    assert migrate_uploads("owner") == 1
    assert migrate_uploads("owner") == 0
    assert path.exists()
    assert objects["uploads/owner/only-copy.txt"] == path.read_bytes()
    assert json.loads(objects["uploads/owner/document_manifest.json"])[path.name]["original_name"] == "My notes.txt"
    monkeypatch.setattr(remote_storage, "list_files", lambda prefix, **kw: [k for k in objects if k.startswith(prefix)])
    documents._rebuild_full_index_locked("owner")
    assert rag_chain.retrieve_context("nebula", "owner")


def test_listing_merges_replica_cache_and_remote_and_hides_deleted(uploads, monkeypatch):
    (uploads / "first.txt").write_text("cached")
    document_lifecycle.mark_deleted("owner", {"deleted.txt"})
    monkeypatch.setattr(documents, "_load_chunk_counts", lambda user: {"first.txt": 1, "second.txt": 2})
    monkeypatch.setattr(remote_storage, "list_file_info", lambda *a, **k: [
        {"key": f"uploads/owner/{name}", "size": 123} for name in ["first.txt", "second.txt", "deleted.txt"]])
    listed = documents._list_upload_files("owner")
    assert [item["id"] for item in listed] == ["first.txt", "second.txt"]
    assert listed[1]["chunks"] == 2
    monkeypatch.setattr(settings, "REDIS_URL", "redis://test")
    monkeypatch.setattr(documents, "_load_manifest", lambda user: {})
    monkeypatch.setattr(index_jobs, "_user_index_lock", lambda user: nullcontext())
    monkeypatch.setattr(remote_storage, "download_bytes", lambda *a, **kw: None)
    def unavailable(*args, **kwargs):
        assert kwargs["required"]
        raise RuntimeError("storage offline")
    monkeypatch.setattr(remote_storage, "list_file_info", unavailable)
    with pytest.raises(RuntimeError, match="storage offline"):
        documents._list_upload_files("owner")


def test_migration_skips_deleted_ids_and_does_not_overwrite_conflicts(uploads, monkeypatch):
    (uploads / "deleted.txt").write_text("old cache")
    document_lifecycle.mark_deleted("owner", {"deleted.txt"})
    path = uploads / "conflict.txt"
    path.write_text("local original")
    objects = remote_adapter(monkeypatch)
    objects["uploads/owner/conflict.txt"] = b"different remote original"
    with pytest.raises(RuntimeError, match="Conflicting remote upload"):
        migrate_uploads("owner")
    assert path.read_text() == "local original"
    assert objects["uploads/owner/conflict.txt"] == b"different remote original"
    assert "uploads/owner/deleted.txt" not in objects
    assert json.loads(objects["index/owner/deleted_documents.json"]) == ["deleted.txt"]


def test_failed_migration_preserves_original_and_retries(uploads, monkeypatch):
    path = uploads / "original.txt"
    path.write_text("original evidence")
    objects = remote_adapter(monkeypatch)
    put_file = remote_storage.upload_file
    monkeypatch.setattr(remote_storage, "upload_file", lambda *a: False)
    with pytest.raises(RuntimeError, match="local original was preserved"):
        migrate_uploads("owner")
    assert path.read_text() == "original evidence"
    monkeypatch.setattr(remote_storage, "upload_file", put_file)
    assert migrate_uploads("owner") == 1
    assert objects["uploads/owner/original.txt"] == path.read_bytes()
