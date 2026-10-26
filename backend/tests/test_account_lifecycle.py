import json
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient

from app import app
from api.routes import documents
from config.settings import settings
from rag import vector_store, rag_chain
from services import account_lifecycle, auth, conversation_store, index_jobs, refresh_sessions, remote_storage, user_preferences


@pytest.fixture
def account(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(settings, "B2_KEY_ID", "")
    monkeypatch.setattr(settings, "B2_APP_KEY", "")
    monkeypatch.setattr(auth, "DATABASE_ENABLED", False)
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(account_lifecycle, "BASE_DIR", tmp_path / "barriers")
    monkeypatch.setattr(documents, "BASE_UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(vector_store, "BASE_INDEX_DIR", tmp_path / "index")
    monkeypatch.setattr(conversation_store, "BASE_DIR", tmp_path / "sessions")
    monkeypatch.setattr(user_preferences, "BASE_DIR", tmp_path / "preferences")
    monkeypatch.setattr(refresh_sessions, "_STORE", tmp_path / "refresh.json")
    monkeypatch.setattr(remote_storage, "download_file", lambda *args: False)
    monkeypatch.setattr(remote_storage, "upload_file", lambda *args: False)
    monkeypatch.setattr(remote_storage, "list_files", lambda *args, **kwargs: [])
    monkeypatch.setattr(remote_storage, "delete_file", lambda *args: False)
    result = auth.register("cleanup.user", "strong-password")
    user_id = result["user_id"]
    (documents._user_uploads_dir(user_id) / "private.txt").write_text("private original")
    conversation_store.append_session_message("session", "user", "private message", user_id)
    user_preferences.save_preferences(user_id, {"nickname": "private nickname"})
    yield result
    rag_chain.unload_vector_store(user_id)


def test_local_account_cleanup_blocks_delayed_writes_and_jobs(account):
    user_id = account["user_id"]
    assert auth.delete_user(user_id)
    assert not auth.user_exists(user_id)
    assert account_lifecycle.deletion_pending(user_id)
    assert not (documents.BASE_UPLOADS_DIR / user_id).exists()
    assert not (conversation_store.BASE_DIR / user_id).exists()
    assert not (user_preferences.BASE_DIR / f"{user_id}.json").exists()
    with pytest.raises(account_lifecycle.AccountDeletionPending):
        conversation_store.append_session_message("session", "assistant", "late reply", user_id)
    with pytest.raises(account_lifecycle.AccountDeletionPending):
        user_preferences.save_preferences(user_id, {})
    with pytest.raises(account_lifecycle.AccountDeletionPending):
        index_jobs.process_file_index(user_id, "/other-host/private.txt", "private.txt")
    with pytest.raises(account_lifecycle.AccountDeletionPending):
        index_jobs.process_full_reindex(user_id)
    assert not (documents.BASE_UPLOADS_DIR / user_id).exists()


def remote_objects(monkeypatch):
    objects = {}
    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(settings, "B2_KEY_ID", "test-key")
    monkeypatch.setattr(settings, "B2_APP_KEY", "test-app-key")
    monkeypatch.setattr(index_jobs, "_user_index_lock", lambda user: nullcontext())
    monkeypatch.setattr(remote_storage, "download_bytes", lambda key, **kw: objects.get(key))
    def put(key, data):
        objects[key] = data
        return True
    monkeypatch.setattr(remote_storage, "upload_bytes", put)
    monkeypatch.setattr(remote_storage, "upload_file", lambda key, path: put(key, path.read_bytes()))
    monkeypatch.setattr(remote_storage, "list_files", lambda prefix, **kw: [key for key in objects if key.startswith(prefix)])
    monkeypatch.setattr(remote_storage, "delete_file", lambda key: objects.pop(key, None) is not False)
    return objects


def test_remote_cleanup_failure_retains_owner_and_can_be_retried(account, monkeypatch, tmp_path):
    user_id = account["user_id"]
    objects = remote_objects(monkeypatch)
    key = f"uploads/{user_id}/private.txt"
    objects[key] = b"private original"
    delete = remote_storage.delete_file
    monkeypatch.setattr(remote_storage, "delete_file", lambda key: False)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    first = client.delete("/auth/account", headers=headers)
    assert first.status_code == 503
    assert auth.user_exists(user_id)
    assert key in objects
    assert account_lifecycle.deletion_pending(user_id)
    assert client.patch("/auth/preferences", headers=headers, json={"theme": "light"}).status_code == 409
    # Another host with no local marker must read the durable barrier too.
    monkeypatch.setattr(account_lifecycle, "BASE_DIR", tmp_path / "another-host")
    with pytest.raises(account_lifecycle.AccountDeletionPending):
        conversation_store.append_session_message("session", "assistant", "late", user_id)
    monkeypatch.setattr(remote_storage, "delete_file", delete)
    second = client.delete("/auth/account", headers=headers)
    assert second.status_code == 200
    assert not auth.user_exists(user_id)
    assert key not in objects
    assert objects[f"account-deletions/{user_id}.json"]
    assert all(record["user_id"] != user_id for record in json.loads(objects["data/users.json"]).values())


def test_failed_account_barrier_preserves_credentials_and_original(account, monkeypatch):
    user_id = account["user_id"]
    remote_objects(monkeypatch)
    monkeypatch.setattr(remote_storage, "upload_bytes", lambda *args: False)
    with pytest.raises(RuntimeError, match="persist account deletion"):
        auth.delete_user(user_id)
    assert auth.user_exists(user_id)
    assert (documents.BASE_UPLOADS_DIR / user_id / "private.txt").read_text() == "private original"
    assert not account_lifecycle.deletion_pending(user_id)


def test_worker_uses_its_own_upload_root_instead_of_api_host_path(account, monkeypatch):
    user_id = account["user_id"]
    expected = documents.BASE_UPLOADS_DIR / user_id / "private.txt"
    calls = []
    def index(path, user, display_name):
        calls.append((path, user, display_name))
        return True, 1, "Indexed"
    monkeypatch.setattr(documents, "_index_uploaded_file_locked", index)
    index_jobs.process_file_index(user_id, r"Z:\api-host\uploads\private.txt", "notes.txt")
    assert calls == [(expected, user_id, "notes.txt")]
