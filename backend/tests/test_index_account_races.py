import shutil
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from config.settings import settings
from rag import rag_chain, vector_store
from services import account_lifecycle, remote_storage
from services.index_jobs import _user_index_lock


@pytest.fixture
def remote_index(tmp_path, monkeypatch):
    # B2-only mode exercises durable artifacts without a real Redis server.
    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(settings, "B2_KEY_ID", "adapter-key")
    monkeypatch.setattr(settings, "B2_APP_KEY", "adapter-secret")
    monkeypatch.setattr(settings, "RETRIEVAL_MODE", "bm25")
    monkeypatch.setattr(account_lifecycle, "BASE_DIR", tmp_path / "barriers")
    monkeypatch.setattr(vector_store, "BASE_INDEX_DIR", tmp_path / "writer")
    objects = {}
    def put(key, data):
        objects[key] = data
        return True
    monkeypatch.setattr(remote_storage, "upload_bytes", put)
    monkeypatch.setattr(remote_storage, "upload_file", lambda key, path: put(key, path.read_bytes()))
    monkeypatch.setattr(remote_storage, "download_bytes", lambda key, **_kwargs: objects.get(key))
    user_id = "7d6c25cb-f087-4c36-871a-6972f074df12"
    rag_chain.unload_vector_store(user_id)
    vector_store.build_vector_store([{
        "content": "private nebula evidence",
        "metadata": {"file_name": "secret.txt", "storage_name": "secret.txt"},
    }], user_id)
    monkeypatch.setattr(vector_store, "BASE_INDEX_DIR", tmp_path / "reader")
    yield user_id, objects, tmp_path / "reader" / user_id
    rag_chain.unload_vector_store(user_id)


def test_account_cleanup_waits_for_hydration_then_removes_its_cache(remote_index, monkeypatch):
    user_id, objects, directory = remote_index
    captured = threading.Event()
    resume = threading.Event()
    cleanup_attempted = threading.Event()
    cleanup_finished = threading.Event()
    order = []

    def read(key, **_kwargs):
        data = objects.get(key)
        if key.endswith("/metadata.jsonl"):
            # Hold bytes captured BEFORE deletion; a second lookup after the
            # cleanup would conceal the late cache-publication race.
            captured.set()
            assert resume.wait(5), "test must release the paused reader"
            order.append("reader_resumed")
        return data
    monkeypatch.setattr(remote_storage, "download_bytes", read)

    def cleanup():
        cleanup_attempted.set()
        with _user_index_lock(user_id):
            order.append("cleanup_started")
            account_lifecycle.mark_deleting(user_id)
            shutil.rmtree(directory, ignore_errors=True)
            for key in list(objects):
                if key.startswith(f"index/{user_id}/"):
                    del objects[key]
            rag_chain.unload_vector_store(user_id)
            cleanup_finished.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        reader = executor.submit(vector_store.load_vector_store, user_id)
        assert captured.wait(5), "reader must reach remote hydration"
        writer = executor.submit(cleanup)
        try:
            assert cleanup_attempted.wait(5)
            assert not cleanup_finished.wait(0.1), "cleanup must wait for the in-flight cache writer"
        finally:
            resume.set()
        # An already-authorized read may finish, but cleanup must remove its
        # output before acknowledging deletion and prevent all future loads.
        assert reader.result(timeout=5).documents
        writer.result(timeout=5)

    assert order.index("reader_resumed") < order.index("cleanup_started")
    assert cleanup_finished.is_set()
    assert not directory.exists()
    assert account_lifecycle.deletion_pending(user_id)
    for load in (vector_store.load_vector_store, rag_chain.get_retriever, rag_chain.reload_vector_store):
        with pytest.raises(account_lifecycle.AccountDeletionPending):
            load(user_id)
    assert not directory.exists()


def test_warm_retriever_and_query_caches_respect_account_barrier(remote_index):
    user_id, _objects, _directory = remote_index
    assert rag_chain.get_retriever(user_id).documents
    assert rag_chain.retrieve_context("nebula", user_id)
    with _user_index_lock(user_id):
        account_lifecycle.mark_deleting(user_id)
    # Both caches were populated before deletion began; neither may bypass
    # the barrier merely because the index revision did not change.
    with pytest.raises(account_lifecycle.AccountDeletionPending):
        rag_chain.get_retriever(user_id)
    with pytest.raises(account_lifecycle.AccountDeletionPending):
        rag_chain.retrieve_context("nebula", user_id)
