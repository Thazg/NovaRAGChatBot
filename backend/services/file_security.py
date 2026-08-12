from __future__ import annotations

import json
import socket
import struct
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

from pypdf import PdfReader
from pypdf import filters as pypdf_filters
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject

from config.settings import settings

# Bound FlateDecode output before any untrusted PDF stream is decompressed by
# either validation or later text extraction. pypdf applies this per stream.
pypdf_filters.ZLIB_MAX_OUTPUT_LENGTH = settings.MAX_PDF_DECOMPRESSED_STREAM_BYTES


class UnsafeUpload(ValueError):
    pass


MIME_ALLOWLIST: dict[str, set[str]] = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    ".ipynb": {"application/json", "text/json", "application/octet-stream"},
    ".txt": {"text/plain", "application/octet-stream"},
    ".md": {"text/plain", "text/markdown", "application/octet-stream"},
    ".markdown": {"text/plain", "text/markdown", "application/octet-stream"},
    ".rst": {"text/plain", "text/x-rst", "application/octet-stream"},
    ".py": {"text/plain", "text/x-python", "application/x-python-code", "application/octet-stream"},
}


def _validate_mime(extension: str, content_type: str | None) -> None:
    mime = (content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    if mime not in MIME_ALLOWLIST.get(extension, set()):
        raise UnsafeUpload(f"MIME type {mime!r} does not match {extension}")


def _is_safe_pdf_open_destination(value: object) -> bool:
    """Allow navigation-only PDF open destinations, never executable actions."""
    try:
        resolved = value.get_object() if hasattr(value, "get_object") else value
    except Exception:
        return False
    if isinstance(resolved, ArrayObject):
        # Explicit destinations are arrays such as [page /Fit]. They only
        # control the initial viewport and do not execute code or access URLs.
        return len(resolved) >= 2
    if isinstance(resolved, (NameObject, TextStringObject)):
        # Named destinations resolve to another location inside this PDF.
        return bool(str(resolved))
    if isinstance(resolved, DictionaryObject):
        # An internal GoTo action is navigation-only. GoToR, URI, Launch,
        # JavaScript, SubmitForm and unknown action types remain blocked.
        return str(resolved.get("/S", "")) == "/GoTo" and "/D" in resolved
    return False


def _validate_pdf(path: Path) -> None:
    with path.open("rb") as stream:
        prefix = stream.read(8)
    if not prefix.startswith(b"%PDF-"):
        raise UnsafeUpload("Invalid PDF signature")
    try:
        reader = PdfReader(str(path), strict=True)
        if reader.is_encrypted:
            raise UnsafeUpload("Encrypted PDFs are not accepted")
        object_count = sum(len(objects) for objects in reader.xref.values())
        if object_count > settings.MAX_PDF_OBJECTS:
            raise UnsafeUpload(f"PDF exceeds {settings.MAX_PDF_OBJECTS} indirect objects")
        if len(reader.pages) > settings.MAX_PDF_PAGES:
            raise UnsafeUpload(f"PDF exceeds {settings.MAX_PDF_PAGES} pages")
        root = reader.trailer.get("/Root")
        if root:
            catalog = root.get_object()
            names = catalog.get("/Names")
            names = names.get_object() if names else {}
            if "/EmbeddedFiles" in names or "/JavaScript" in names:
                raise UnsafeUpload("PDF contains embedded files or JavaScript")
            if "/AA" in catalog:
                raise UnsafeUpload("PDF contains executable automatic actions")
            open_action = catalog.get("/OpenAction")
            if open_action is not None and not _is_safe_pdf_open_destination(open_action):
                raise UnsafeUpload("PDF contains executable automatic actions")
            acroform = catalog.get("/AcroForm")
            if acroform and acroform.get_object().get("/XFA"):
                raise UnsafeUpload("PDF contains an XFA form")
        extracted_chars = 0
        for page in reader.pages:
            _ = page.mediabox
            if "/AA" in page:
                raise UnsafeUpload("PDF page contains automatic actions")
            extracted_chars += len(page.extract_text() or "")
            if extracted_chars > settings.MAX_PDF_EXTRACTED_CHARS:
                raise UnsafeUpload(
                    f"PDF extracted text exceeds {settings.MAX_PDF_EXTRACTED_CHARS} characters"
                )
    except UnsafeUpload:
        raise
    except Exception as exc:
        raise UnsafeUpload("Malformed or overly complex PDF") from exc


def _validate_docx(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > settings.MAX_ARCHIVE_ENTRIES:
                raise UnsafeUpload("DOCX contains too many archive entries")
            names = {info.filename for info in infos}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise UnsafeUpload("ZIP payload is not a DOCX document")
            lowered_names = {name.lower() for name in names}
            if any(
                name.endswith("vbaproject.bin")
                or name.startswith("word/activex/")
                or name.startswith("word/embeddings/")
                for name in lowered_names
            ):
                raise UnsafeUpload("DOCX contains active or embedded content")
            total_uncompressed = 0
            for info in infos:
                normalized = PurePosixPath(info.filename.replace("\\", "/"))
                if normalized.is_absolute() or ".." in normalized.parts:
                    raise UnsafeUpload("DOCX contains an unsafe archive path")
                total_uncompressed += info.file_size
                if total_uncompressed > settings.MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise UnsafeUpload("DOCX expands beyond the safe limit")
                if info.file_size and info.compress_size == 0:
                    raise UnsafeUpload("DOCX contains an invalid compressed entry")
                if info.compress_size:
                    ratio = info.file_size / info.compress_size
                    if ratio > settings.MAX_ARCHIVE_COMPRESSION_RATIO:
                        raise UnsafeUpload("DOCX compression ratio is unsafe")
            for relationship_name in (
                name for name in names if name.lower().endswith(".rels")
            ):
                try:
                    relationship_root = ET.fromstring(archive.read(relationship_name))
                except ET.ParseError as exc:
                    raise UnsafeUpload("DOCX contains malformed relationships") from exc
                if any(
                    node.attrib.get("TargetMode", "").lower() == "external"
                    for node in relationship_root.iter()
                ):
                    raise UnsafeUpload("DOCX contains external relationships")
    except UnsafeUpload:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise UnsafeUpload("Invalid DOCX signature") from exc


def _read_utf8(path: Path) -> str:
    data = path.read_bytes()
    if b"\x00" in data:
        raise UnsafeUpload("Text document contains binary data")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsafeUpload("Text documents must be UTF-8") from exc


def _validate_notebook(path: Path) -> None:
    try:
        payload = json.loads(_read_utf8(path))
    except json.JSONDecodeError as exc:
        raise UnsafeUpload("Invalid notebook JSON") from exc
    cells = payload.get("cells") if isinstance(payload, dict) else None
    if not isinstance(cells, list):
        raise UnsafeUpload("Notebook must contain a cells array")
    if len(cells) > settings.MAX_NOTEBOOK_CELLS:
        raise UnsafeUpload("Notebook contains too many cells")


def _scan_with_clamav(path: Path) -> None:
    data = path.read_bytes()
    if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in data:
        raise UnsafeUpload("Malware signature detected")
    if not settings.CLAMAV_HOST:
        if settings.MALWARE_SCAN_REQUIRED:
            raise UnsafeUpload("Malware scanner is unavailable")
        return

    try:
        with socket.create_connection((settings.CLAMAV_HOST, settings.CLAMAV_PORT), timeout=10) as client:
            client.sendall(b"zINSTREAM\0")
            with path.open("rb") as stream:
                while chunk := stream.read(64 * 1024):
                    client.sendall(struct.pack("!I", len(chunk)))
                    client.sendall(chunk)
            client.sendall(struct.pack("!I", 0))
            result = client.recv(4096).decode("utf-8", errors="replace")
    except OSError as exc:
        if settings.MALWARE_SCAN_REQUIRED:
            raise UnsafeUpload("Malware scanner is unavailable") from exc
        return
    if "FOUND" in result:
        raise UnsafeUpload("Malware scanner rejected the document")
    if "OK" not in result and settings.MALWARE_SCAN_REQUIRED:
        raise UnsafeUpload("Malware scan did not complete successfully")


def validate_uploaded_file(path: Path, original_name: str, content_type: str | None) -> None:
    extension = Path(original_name).suffix.lower()
    _validate_mime(extension, content_type)
    if extension == ".pdf":
        _validate_pdf(path)
    elif extension == ".docx":
        _validate_docx(path)
    elif extension == ".ipynb":
        _validate_notebook(path)
    else:
        _read_utf8(path)
    _scan_with_clamav(path)
