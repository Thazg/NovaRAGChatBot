from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from config.settings import settings

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="nova-index")
_LOCAL_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.RLock()
_USER_LOCKS: dict[str, threading.RLock] = {}
_LOCAL_JOB_TTL_SECONDS = 24 * 60 * 60
logger = logging.getLogger(__name__)


class IndexQueueUnavailable(RuntimeError):
    pass


@contextmanager
def _user_index_lock(user_id: str):
    """Serialize index mutations per user across threads or RQ replicas."""
    if settings.REDIS_URL:
        from redis import Redis
        lock = Redis.from_url(settings.REDIS_URL).lock(
            f"nova:index-lock:{user_id}", timeout=900, blocking_timeout=30
        )
        if not lock.acquire(blocking=True):
            raise TimeoutError("Another indexing job is still running for this user")
        try:
            yield
        finally:
            lock.release()
        return
    with _LOCK:
        user_lock = _USER_LOCKS.setdefault(user_id, threading.RLock())
    with user_lock:
        yield


def _purge_local_jobs() -> None:
    cutoff = time.time() - _LOCAL_JOB_TTL_SECONDS
    for job_id, state in list(_LOCAL_JOBS.items()):
        if float(state.get("updated_at", 0)) < cutoff:
            _LOCAL_JOBS.pop(job_id, None)


def _set_local(job_id: str, **values: Any) -> None:
    with _LOCK:
        _purge_local_jobs()
        values["updated_at"] = time.time()
        _LOCAL_JOBS.setdefault(job_id, {}).update(values)


def _run_local(job_id: str, task: Callable, *args: Any) -> None:
    _set_local(job_id, status="started", progress=10)
    try:
        result = task(*args)
        _set_local(job_id, status="finished", progress=100, result=result)
    except Exception as exc:
        logger.exception("Local indexing job %s failed", job_id)
        _set_local(job_id, status="failed", progress=100, error="Document indexing failed")


def _update_rq_progress(progress: int) -> None:
    try:
        from rq import get_current_job
        job = get_current_job()
        if job:
            job.meta["progress"] = progress
            job.save_meta()
    except ImportError:
        pass


def process_file_index(user_id: str, file_path: str, display_name: str) -> dict[str, Any]:
    _update_rq_progress(25)
    path = Path(file_path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        from services.remote_storage import download_file
        if not download_file(f"uploads/{user_id}/{path.name}", path):
            raise FileNotFoundError("Uploaded document is unavailable to the indexing worker")
    from api.routes.documents import _index_uploaded_file
    with _user_index_lock(user_id):
        indexed, chunks, message = _index_uploaded_file(path, user_id, display_name)
    _update_rq_progress(100)
    if not indexed:
        raise ValueError(message)
    return {"indexed": True, "chunks": chunks, "message": message}


def process_full_reindex(user_id: str) -> dict[str, Any]:
    _update_rq_progress(20)
    from api.routes.documents import _rebuild_full_index
    with _user_index_lock(user_id):
        documents, chunks = _rebuild_full_index(user_id)
    _update_rq_progress(100)
    return {"indexed": True, "documents": documents, "chunks": chunks, "message": "Reindexing completed"}


def _enqueue(task: Callable, *args: Any) -> str:
    owner_id = str(args[0])
    if settings.REDIS_URL:
        try:
            from redis import Redis
            from rq import Queue
            queue = Queue("nova-index", connection=Redis.from_url(settings.REDIS_URL), default_timeout=900)
            job = queue.enqueue(
                task,
                *args,
                job_timeout=900,
                result_ttl=3600,
                failure_ttl=86400,
                meta={"user_id": owner_id, "progress": 0},
            )
            return job.id
        except Exception as exc:
            logger.exception("Redis indexing queue is unavailable")
            raise IndexQueueUnavailable("Indexing queue is unavailable") from exc
    job_id = uuid.uuid4().hex
    _set_local(job_id, status="queued", progress=0, user_id=owner_id)
    _EXECUTOR.submit(_run_local, job_id, task, *args)
    return job_id


def enqueue_file_index(user_id: str, file_path: str, display_name: str) -> str:
    return _enqueue(process_file_index, user_id, file_path, display_name)


def enqueue_full_reindex(user_id: str) -> str:
    return _enqueue(process_full_reindex, user_id)


def get_job(job_id: str, user_id: str) -> dict[str, Any] | None:
    if settings.REDIS_URL:
        from redis import Redis
        from rq.exceptions import NoSuchJobError
        from rq.job import Job
        try:
            job = Job.fetch(job_id, connection=Redis.from_url(settings.REDIS_URL))
        except NoSuchJobError:
            return None
        except Exception as exc:
            logger.exception("Could not read Redis indexing job %s", job_id)
            raise IndexQueueUnavailable("Indexing queue is unavailable") from exc
        if job.meta.get("user_id") != user_id:
            return None
        status = job.get_status(refresh=True)
        return {
            "id": job.id,
            "status": status,
            "progress": int(job.meta.get("progress", 100 if status == "finished" else 0)),
            "result": job.result if status == "finished" else None,
            "error": "Document indexing failed" if job.exc_info else None,
        }
    with _LOCK:
        _purge_local_jobs()
        state = _LOCAL_JOBS.get(job_id)
        if not state or state.get("user_id") != user_id:
            return None
        public_state = {key: value for key, value in state.items() if key != "updated_at"}
        return {"id": job_id, **public_state}
