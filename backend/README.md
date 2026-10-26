# Backend development

Nova's FastAPI service owns authentication, private document ingestion, retrieval, streamed answers and conversation persistence. Start here when running or changing the backend; see [architecture](../docs/ARCHITECTURE.md) for module boundaries and [API reference](../docs/API_REFERENCE.md) for client contracts.

## Run locally

Use Python 3.12, matching CI. From the repository root:

```bash
python -m venv .venv
# Bash/macOS/Linux:
source .venv/bin/activate
# PowerShell instead:
# .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements-dev.txt
python -m pip_audit
```

Copy `.env.example` to `backend/.env` (`cp` in Bash, `Copy-Item` in PowerShell). Configure a unique `JWT_SECRET` and either `GROQ_API_KEY` or `LLM_PROVIDER=ollama` with a model available at `OLLAMA_URL`. Keep `RETRIEVAL_MODE=bm25` for the default path; it does not call an embedding provider. Never commit the real `.env`.

```bash
cd backend
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs`. Documentation and health endpoints are public; use Swagger's **Authorize** button with a login access token to call private routes. Cookie-backed auth POSTs need an allowed `Origin` in production. Browser clients should use the same-origin `/api` proxy described in [session security](../docs/SESSION_SECURITY.md).

Configuration loads from environment and `backend/.env` at import time. Restart the API and workers after changing it. The API creates the upload directory during startup, initializes configured database tables in development, and attempts Ollama warmup when selected. Warmup is not a readiness guarantee.

## Two runtime modes

| Concern | Local development | Shared deployment |
| --- | --- | --- |
| Users, refresh records, conversations | JSON under `backend/storage`; process locks | PostgreSQL with migrations |
| Preferences | Local JSON with optional B2 copy | Same adapter; cross-replica synchronization is a known limitation |
| Indexing | Two-thread executor in this process | Redis/RQ worker on `nova-index` |
| Uploads/indexes | Local files; B2 if configured | Shared B2 artifacts required for separate hosts |
| Rate limits | Process memory | Redis |

Use one API process in JSON/local mode. B2 copies of JSON state do not turn local read/modify/write locks into distributed transactions. Multi-host operation requires the shared services and verification in [production persistence](../docs/PRODUCTION_PERSISTENCE.md).

## Module map

| Directory | Change here for |
| --- | --- |
| `api/routes/` | HTTP validation, auth/session endpoints, SSE transport and document operations |
| `services/` | Identity, sessions, storage adapters, upload security, jobs and mutation locks |
| `rag/` | Parsing, provenance, chunks, retrieval, prompt packing and provider streaming |
| `evaluation/` | Versioned corpus, annotations, quality metrics and benchmark commands |
| `alembic/` | Production schema changes; do not depend on development `create_all` |
| `tests/` | Unit, API, isolated storage-failure and full upload-to-stream tests |

Routes resolve the authenticated user from middleware. Keep that user scope through storage paths, query cache keys, job metadata and database predicates. Never accept a user ID from request JSON as an ownership override.

## Verification

Run from the repository root:

```bash
python -m pytest -q --tb=short
python -m pytest --cov --cov-report=term-missing --cov-fail-under=64
```

The evaluation test requires generated corpus artifacts. On a fresh checkout, first run from `backend`:

```bash
python evaluation/arxiv_corpus/download_papers.py
python evaluation/arxiv_corpus/extract_corpus.py
python evaluation/arxiv_corpus/build_dataset.py
python -m evaluation.run --k 5
```

The download uses pinned checksums and network access; subsequent extraction/evaluation can use the cached PDFs offline. Ordinary tests use isolated directories and provider/storage doubles. They do not prove real Redis leases, PostgreSQL locking, B2 permissions, provider generation or backup restoration. See [evaluation methodology](evaluation/README.md) and the production runbook before treating those integrations as verified.

For a focused API change, start with `tests/test_api.py`, `tests/test_chat_contracts.py` or the corresponding service test, then run the affected integration tests. Do not lower quality/coverage gates to hide a failure.

## Debug a failure

- `/health` reports configuration and liveness, not a working provider call. `/health/ready?refresh=true` forces provider/infrastructure probes and returns 503 when required dependencies fail.
- A 401 is an absent/invalid access token; refresh with the cookie, then retry a safe request. Do not automatically replay a chat POST after a broken response stream.
- A 403 on register/login/refresh/logout is usually an `Origin` mismatch. Check both the frontend public origin and proxy configuration.
- Upload 202 means **queued**, not indexed. Poll the returned job until `finished` or a failure status before querying the document.
- Keep the response `X-Request-ID` when reporting a failure. Timing headers measure response setup; they do not include the full duration of a streamed answer.
- Keep storage-read errors distinct from an empty knowledge base. Follow the deletion/migration recovery procedures rather than deleting snapshot pointers by hand.
