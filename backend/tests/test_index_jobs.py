import time
import threading
from concurrent.futures import ThreadPoolExecutor

from services import index_jobs


def _wait_for_job(job_id: str, user_id: str) -> dict:
    for _ in range(100):
        job = index_jobs.get_job(job_id, user_id)
        if job and job["status"] in {"finished", "failed"}:
            return job
        time.sleep(0.01)
    raise AssertionError("local indexing job did not finish")


def test_local_queue_reports_progress_result_and_owner(monkeypatch) -> None:
    monkeypatch.setattr(index_jobs.settings, "REDIS_URL", "")
    index_jobs._LOCAL_JOBS.clear()

    job_id = index_jobs._enqueue(
        lambda user_id, value: {"user_id": user_id, "value": value},
        "owner-a",
        42,
    )
    job = _wait_for_job(job_id, "owner-a")

    assert job["status"] == "finished"
    assert job["progress"] == 100
    assert job["result"]["value"] == 42
    assert index_jobs.get_job(job_id, "owner-b") is None
    assert "updated_at" not in job


def test_local_queue_does_not_expose_internal_exception(monkeypatch) -> None:
    monkeypatch.setattr(index_jobs.settings, "REDIS_URL", "")
    index_jobs._LOCAL_JOBS.clear()

    def fail(_user_id: str):
        raise RuntimeError("secret backend path and credentials")

    job_id = index_jobs._enqueue(fail, "owner-a")
    job = _wait_for_job(job_id, "owner-a")

    assert job["status"] == "failed"
    assert job["error"] == "Document indexing failed"
    assert "secret" not in job["error"]


def test_local_queue_purges_expired_job_metadata(monkeypatch) -> None:
    monkeypatch.setattr(index_jobs.settings, "REDIS_URL", "")
    index_jobs._LOCAL_JOBS.clear()
    index_jobs._LOCAL_JOBS["expired-job"] = {
        "user_id": "owner-a",
        "status": "finished",
        "updated_at": time.time() - index_jobs._LOCAL_JOB_TTL_SECONDS - 1,
    }

    assert index_jobs.get_job("expired-job", "owner-a") is None
    assert "expired-job" not in index_jobs._LOCAL_JOBS


def test_local_index_mutations_are_serialized_per_user(monkeypatch) -> None:
    monkeypatch.setattr(index_jobs.settings, "REDIS_URL", "")
    active = 0
    maximum_active = 0
    state_lock = threading.Lock()

    def mutate() -> None:
        nonlocal active, maximum_active
        with index_jobs._user_index_lock("owner-a"):
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.03)
            with state_lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(mutate) for _ in range(2)]
        for future in futures:
            future.result()

    assert maximum_active == 1
