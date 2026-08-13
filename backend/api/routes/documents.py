import asyncio
import json
import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from config.settings import settings
from rag.chunking import split_documents
from rag.load import load_file
from rag.llm_client import stream_tokens
from rag.rag_chain import get_retriever, reload_vector_store, unload_vector_store
from rag.vector_store import build_vector_store, delete_vector_store, load_vector_store

logger = logging.getLogger(__name__)
router = APIRouter()

BASE_UPLOADS_DIR = Path(settings.UPLOAD_FOLDER).resolve()
SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown", ".rst", ".txt", ".docx", ".py", ".ipynb"}
INTERNAL_METADATA_FILES = {"source_urls.json", "document_manifest.json"}


def _safe_filename(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    if not name or name in {".", "..", *INTERNAL_METADATA_FILES}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if len(name) > 180:
        stem = Path(name).stem[:140]
        name = f"{stem}{Path(name).suffix}"
    if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported file type")
    return name


def _safe_document_id(document_id: str) -> str:
    """Accept UUID storage ids and legacy flat filenames, never paths."""
    name = document_id.strip()
    if (
        not name
        or name in {".", "..", *INTERNAL_METADATA_FILES}
        or "/" in name
        or "\\" in name
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
        or len(name) > 180
        or Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS
    ):
        raise HTTPException(status_code=400, detail="Invalid document ID")
    return name


def _user_uploads_dir(user_id: str) -> Path:
    d = BASE_UPLOADS_DIR / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _source_urls_file(user_id: str) -> Path:
    return _user_uploads_dir(user_id) / "source_urls.json"


def _manifest_file(user_id: str) -> Path:
    return _user_uploads_dir(user_id) / "document_manifest.json"


def _load_manifest(user_id: str) -> dict[str, dict[str, str]]:
    path = _manifest_file(user_id)
    if not path.exists():
        try:
            from services.remote_storage import download_file
            download_file(f"uploads/{user_id}/document_manifest.json", path)
        except Exception:
            pass
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _save_manifest(manifest: dict[str, dict[str, str]], user_id: str) -> None:
    path = _manifest_file(user_id)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from services.remote_storage import upload_file
        upload_file(f"uploads/{user_id}/document_manifest.json", path)
    except Exception:
        pass


def _display_name(stored_name: str, manifest: dict[str, dict[str, str]]) -> str:
    entry = manifest.get(stored_name, {})
    return entry.get("original_name", stored_name)


def _load_source_urls(user_id: str) -> dict[str, str]:
    sf = _source_urls_file(user_id)
    if not sf.exists():
        try:
            from services.remote_storage import download_file
            download_file(f"uploads/{user_id}/source_urls.json", sf)
        except Exception:
            pass
    if sf.exists():
        try:
            with sf.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_source_urls(mapping: dict[str, str], user_id: str) -> None:
    sf = _source_urls_file(user_id)
    with sf.open("w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    try:
        from services.remote_storage import upload_file
        upload_file(f"uploads/{user_id}/source_urls.json", sf)
    except Exception:
        pass


def _delete_remote_file(filename: str, user_id: str) -> bool:
    try:
        from services.remote_storage import delete_file
        return delete_file(f"uploads/{user_id}/{filename}")
    except Exception:
        return False


class SummarizeRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=180)


@router.post("/summarize")
async def summarize_document(request: Request, body: SummarizeRequest):
    filename = body.filename.strip()
    user_id = getattr(request.state, "user_id", "") or "__anonymous__"
    manifest = _load_manifest(user_id)
    stored_name = filename if filename in manifest else next(
        (key for key, value in manifest.items() if value.get("original_name") == filename),
        filename,
    )

    try:
        store = load_vector_store(user_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Vector store not found")

    filename_lower = filename.lower()
    chunks = [
        doc.get("content", "")
        for doc in store.documents
        if (
            doc.get("metadata", {}).get("storage_name", "").lower() == stored_name.lower()
            or doc.get("metadata", {}).get("file_name", "").lower() == filename_lower
        )
    ]
    if not chunks:
        raise HTTPException(status_code=404, detail="No chunks found for this file")

    full_text = "\n\n".join(chunks)
    max_chars = 20000
    truncated = len(full_text) > max_chars
    if truncated:
        full_text = full_text[:max_chars] + "\n\n[... content truncated ...]"

    prompt = (
        f"You are a research assistant. Summarize the document below thoroughly but concisely.\n"
        f"Structure your response into these sections:\n"
        f"## Overview\n"
        f"A brief description of what this document covers.\n\n"
        f"## Key Points\n"
        f"Bullet list of the main ideas, findings, or arguments.\n\n"
        f"## Key Terms & Definitions\n"
        f"Important terminology introduced in the document.\n\n"
        f"## Conclusion\n"
        f"The main takeaway or final message.\n\n"
        f"Respond in the same language as the document.{' Note: the document was too long and was truncated.' if truncated else ''}\n\n"
        f"Document:\n{full_text}\n\n"
        f"Summary:"
    )
    summary = ""
    async for token in stream_tokens(prompt):
        summary += token
    return {"summary": summary, "chunks": len(chunks), "filename": filename}


def _load_chunk_counts(user_id: str) -> dict[str, int]:
    from rag.vector_store import _metadata_file
    mf = _metadata_file(user_id)
    if not mf.exists():
        try:
            load_vector_store(user_id)
        except FileNotFoundError:
            pass
    chunk_counts: dict[str, int] = {}
    if not mf.exists():
        return chunk_counts
    with mf.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                metadata = item.get("metadata", {})
                source = metadata.get("storage_name") or metadata.get("file_name") or metadata.get("source")
                if source:
                    chunk_counts[source] = chunk_counts.get(source, 0) + 1
            except json.JSONDecodeError:
                continue
    return chunk_counts


def _list_upload_files(user_id: str) -> list[dict]:
    chunk_counts = _load_chunk_counts(user_id)
    source_urls = _load_source_urls(user_id)
    manifest = _load_manifest(user_id)
    upload_dir = _user_uploads_dir(user_id)
    files = []
    local_files = [
        path for path in upload_dir.iterdir()
        if path.is_file() and path.name not in INTERNAL_METADATA_FILES
    ] if upload_dir.exists() else []

    if not local_files:
        try:
            from services.remote_storage import list_file_info
            remote_files = list_file_info(f"uploads/{user_id}/")
            for remote_file in remote_files:
                remote_path = str(remote_file["key"])
                name = remote_path[len(f"uploads/{user_id}/"):]
                if name in INTERNAL_METADATA_FILES:
                    continue
                item = {
                    "id": name,
                    "name": _display_name(name, manifest),
                    "size": int(remote_file.get("size", 0)),
                    "indexed": bool(chunk_counts.get(name)),
                    "chunks": chunk_counts.get(name, 0),
                }
                if source_url := source_urls.get(name):
                    item["source_url"] = source_url
                files.append(item)
            return files
        except ImportError:
            pass

    seen_names: set[str] = set()
    if upload_dir.exists():
        for file_path in sorted(local_files):
            if not file_path.is_file() or file_path.name in seen_names or file_path.name in INTERNAL_METADATA_FILES:
                continue
            seen_names.add(file_path.name)
            item = {
                "id": file_path.name, "name": _display_name(file_path.name, manifest), "size": file_path.stat().st_size,
                "indexed": bool(chunk_counts.get(file_path.name)),
                "chunks": chunk_counts.get(file_path.name, 0),
            }
            if source_url := source_urls.get(file_path.name):
                item["source_url"] = source_url
            files.append(item)
    return files


def _restore_remote_uploads(user_id: str) -> None:
    """Hydrate missing upload files before a full reindex on ephemeral hosts."""
    try:
        from services.remote_storage import download_file, list_files
        prefix = f"uploads/{user_id}/"
        upload_dir = _user_uploads_dir(user_id)
        for remote_path in list_files(prefix):
            name = remote_path[len(prefix):].replace("\\", "/").rsplit("/", 1)[-1]
            if not name or name in INTERNAL_METADATA_FILES or Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            local_path = upload_dir / name
            if not local_path.exists():
                download_file(remote_path, local_path)
    except Exception as exc:
        logger.warning("Could not restore remote uploads for %s: %s", user_id, exc)


def _apply_document_identity(documents: list, file_path: Path, display_name: str) -> None:
    for document in documents:
        document.metadata["storage_name"] = file_path.name
        document.metadata["file_name"] = display_name


def _index_uploaded_file(file_path: Path, user_id: str, display_name: str | None = None) -> tuple[bool, int, str]:
    documents = load_file(file_path)
    _apply_document_identity(documents, file_path, display_name or file_path.name)
    if not documents:
        return False, 0, "File type not supported"
    nodes = split_documents(documents)
    if not nodes:
        return False, 0, "No content extracted from file"
    try:
        store = get_retriever(user_id)
        if store is None:
            raise FileNotFoundError("No retriever available")
    except (FileNotFoundError, AttributeError):
        try:
            store = load_vector_store(user_id)
        except FileNotFoundError:
            build_vector_store(nodes, user_id)
            reload_vector_store(user_id)
            return True, len(nodes), "Indexed successfully"
    store.remove_by_file_name(file_path.name)
    store.add_nodes(nodes)
    store.persist()
    reload_vector_store(user_id)
    return True, len(nodes), "Indexed successfully"


def _rebuild_full_index(user_id: str) -> tuple[int, int]:
    _restore_remote_uploads(user_id)
    upload_dir = _user_uploads_dir(user_id)
    documents = []
    manifest = _load_manifest(user_id)
    if upload_dir.exists():
        for fp in upload_dir.iterdir():
            if fp.is_file() and fp.suffix.lower() in SUPPORTED_EXTENSIONS:
                loaded = load_file(fp)
                _apply_document_identity(loaded, fp, _display_name(fp.name, manifest))
                documents.extend(loaded)
    nodes = split_documents(documents)
    if nodes:
        build_vector_store(nodes, user_id)
        reload_vector_store(user_id)
    else:
        delete_vector_store(user_id)
        unload_vector_store(user_id)
    return len(documents), len(nodes)


@router.get("")
def list_documents(request: Request):
    user_id = getattr(request.state, "user_id", "") or "__anonymous__"
    return _list_upload_files(user_id)


@router.post("/upload", status_code=202)
async def upload_document(request: Request, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    original_name = _safe_filename(file.filename)
    stored_name = f"{uuid.uuid4().hex}{Path(original_name).suffix.lower()}"
    user_id = getattr(request.state, "user_id", "") or "__anonymous__"
    upload_dir = _user_uploads_dir(user_id)
    file_location = upload_dir / stored_name
    temp_location = upload_dir / f".{uuid.uuid4().hex}.upload"
    total_bytes = 0
    try:
        with temp_location.open("wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > settings.MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File is too large")
                buffer.write(chunk)
    except Exception:
        temp_location.unlink(missing_ok=True)
        raise

    try:
        from services.file_security import UnsafeUpload, validate_uploaded_file
        await asyncio.to_thread(validate_uploaded_file, temp_location, original_name, file.content_type)
        temp_location.replace(file_location)
    except UnsafeUpload as exc:
        temp_location.unlink(missing_ok=True)
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception:
        temp_location.unlink(missing_ok=True)
        raise

    try:
        manifest = _load_manifest(user_id)
        manifest[stored_name] = {"original_name": original_name}
        _save_manifest(manifest, user_id)
        remote_persisted = False
        try:
            from services.remote_storage import upload_file
            remote_persisted = bool(await asyncio.to_thread(
                upload_file, f"uploads/{user_id}/{stored_name}", file_location
            ))
        except Exception as exc:
            logger.warning("Could not persist upload %s to remote storage: %s", stored_name, exc)
        if settings.REDIS_URL and not remote_persisted:
            raise HTTPException(
                status_code=503,
                detail="Durable upload storage is required for background indexing",
            )
        from services.index_jobs import IndexQueueUnavailable, enqueue_file_index
        try:
            job_id = enqueue_file_index(user_id, str(file_location), original_name)
        except IndexQueueUnavailable as exc:
            raise HTTPException(status_code=503, detail="Indexing queue is unavailable") from exc
        return {
            "status": "queued", "id": stored_name, "filename": original_name,
            "indexed": False, "job_id": job_id, "progress": 0,
            "message": "Upload accepted; indexing is running in the background.",
        }
    except HTTPException:
        manifest = _load_manifest(user_id)
        manifest.pop(stored_name, None)
        _save_manifest(manifest, user_id)
        file_location.unlink(missing_ok=True)
        _delete_remote_file(stored_name, user_id)
        try:
            _rebuild_full_index(user_id)
        except Exception:
            logger.exception("Could not restore index after rejected upload for user %s", user_id)
        raise
    except Exception as exc:
        logger.exception("Failed to store uploaded document for user %s", user_id)
        manifest = _load_manifest(user_id)
        manifest.pop(stored_name, None)
        _save_manifest(manifest, user_id)
        file_location.unlink(missing_ok=True)
        _delete_remote_file(stored_name, user_id)
        try:
            _rebuild_full_index(user_id)
        except Exception:
            logger.exception("Could not restore index after upload failure for user %s", user_id)
        raise HTTPException(status_code=500, detail="Failed to store and index document") from exc


@router.get("/jobs/{job_id}")
def get_index_job(request: Request, job_id: str):
    user_id = getattr(request.state, "user_id", "") or "__anonymous__"
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", job_id):
        raise HTTPException(status_code=400, detail="Invalid job ID")
    from services.index_jobs import IndexQueueUnavailable, get_job
    try:
        job = get_job(job_id, user_id)
    except IndexQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail="Indexing queue is unavailable") from exc
    if not job:
        raise HTTPException(status_code=404, detail="Indexing job not found")
    return job


@router.delete("/clear-all")
def clear_all_documents(request: Request):
    user_id = getattr(request.state, "user_id", "") or "__anonymous__"
    upload_dir = _user_uploads_dir(user_id)
    deleted_count = 0
    if upload_dir.exists():
        for file_path in upload_dir.iterdir():
            if file_path.is_file() and file_path.name not in INTERNAL_METADATA_FILES:
                file_path.unlink()
                deleted_count += 1
    try:
        from services.remote_storage import list_files, delete_file
        remote_files = list_files(f"uploads/{user_id}/")
        for remote_path in remote_files:
            if not remote_path.endswith("source_urls.json"):
                delete_file(remote_path)
    except Exception:
        pass
    _save_source_urls({}, user_id)
    _save_manifest({}, user_id)
    _rebuild_full_index(user_id)
    return {"status": "success", "deleted": deleted_count}


@router.delete("/{id}")
def delete_document(request: Request, id: str):
    user_id = getattr(request.state, "user_id", "") or "__anonymous__"
    safe_id = _safe_document_id(id)
    upload_dir = _user_uploads_dir(user_id)
    file_location = upload_dir / safe_id
    deleted = False
    if file_location.exists():
        file_location.unlink()
        deleted = True
    remote_deleted = _delete_remote_file(safe_id, user_id)
    if not deleted and not remote_deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    source_urls = _load_source_urls(user_id)
    source_urls.pop(safe_id, None)
    _save_source_urls(source_urls, user_id)
    manifest = _load_manifest(user_id)
    manifest.pop(safe_id, None)
    _save_manifest(manifest, user_id)
    try:
        store = get_retriever(user_id)
        if store is None:
            raise FileNotFoundError
        store.remove_by_file_name(safe_id)
        store.persist()
        reload_vector_store(user_id)
    except FileNotFoundError:
        _rebuild_full_index(user_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Document deleted but reindex failed: {exc}") from exc
    return {"status": "success"}


@router.post("/reindex")
def reindex_documents(request: Request):
    user_id = getattr(request.state, "user_id", "") or "__anonymous__"
    try:
        from services.index_jobs import IndexQueueUnavailable, enqueue_full_reindex
        try:
            job_id = enqueue_full_reindex(user_id)
        except IndexQueueUnavailable as exc:
            raise HTTPException(status_code=503, detail="Indexing queue is unavailable") from exc
        return {
            "status": "queued", "message": "Reindexing queued",
            "job_id": job_id, "progress": 0,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Reindexing failed for user %s", user_id)
        raise HTTPException(status_code=500, detail="Document reindexing failed") from exc


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    max_results: int = Field(default=3, ge=1, le=5)


@router.post("/search-download")
def search_and_download(request: Request, req: SearchRequest):
    user_id = getattr(request.state, "user_id", "") or "__anonymous__"
    try:
        from rag.downloader import download_pdf, safe_pdf_filename, search_pdf_urls

        clean_query = re.sub(
            r"^(?:search|tìm)\s+(?:for|kiếm)?\s*",
            "",
            req.query,
            flags=re.IGNORECASE,
        ).strip()
        if not clean_query:
            clean_query = req.query
        search_query = f'{clean_query} filetype:pdf'
        urls = search_pdf_urls(search_query, max_results=req.max_results)
        if not urls:
            urls = search_pdf_urls(clean_query, max_results=req.max_results)
        if not urls:
            return {"status": "success", "downloaded": [], "message": "No PDFs found for query."}

        source_urls = _load_source_urls(user_id)
        manifest = _load_manifest(user_id)
        upload_dir = _user_uploads_dir(user_id)
        downloaded = []
        for url in urls:
            original_name = safe_pdf_filename(url)
            existing_name = next((name for name, source in source_urls.items() if source == url), None)
            if existing_name and (upload_dir / existing_name).exists():
                downloaded.append({"id": existing_name, "file_name": _display_name(existing_name, manifest), "new": False})
                continue
            stored_name = f"{uuid.uuid4().hex}.pdf"
            file_path = upload_dir / stored_name
            try:
                download_pdf(url, file_path)
                from services.file_security import validate_uploaded_file
                validate_uploaded_file(file_path, original_name, "application/pdf")
                remote_persisted = False
                try:
                    from services.remote_storage import upload_file
                    remote_persisted = bool(upload_file(f"uploads/{user_id}/{stored_name}", file_path))
                except Exception as exc:
                    logger.warning("Could not persist remote PDF %s: %s", stored_name, exc)
                if settings.REDIS_URL and not remote_persisted:
                    raise RuntimeError("Durable upload storage is unavailable")
                downloaded.append({"id": stored_name, "file_name": original_name, "new": True})
                source_urls[stored_name] = url
                manifest[stored_name] = {"original_name": original_name}
            except Exception as exc:
                file_path.unlink(missing_ok=True)
                logger.warning("Failed to download %s: %s", url, exc)
        new_downloads = any(item["new"] for item in downloaded)
        if new_downloads:
            _save_source_urls(source_urls, user_id)
            _save_manifest(manifest, user_id)
            from services.index_jobs import IndexQueueUnavailable, enqueue_full_reindex
            try:
                job_id = enqueue_full_reindex(user_id)
            except IndexQueueUnavailable as exc:
                raise HTTPException(status_code=503, detail="Indexing queue is unavailable") from exc
        else:
            job_id = None
        return {
            "status": "success", "downloaded": downloaded,
            "message": f"Downloaded {sum(1 for d in downloaded if d['new'])} new files.",
            "job_id": job_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Search-and-download failed safely for user %s", user_id)
        raise HTTPException(status_code=502, detail="Search download failed safely") from exc
