import asyncio
import io
import re
import shutil
import socket
import sys
import zipfile
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject
from starlette.datastructures import Headers
from starlette.requests import Request

from api.routes import documents
from rag import downloader
from services.file_security import UnsafeUpload, validate_uploaded_file


@pytest.fixture
def payload_path(request):
    path = Path(__file__).with_name(f"_security_{request.node.name}.bin")
    path.unlink(missing_ok=True)
    yield path
    path.unlink(missing_ok=True)


def test_ssrf_guard_rejects_private_dns_answer(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))],
    )
    with pytest.raises(ValueError, match="non-public"):
        downloader.validate_public_url("https://example.com/document.pdf")


def test_ssrf_guard_accepts_only_global_dns_answers(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    assert downloader.validate_public_url("https://example.com/document.pdf").startswith("https://")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/file.pdf",
        "http://10.0.0.5/file.pdf",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/file.pdf",
        "file:///etc/passwd",
        "https://user:password@example.com/file.pdf",
        "https://example.com:8080/file.pdf",
    ],
)
def test_ssrf_guard_rejects_local_schemes_credentials_and_ports(url: str) -> None:
    with pytest.raises(downloader.UnsafeRemoteURL):
        downloader.validate_public_url(url)


def test_ssrf_guard_rejects_mixed_public_and_private_dns(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443)),
        ],
    )
    with pytest.raises(downloader.UnsafeRemoteURL, match="non-public"):
        downloader.validate_public_url("https://example.com/file.pdf")


class _FakeSocket:
    def __init__(self, address: str):
        self.address = address

    def getpeername(self):
        return self.address, 443


def _fake_response(peer: str | None):
    connection = SimpleNamespace(sock=_FakeSocket(peer)) if peer else None
    return SimpleNamespace(raw=SimpleNamespace(_connection=connection, connection=connection))


def test_connected_peer_check_fails_closed() -> None:
    with pytest.raises(downloader.UnsafeRemoteURL, match="verify"):
        downloader._validate_connected_peer(_fake_response(None))
    with pytest.raises(downloader.UnsafeRemoteURL, match="non-public"):
        downloader._validate_connected_peer(_fake_response("127.0.0.1"))


def test_redirect_to_private_address_is_blocked_before_second_request(monkeypatch) -> None:
    def resolve(host, port, **_kwargs):
        address = "127.0.0.1" if host == "127.0.0.1" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    first = SimpleNamespace(
        status_code=302,
        headers={"Location": "http://127.0.0.1/internal.pdf"},
        url="https://example.com/start.pdf",
        raw=SimpleNamespace(_connection=SimpleNamespace(sock=_FakeSocket("93.184.216.34"))),
        close=lambda: None,
    )
    calls = []
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(downloader.SESSION, "get", lambda *args, **kwargs: calls.append(args[0]) or first)
    monkeypatch.setattr(downloader.time, "sleep", lambda *_args: pytest.fail("unsafe URLs must not retry"))

    with pytest.raises(downloader.UnsafeRemoteURL, match="non-public"):
        downloader.request_with_retry("https://example.com/start.pdf")
    assert calls == ["https://example.com/start.pdf"]


def test_pdf_search_uses_canonical_endpoint(monkeypatch) -> None:
    response = SimpleNamespace(
        text=(
            '<a class="result__a" '
            'href="https://example.com/scalable-rag.pdf">Scalable RAG</a>'
        ),
        close=lambda: None,
    )
    calls = []
    monkeypatch.setattr(
        downloader,
        "request_with_retry",
        lambda url, **kwargs: calls.append((url, kwargs)) or response,
    )
    monkeypatch.setattr(downloader, "validate_public_url", lambda url: url)

    assert downloader.search_pdf_urls("scalable rag filetype:pdf", 3) == [
        "https://example.com/scalable-rag.pdf"
    ]
    assert calls == [
        (
            "https://html.duckduckgo.com/html/",
            {"params": {"q": "scalable rag filetype:pdf", "kl": "us-en"}},
        )
    ]


class _DownloadResponse:
    def __init__(self, content_type: str, chunks: list[bytes], content_length: str = "0"):
        self.headers = {"Content-Type": content_type, "Content-Length": content_length}
        self._chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size: int):
        del chunk_size
        yield from self._chunks

    def close(self):
        self.closed = True


def test_pdf_download_rejects_html_content_type(payload_path: Path, monkeypatch) -> None:
    response = _DownloadResponse("text/html; charset=utf-8", [b"%PDF-1.7"])
    monkeypatch.setattr(downloader, "validate_public_url", lambda url: url)
    monkeypatch.setattr(downloader, "request_with_retry", lambda *_args, **_kwargs: response)

    with pytest.raises(ValueError, match="content type"):
        downloader.download_pdf("https://example.com/report.pdf", payload_path)
    assert response.closed is True
    assert not payload_path.exists()


def test_pdf_download_enforces_streaming_size_limit(payload_path: Path, monkeypatch) -> None:
    response = _DownloadResponse("application/pdf", [b"%PDF-", b"too-large"])
    monkeypatch.setattr(downloader, "validate_public_url", lambda url: url)
    monkeypatch.setattr(downloader, "request_with_retry", lambda *_args, **_kwargs: response)
    monkeypatch.setattr("config.settings.settings.MAX_UPLOAD_BYTES", 8)

    with pytest.raises(ValueError, match="too large"):
        downloader.download_pdf("https://example.com/report.pdf", payload_path)
    assert response.closed is True
    assert not payload_path.exists()
    assert not payload_path.with_suffix(payload_path.suffix + ".part").exists()


def test_upload_rejects_spoofed_pdf(payload_path: Path) -> None:
    payload_path.write_text("not really a PDF", encoding="utf-8")
    with pytest.raises(UnsafeUpload, match="signature"):
        validate_uploaded_file(payload_path, "report.pdf", "application/pdf")


def test_upload_rejects_mime_mismatch(payload_path: Path) -> None:
    payload_path.write_text("safe text", encoding="utf-8")
    with pytest.raises(UnsafeUpload, match="MIME"):
        validate_uploaded_file(payload_path, "notes.txt", "image/svg+xml")


def test_upload_rejects_eicar_signature(payload_path: Path) -> None:
    payload_path.write_text("EICAR-STANDARD-ANTIVIRUS-TEST-FILE", encoding="utf-8")
    with pytest.raises(UnsafeUpload, match="Malware"):
        validate_uploaded_file(payload_path, "notes.txt", "text/plain")


def test_pdf_rejects_automatic_actions(payload_path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer._root_object[NameObject("/OpenAction")] = DictionaryObject()
    with payload_path.open("wb") as stream:
        writer.write(stream)
    with pytest.raises(UnsafeUpload, match="automatic actions"):
        validate_uploaded_file(payload_path, "active.pdf", "application/pdf")


def test_pdf_allows_navigation_only_open_destination(payload_path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=72, height=72)
    writer._root_object[NameObject("/OpenAction")] = ArrayObject(
        [page.indirect_reference, NameObject("/Fit")]
    )
    with payload_path.open("wb") as stream:
        writer.write(stream)

    validate_uploaded_file(payload_path, "navigation.pdf", "application/pdf")


def test_pdf_rejects_javascript_open_action(payload_path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer._root_object[NameObject("/OpenAction")] = DictionaryObject({
        NameObject("/S"): NameObject("/JavaScript"),
        NameObject("/JS"): TextStringObject("app.alert('unsafe')"),
    })
    with payload_path.open("wb") as stream:
        writer.write(stream)

    with pytest.raises(UnsafeUpload, match="automatic actions"):
        validate_uploaded_file(payload_path, "javascript.pdf", "application/pdf")


def test_pdf_object_complexity_limit(payload_path: Path, monkeypatch) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with payload_path.open("wb") as stream:
        writer.write(stream)
    monkeypatch.setattr("config.settings.settings.MAX_PDF_OBJECTS", 0)
    with pytest.raises(UnsafeUpload, match="indirect objects"):
        validate_uploaded_file(payload_path, "large-graph.pdf", "application/pdf")


def test_docx_archive_complexity_limit(payload_path: Path, monkeypatch) -> None:
    with zipfile.ZipFile(payload_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "types")
        archive.writestr("word/document.xml", "0" * 50_000)
    monkeypatch.setattr("config.settings.settings.MAX_ARCHIVE_COMPRESSION_RATIO", 2)
    with pytest.raises(UnsafeUpload, match="compression ratio"):
        validate_uploaded_file(
            payload_path,
            "report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


def test_docx_rejects_external_relationships(payload_path: Path) -> None:
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="test" Target="http://127.0.0.1/secret" '
        'TargetMode="External"/></Relationships>'
    )
    with zipfile.ZipFile(payload_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("[Content_Types].xml", "types")
        archive.writestr("word/document.xml", "document")
        archive.writestr("word/_rels/document.xml.rels", relationships)
    with pytest.raises(UnsafeUpload, match="external relationships"):
        validate_uploaded_file(
            payload_path,
            "external.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


def test_required_malware_scanner_fails_closed(payload_path: Path, monkeypatch) -> None:
    payload_path.write_text("safe text", encoding="utf-8")
    monkeypatch.setattr("config.settings.settings.CLAMAV_HOST", "")
    monkeypatch.setattr("config.settings.settings.MALWARE_SCAN_REQUIRED", True)
    with pytest.raises(UnsafeUpload, match="scanner is unavailable"):
        validate_uploaded_file(payload_path, "notes.txt", "text/plain")


def _upload_request(user_id: str = "security-user") -> Request:
    request = Request({"type": "http", "method": "POST", "path": "/documents/upload", "headers": []})
    request.state.user_id = user_id
    return request


def _upload_file(name: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=name,
        headers=Headers({"content-type": content_type}),
    )


def test_upload_uses_uuid_storage_name_and_preserves_display_name(monkeypatch) -> None:
    workspace = Path(__file__).with_name("_security_upload_workspace")
    shutil.rmtree(workspace, ignore_errors=True)
    manifest: dict[str, dict[str, str]] = {}
    monkeypatch.setattr(documents, "BASE_UPLOADS_DIR", workspace)
    monkeypatch.setattr(documents, "_load_manifest", lambda _user_id: dict(manifest))
    monkeypatch.setattr(
        documents,
        "_save_manifest",
        lambda value, _user_id: (manifest.clear(), manifest.update(value)),
    )
    monkeypatch.setattr(
        documents,
        "_index_uploaded_file",
        lambda *_args, **_kwargs: (True, 1, "Indexed successfully"),
    )
    remote_storage = ModuleType("services.remote_storage")
    remote_storage.upload_file = lambda *_args, **_kwargs: True
    monkeypatch.setitem(sys.modules, "services.remote_storage", remote_storage)

    try:
        result = asyncio.run(documents.upload_document(
            _upload_request(),
            _upload_file("../../Quarterly Report.txt", b"safe portfolio content", "text/plain"),
        ))
        assert result["filename"] == "Quarterly Report.txt"
        assert re.fullmatch(r"[0-9a-f]{32}\.txt", result["id"])
        assert manifest[result["id"]]["original_name"] == "Quarterly Report.txt"
        assert (workspace / "security-user" / result["id"]).read_bytes() == b"safe portfolio content"
        assert not (workspace / "security-user" / "Quarterly Report.txt").exists()
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_upload_rejects_spoofed_content_before_indexing(monkeypatch) -> None:
    workspace = Path(__file__).with_name("_security_upload_reject_workspace")
    shutil.rmtree(workspace, ignore_errors=True)
    monkeypatch.setattr(documents, "BASE_UPLOADS_DIR", workspace)
    monkeypatch.setattr(
        documents,
        "_index_uploaded_file",
        lambda *_args, **_kwargs: pytest.fail("unsafe content must never be indexed"),
    )
    try:
        with pytest.raises(HTTPException) as error:
            asyncio.run(documents.upload_document(
                _upload_request(),
                _upload_file("fake.pdf", b"this is HTML, not a PDF", "application/pdf"),
            ))
        assert error.value.status_code == 415
        remaining = list((workspace / "security-user").glob("*"))
        assert remaining == []
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
