import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from rag import rag_chain, vector_store
from services import remote_storage
from api.routes import documents
from config.settings import settings


def node(text, name):
    return {"content": text, "metadata": {"file_name": name, "storage_name": name}}


@pytest.fixture
def local_indexes(tmp_path, monkeypatch):
    monkeypatch.setattr(vector_store, "BASE_INDEX_DIR", tmp_path / "index")
    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(settings, "B2_KEY_ID", "")
    monkeypatch.setattr(settings, "B2_APP_KEY", "")
    rag_chain.unload_vector_store("owner")
    yield tmp_path
    rag_chain.unload_vector_store("owner")


def test_cached_queries_observe_external_updates_and_empty_revision(local_indexes):
    vector_store.build_vector_store([node("alpha research evidence", "a.txt")], "owner")
    assert rag_chain.retrieve_context("beta", "owner") == []
    old_reader = rag_chain.get_retriever("owner")
    # Independent store object models a writer outside the API's memory cache.
    writer = vector_store.load_vector_store("owner")
    writer.add_nodes([node("beta fusion evidence", "b.txt")])
    writer.persist()
    assert rag_chain.retrieve_context("beta", "owner")[0]["metadata"]["file_name"] == "b.txt"
    assert rag_chain.get_retriever("owner") is not old_reader
    vector_store.delete_vector_store("owner")
    assert rag_chain.retrieve_context("beta", "owner") == []


def test_stale_writer_cannot_replace_a_new_revision(local_indexes):
    vector_store.build_vector_store([node("alpha evidence", "a.txt")], "owner")
    stale = vector_store.load_vector_store("owner")
    fresh = vector_store.load_vector_store("owner")
    fresh.add_nodes([node("beta evidence", "b.txt")])
    fresh.persist()
    stale.add_nodes([node("gamma evidence", "c.txt")])
    with pytest.raises(RuntimeError, match="Index changed"):
        stale.persist()
    assert len(vector_store.load_vector_store("owner").documents) == 2


def test_failed_durable_write_never_publishes_partial_snapshot(local_indexes, monkeypatch):
    objects = {}
    monkeypatch.setattr(settings, "REDIS_URL", "redis://test")
    monkeypatch.setattr(remote_storage, "download_bytes", lambda key, **kwargs: objects.get(key))
    monkeypatch.setattr(remote_storage, "upload_file", lambda key, path: objects.setdefault(key, path.read_bytes()) is not None)
    monkeypatch.setattr(remote_storage, "upload_bytes", lambda key, data: objects.setdefault(key, data) is not None)
    store = vector_store.build_vector_store([node("alpha evidence", "a.txt")], "owner")
    original = objects["index/owner/current.json"]
    store.add_nodes([node("beta evidence", "b.txt")])
    monkeypatch.setattr(remote_storage, "upload_file", lambda *args: False)
    with pytest.raises(RuntimeError, match="complete index"):
        store.persist()
    assert objects["index/owner/current.json"] == original
    assert len(vector_store.load_vector_store("owner").documents) == 1
    monkeypatch.setattr(remote_storage, "download_bytes", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("storage offline")))
    with pytest.raises(RuntimeError, match="storage offline"):
        rag_chain.get_retriever("owner")


def test_distributed_reindex_cannot_restore_deleted_local_uploads(local_indexes, monkeypatch):
    monkeypatch.setattr(documents, "BASE_UPLOADS_DIR", local_indexes / "uploads")
    monkeypatch.setattr(settings, "REDIS_URL", "redis://test")
    monkeypatch.setattr(remote_storage, "download_bytes", lambda key, **kwargs:
                        b'["deleted.txt"]' if key.endswith("deleted_documents.json") else None)
    directory = documents._user_uploads_dir("owner")
    (directory / "deleted.txt").write_text("stale local copy", encoding="utf-8")
    (directory / "document_manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(remote_storage, "list_files", lambda *args, **kwargs: ["uploads/owner/current.txt"])
    def download(key, destination):
        destination.write_text("current durable text", encoding="utf-8")
        return True
    monkeypatch.setattr(remote_storage, "download_file", download)
    documents._restore_remote_uploads("owner")
    # Hydration never destroys local originals, even for a stale deleted cache.
    assert (directory / "deleted.txt").exists()
    assert (directory / "current.txt").read_text(encoding="utf-8") == "current durable text"
    assert (directory / "document_manifest.json").exists()
    monkeypatch.setattr(remote_storage, "file_exists", lambda *args, **kwargs: False)
    with pytest.raises(FileNotFoundError, match="deleted before"):
        documents._index_uploaded_file_locked(directory / "current.txt", "owner", "current.txt")


def test_reindex_storage_failure_does_not_publish_an_empty_index(local_indexes, monkeypatch):
    monkeypatch.setattr(documents, "BASE_UPLOADS_DIR", local_indexes / "uploads")
    monkeypatch.setattr(settings, "REDIS_URL", "redis://test")
    path = documents._user_uploads_dir("owner") / "current.txt"
    path.write_text("valuable evidence", encoding="utf-8")
    def fail(*args, **kwargs):
        raise RuntimeError("storage unavailable")
    monkeypatch.setattr(remote_storage, "list_files", fail)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        documents._rebuild_full_index_locked("owner")
    assert path.read_text(encoding="utf-8") == "valuable evidence"
    assert not vector_store._pointer_file("owner").exists()


def test_corrupt_remote_snapshot_is_not_used_as_fresh_evidence(local_indexes, monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "redis://test")
    manifest = {"revision": "a" * 32, "files": {"metadata.jsonl": "b" * 64}}
    monkeypatch.setattr(remote_storage, "download_bytes", lambda key, **kwargs:
        json.dumps(manifest).encode() if key.endswith("current.json") else b'corrupt')
    with pytest.raises(RuntimeError, match="incomplete or corrupt"):
        vector_store.load_vector_store("owner")
    assert not vector_store._pointer_file("owner").exists()


def test_separate_processes_hydrate_latest_snapshot_on_separate_local_disks(local_indexes):
    # The filesystem object-store adapter crosses an actual process boundary;
    # neither the reader nor writer can share Python globals/local index files.
    script = r'''
import json, sys
from pathlib import Path
from config.settings import settings
from rag import rag_chain, vector_store
from services import remote_storage
root, host, action = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
settings.REDIS_URL = "redis://test"
settings.RETRIEVAL_MODE = "bm25"
vector_store.BASE_INDEX_DIR = root / host
def read(key, **kwargs):
    path = root / "objects" / key
    return path.read_bytes() if path.exists() else None
def put(key, data):
    path = root / "objects" / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True
remote_storage.download_bytes = read
remote_storage.upload_bytes = put
remote_storage.upload_file = lambda key, path: put(key, path.read_bytes())
if action == "create":
    vector_store.build_vector_store([{"content": "alpha research", "metadata": {"file_name": "a.txt"}}], "owner")
elif action == "append":
    store = vector_store.load_vector_store("owner")
    store.add_nodes([{"content": "beta fusion", "metadata": {"file_name": "b.txt"}}])
    store.persist()
elif action == "clear":
    vector_store.delete_vector_store("owner")
else:
    print(json.dumps([d["content"] for d in rag_chain.get_retriever("owner").documents]))
'''
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1])}
    def run(host, action):
        return subprocess.check_output([sys.executable, "-c", script, str(local_indexes), host, action], env=env, text=True)
    run("worker-a", "create")
    assert json.loads(run("api", "read")) == ["alpha research"]
    run("worker-b", "append")
    assert json.loads(run("api", "read")) == ["alpha research", "beta fusion"]
    run("worker-a", "clear")
    assert json.loads(run("api", "read")) == []
