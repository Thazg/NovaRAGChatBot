import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

import app as application
from api.routes import documents
from config.settings import settings
from rag import vector_store
from services import account_lifecycle, document_lifecycle, remote_storage


@pytest.fixture
def download_client(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "BASE_UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(vector_store, "BASE_INDEX_DIR", tmp_path / "indexes")
    monkeypatch.setattr(account_lifecycle, "BASE_DIR", tmp_path / "account-deletions")
    for field in ("B2_KEY_ID", "B2_APP_KEY", "REDIS_URL"):
        monkeypatch.setattr(settings, field, "")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(remote_storage, "download_file", lambda *a: False)
    monkeypatch.setattr(remote_storage, "download_bytes", lambda *a, **kw: None)
    monkeypatch.setattr(application, "verify_token", lambda token: {"user_id": token} if token in {"owner", "other"} else None)
    monkeypatch.setattr(application, "user_exists", lambda user: user in {"owner", "other"})
    directory = documents.BASE_UPLOADS_DIR / "owner"
    directory.mkdir(parents=True)
    return TestClient(application.app), directory


def test_download_returns_original_bytes_and_original_unicode_filename(download_client):
    client, directory = download_client
    (directory / "stored.txt").write_bytes(b"original document\n")
    name = "Báo cáo.txt"
    (directory / "document_manifest.json").write_text(json.dumps({"stored.txt": {"original_name": name}}))
    response = client.get("/documents/stored.txt/download", headers={"Authorization": "Bearer owner"})
    assert response.status_code == 200
    assert response.content == b"original document\n"
    assert response.headers["content-disposition"] == f"attachment; filename*=UTF-8''{quote(name, safe='')}"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_download_is_authenticated_owner_scoped_and_hides_deleted_files(download_client):
    client, directory = download_client
    (directory / "private.txt").write_bytes(b"private original")
    assert client.get("/documents/private.txt/download").status_code == 401
    assert client.get("/documents/private.txt/download", headers={"Authorization": "Bearer other"}).status_code == 404
    document_lifecycle.mark_deleted("owner", {"private.txt"})
    assert client.get("/documents/private.txt/download", headers={"Authorization": "Bearer owner"}).status_code == 404
    assert (directory / "private.txt").exists()  # A stale cache must not bypass the barrier.


@pytest.mark.parametrize("document_id", ["document_manifest.json", "..\\private.txt", "source_urls.json"])
def test_download_rejects_internal_metadata_and_path_ids(download_client, document_id):
    client, _ = download_client
    response = client.get(f"/documents/{quote(document_id, safe='')}/download", headers={"Authorization": "Bearer owner"})
    assert response.status_code == 400


def test_download_restores_remote_original_without_creating_local_cache(download_client, monkeypatch):
    client, directory = download_client
    def get_bytes(key, **kwargs):
        return b"remote original" if key == "uploads/owner/remote.txt" else None
    monkeypatch.setattr(remote_storage, "download_bytes", get_bytes)
    response = client.get("/documents/remote.txt/download", headers={"Authorization": "Bearer owner"})
    assert response.status_code == 200
    assert response.content == b"remote original"
    assert not (directory / "remote.txt").exists()


def test_download_reports_remote_outage_and_pending_account_deletion(download_client, monkeypatch):
    client, _ = download_client
    def unavailable(key, **kwargs):
        if key.startswith("uploads/"):
            raise RuntimeError("storage unavailable")
        return None
    monkeypatch.setattr(remote_storage, "download_bytes", unavailable)
    assert client.get("/documents/remote.txt/download", headers={"Authorization": "Bearer owner"}).status_code == 503
    account_lifecycle.mark_deleting("owner")
    assert client.get("/documents/remote.txt/download", headers={"Authorization": "Bearer owner"}).status_code == 409
