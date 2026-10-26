import importlib

import pytest

import rebuild_index
from api.routes import documents
from config.settings import settings
from rag import load, rag_chain, vector_store
from services import auth, remote_storage, account_lifecycle


def test_import_does_not_rebuild_or_load_uploads(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Importing the CLI must not read uploads or publish an index")
    monkeypatch.setattr(load, "load_documents", forbidden)
    monkeypatch.setattr(documents, "_rebuild_full_index", forbidden)
    importlib.reload(rebuild_index)


@pytest.mark.parametrize("user_id", ["", "../other", "a/b", "a\\b", "__anonymous__", "."])
def test_invalid_account_id_fails_before_looking_up_or_writing(monkeypatch, user_id):
    monkeypatch.setattr(auth, "user_exists", lambda uid: pytest.fail("Invalid paths must not reach account storage"))
    with pytest.raises(ValueError):
        rebuild_index.rebuild_index(user_id)


def test_required_or_unknown_account_cannot_publish_an_index(monkeypatch):
    with pytest.raises(SystemExit) as missing:
        rebuild_index.main([])
    assert missing.value.code == 2
    monkeypatch.setattr(auth, "user_exists", lambda uid: False)
    monkeypatch.setattr(documents, "_rebuild_full_index", lambda uid: pytest.fail("Missing account must not be indexed"))
    with pytest.raises(LookupError, match="Account not found"):
        rebuild_index.rebuild_index("missing-account")


def test_rebuild_reads_only_selected_account_and_preserves_other_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(settings, "B2_KEY_ID", "")
    monkeypatch.setattr(settings, "B2_APP_KEY", "")
    monkeypatch.setattr(documents, "BASE_UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(vector_store, "BASE_INDEX_DIR", tmp_path / "indexes")
    monkeypatch.setattr(account_lifecycle, "BASE_DIR", tmp_path / "deletions")
    monkeypatch.setattr(auth, "user_exists", lambda uid: uid in {"owner", "other"})
    monkeypatch.setattr(remote_storage, "download_file", lambda *args: False)
    monkeypatch.setattr(remote_storage, "list_files", lambda *args, **kwargs: [])
    owner = documents._user_uploads_dir("owner") / "owner.txt"
    other = documents._user_uploads_dir("other") / "other.txt"
    owner.write_text("Owner nebula evidence", encoding="utf-8")
    other.write_text("Other confidential evidence", encoding="utf-8")
    monkeypatch.setattr(load, "load_documents", lambda: pytest.fail("Never recurse across account directories"))
    try:
        assert rebuild_index.rebuild_index("owner") == (1, 1)
        store = vector_store.load_vector_store("owner")
        assert [node["metadata"]["storage_name"] for node in store.documents] == ["owner.txt"]
        assert "confidential" not in store.documents[0]["content"]
        assert other.read_text(encoding="utf-8") == "Other confidential evidence"
        assert not vector_store._pointer_file("other").exists()
    finally:
        rag_chain.unload_vector_store("owner")
