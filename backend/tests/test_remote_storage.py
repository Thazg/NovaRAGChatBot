from pathlib import Path
import shutil

from botocore.exceptions import ClientError

from api.routes import documents
from services import remote_storage

TEST_ROOT = Path(__file__).with_name("_remote_storage")


class FakeBody:
    def read(self) -> bytes:
        return b"downloaded-bytes"


class FakeS3:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.pages = 0

    def upload_file(self, local: str, bucket: str, key: str) -> None:
        self.calls.append(("upload", local, bucket, key))

    def download_file(self, bucket: str, key: str, local: str) -> None:
        self.calls.append(("download", bucket, key, local))
        Path(local).write_bytes(b"file")

    def head_object(self, **kwargs) -> None:
        self.calls.append(("head", kwargs))

    def list_objects_v2(self, **kwargs):
        self.pages += 1
        if self.pages == 1:
            return {
                "Contents": [{"Key": "uploads/a.txt", "Size": 123}],
                "IsTruncated": True,
                "NextContinuationToken": "next",
            }
        assert kwargs["ContinuationToken"] == "next"
        return {"Contents": [{"Key": "uploads/b.txt", "Size": 456}], "IsTruncated": False}

    def delete_object(self, **kwargs) -> None:
        self.calls.append(("delete", kwargs))

    def put_object(self, **kwargs) -> None:
        self.calls.append(("put", kwargs))

    def get_object(self, **kwargs):
        self.calls.append(("get", kwargs))
        return {"Body": FakeBody()}


class FailingS3:
    def __getattr__(self, name):
        def fail(*_args, **_kwargs):
            raise ClientError({"Error": {"Code": "500", "Message": "failed"}}, name)
        return fail


def test_remote_storage_returns_safe_defaults_without_credentials(monkeypatch) -> None:
    monkeypatch.setattr(remote_storage, "_client", None)
    monkeypatch.setattr(remote_storage.settings, "B2_KEY_ID", "")
    monkeypatch.setattr(remote_storage.settings, "B2_APP_KEY", "")

    assert remote_storage.upload_file("x", TEST_ROOT / "x") is False
    assert remote_storage.download_file("x", TEST_ROOT / "x") is False
    assert remote_storage.file_exists("x") is False
    assert remote_storage.list_file_info("x") == []
    assert remote_storage.list_files("x") == []
    assert remote_storage.delete_file("x") is False
    assert remote_storage.upload_bytes("x", b"x") is False
    assert remote_storage.download_bytes("x") is None


def test_remote_storage_success_paths_and_pagination(monkeypatch) -> None:
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
    TEST_ROOT.mkdir(parents=True)
    fake = FakeS3()
    monkeypatch.setattr(remote_storage, "_client", fake)
    source = TEST_ROOT / "source.txt"
    source.write_text("hello", encoding="utf-8")
    destination = TEST_ROOT / "nested" / "destination.txt"

    assert remote_storage.upload_file("uploads/source.txt", source)
    assert remote_storage.download_file("uploads/source.txt", destination)
    assert destination.read_bytes() == b"file"
    assert remote_storage.file_exists("uploads/source.txt")
    assert remote_storage.list_file_info("uploads/") == [
        {"key": "uploads/a.txt", "size": 123},
        {"key": "uploads/b.txt", "size": 456},
    ]
    fake.pages = 0
    assert remote_storage.list_files("uploads/") == ["uploads/a.txt", "uploads/b.txt"]
    assert remote_storage.delete_file("uploads/source.txt")
    assert remote_storage.upload_bytes("state.json", b"{}")
    assert remote_storage.download_bytes("state.json") == b"downloaded-bytes"
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


def test_remote_storage_converts_provider_errors_to_safe_results(monkeypatch) -> None:
    monkeypatch.setattr(remote_storage, "_client", FailingS3())

    assert remote_storage.upload_file("x", TEST_ROOT / "x") is False
    assert remote_storage.download_file("x", TEST_ROOT / "x") is False
    assert remote_storage.file_exists("x") is False
    assert remote_storage.list_file_info("x") == []
    assert remote_storage.list_files("x") == []
    assert remote_storage.delete_file("x") is False
    assert remote_storage.upload_bytes("x", b"x") is False
    assert remote_storage.download_bytes("x") is None


def test_remote_document_listing_preserves_object_size(monkeypatch) -> None:
    listing_root = TEST_ROOT / "listing"
    shutil.rmtree(listing_root, ignore_errors=True)
    monkeypatch.setattr(documents, "BASE_UPLOADS_DIR", listing_root / "uploads")
    monkeypatch.setattr(documents, "_load_chunk_counts", lambda _user_id: {"stored.pdf": 20})
    monkeypatch.setattr(documents, "_load_source_urls", lambda _user_id: {})
    monkeypatch.setattr(
        documents,
        "_load_manifest",
        lambda _user_id: {"stored.pdf": {"original_name": "paper.pdf"}},
    )
    monkeypatch.setattr(
        remote_storage,
        "list_file_info",
        lambda _prefix: [{"key": "uploads/test-user/stored.pdf", "size": 231_097}],
    )

    listed = documents._list_upload_files("test-user")

    assert listed == [{
        "id": "stored.pdf",
        "name": "paper.pdf",
        "size": 231_097,
        "indexed": True,
        "chunks": 20,
    }]
    shutil.rmtree(listing_root, ignore_errors=True)
