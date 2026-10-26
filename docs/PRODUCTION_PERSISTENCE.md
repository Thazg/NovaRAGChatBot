# Production persistence and background indexing

## Runtime architecture

Nova deliberately keeps local development dependency-light while enabling shared production infrastructure:

| Concern | No service URL | Production URL configured |
|---|---|---|
| Users, refresh sessions, conversations | Atomic JSON files and process lock | PostgreSQL through SQLAlchemy |
| Rate limiting | Process-local sliding window | Atomic Redis sorted-set window |
| Document indexing | Two-thread local executor | RQ queue and Redis worker |
| Upload and index artifacts | Local filesystem, optionally B2 | B2 is required for workers on separate hosts |
| User preferences | Local files with optional B2 copies | Still local/B2, not a PostgreSQL preference record; cross-host authority is not yet implemented |

The frontend treats the backend conversation API as the source of truth. Conversation/session data is not persisted in browser storage.

## PostgreSQL migration

Set a psycopg-compatible URL:

```env
DATABASE_URL=postgresql+psycopg://user:password@host:5432/nova
```

Run migrations from the `backend` directory before starting a production web process:

```bash
alembic upgrade head
alembic current
```

Production startup checks for the `users`, `refresh_sessions`, and `conversations` tables and fails with a migration instruction when they are missing. Development may create tables automatically for disposable environments.

To migrate existing JSON state, first validate, then import:

```bash
python -m scripts.migrate_json_to_postgres --dry-run
python -m scripts.migrate_json_to_postgres
```

The importer is idempotent by user/conversation ID and username. It does not delete JSON/B2 data, so keep that data as a rollback snapshot until counts and representative conversations are verified.

## Redis and RQ configuration

Configure the same Redis URL on the API and worker:

```env
REDIS_URL=redis://default:password@host:6379/0
```

Start at least one worker from `backend`:

```bash
rq worker --url "$REDIS_URL" nova-index
```

The API returns HTTP 202 with `job_id` and `progress: 0`. The frontend polls:

```text
GET /documents/jobs/{job_id}
```

Only the owning user can read a job. Public error responses do not expose worker tracebacks. RQ results live for one hour and failures for one day; local job metadata is purged after one day.
Index add/delete/reindex operations share a per-user mutation lock (Redis in distributed mode, an in-process lock locally). RQ jobs time out after 900 seconds; the Redis lease lasts 960 seconds. Local mode supports a single API process; use Redis/RQ and shared storage for multiple processes/hosts.

Every write creates an immutable `index/<user>/revisions/<revision>/` snapshot. Each artifact has a SHA-256 in `current.json`. The writer uploads all artifacts before publishing the pointer, then atomically switches the local pointer. A failed upload/publication fails the job. API readers check the current revision **before query-cache lookup**, hydrate and verify the entire snapshot, then replace their cached store. Writers reload the latest snapshot under the same mutation lock, and a stale store cannot overwrite a newer revision.

Deletion first publishes a permanent storage-ID barrier in `index/<user>/deleted_documents.json`, then removes uploads/metadata and publishes the cleaned index. Readers check both the snapshot revision and deletion set before using cached retrieval. If cleanup or index publication fails, the document stays excluded from retrieval, summaries, listing and future indexing; repeating DELETE finishes cleanup even after the physical file is gone. Clear-all retains the same barriers and publishes an empty revision. A deletion whose barrier could not be persisted fails before removing an upload. Barriers are retained because storage IDs are never reused.

Distributed reindex hydrates remote uploads and excludes deletion barriers. It **never deletes unmatched local files**: those may be the only originals from local mode. If any non-deleted local document is missing remotely, reindex fails with an explicit migration instruction and leaves originals/index publication untouched. Document listing always merges local and remote IDs, even when a replica already caches some uploads, and filters deleted IDs. Storage-read failures in distributed mode fail closed rather than becoming an empty knowledge base. BM25 is the default; optional dense artifacts use the same snapshot lifecycle.

Snapshot artifacts from previous revisions are retained to protect in-flight readers. Garbage collection is not automated yet: schedule retention cleanup only after old readers/jobs have drained. Account deletion removes the user's index prefix. Do not delete `current.json` as a substitute for publishing an empty index.

Account cleanup now writes a durable UUID-only barrier under `account-deletions/<user>.json` before removing active artifacts, and removes credentials last. Failure returns503 with the account retained for retry; normal writes are blocked with409. The account marker intentionally survives cleanup of per-user prefixes. Read-cache hydration and writes share the user lock, so a paused old download cannot recreate an account's cache after cleanup. Nested synchronous operations on one thread reuse the Redis lease; there is no automatic lease renewal. The worker uses a validated storage ID under its own upload root rather than the API container's absolute path.

Account deletion addresses active local/B2 content; independent backups/provider object versions and security metadata need their own retention policy. See [operations and recovery](OPERATIONS.md) for the full boundary and failure workflow.

When `REDIS_URL` is configured, uploads must be durably copied to B2 before enqueueing because a separate worker cannot rely on the API container's ephemeral filesystem. Configure the B2 variables in both services.

## Deployment sequence

1. Provision PostgreSQL, Redis, B2, and a worker service in staging.
2. Run `alembic upgrade head`.
3. Run the JSON importer with `--dry-run`, then without it.
4. If moving from local uploads, stop new writes, drain old indexing jobs, and back up the local uploads/index directories. With B2 and Redis configured, run `python -m services.migrate_uploads --user-id <account-id>` from `backend` on the host holding the originals, once per account. The command skips deleted IDs, merges display-name metadata, verifies existing objects have identical bytes, and never removes local originals. A failure can be retried; conflicting IDs fail without overwriting either copy. Keep backups until verification finishes.
5. Start the RQ worker, confirm it listens on `nova-index`, then deploy the API with `DATABASE_URL` and `REDIS_URL`. Queue a full reindex per migrated account before resuming traffic.
6. Call `/health/ready?refresh=true`; it must report database and Redis ready with at least one indexing worker.
7. Upload a real document, poll the job through `finished`, and verify retrieval/citations.
8. Keep JSON/B2 snapshots until user counts, conversation counts, and sampled message checksums match.

Do not enable `REDIS_URL` on the public API without a running worker: uploads would remain queued. The readiness endpoint intentionally reports this as not ready.

Readiness also fails closed when Redis/RQ mode is enabled without reachable B2 object storage, or when `MALWARE_SCAN_REQUIRED=true` without a responsive ClamAV daemon. This prevents a green deployment from accepting work that its worker cannot safely complete.

## Error and trace monitoring

Set `SENTRY_DSN` to enable opt-in FastAPI/background error and trace reporting. Nova sets the environment and release automatically, samples 5% of traces by default, and keeps `send_default_pii=false`. Leave the DSN empty to use structured application logs only; no events are sent to Sentry in that mode.

```env
SENTRY_DSN=https://public-key@your-sentry-host/project-id
SENTRY_TRACES_SAMPLE_RATE=0.05
```

## Render deployment requirements

`render.yaml` declares the web-service variables but does not provision a paid
background worker or managed databases. Add the PostgreSQL and Redis resources
and the worker explicitly in Render, then follow the deployment sequence above.
If the selected plan supports a pre-deploy command, use
`cd backend && alembic upgrade head`; otherwise run the migration from a one-off
shell before enabling `DATABASE_URL`.

## Upgrade and verification for the portfolio fixes

Rebuild existing indexes after this upgrade. Legacy indexes remain readable, but only reindexing adds page/line numbers and the shared 220-word / 40-word ingestion policy. Old conversation answers cannot gain evidence retroactively. New answers persist the evidence sent to the model. Citations show the uploaded filename, page and extracted line range as plain text, without a link or PDF-serving endpoint. PDF line numbers count the extracted lines on each page, including blank lines; whitespace/ligature normalization and dehyphenation retain those source offsets. Non-PDF text uses extracted-text line numbers without inventing a page. Context truncation also narrows the cited line range.

Default prompt budgets are now `MAX_CHUNK_CHARS=2400` and `MAX_CONTEXT_CHARS=10000` to preserve typical top-5, 220-word passages. Ollama defaults to `NUM_CTX=8192`. Remove older overrides or update them explicitly during deployment. Smaller budgets select a contiguous query-relevant window and cite only overlapping extracted lines; they may retain less evidence. Character budgets are not exact model token counts, especially for multilingual text. The offline gate measures annotated character-span retention (case/whitespace insensitive) after production packing, separately from page Hit@5 and generated-answer accuracy.

Copy, native Share and conversation TXT export use the same plain filename/page/line formatter as displayed answers. Structured account JSON exports retain original message IDs plus their evidence metadata for data portability.

The SSE client requires `[DONE]` and never automatically replays a failed chat POST. The server saves a completed answer before emitting `[DONE]`; interrupted streams are recorded as incomplete. The UI offers explicit regeneration, which keeps the existing user turn and clears only that question's assistant reply.

Local regression tests include separate Python processes and separate local index directories against a filesystem object-store adapter, fault-injected upload/read failures, stale-writer rejection and empty-index publication. This verifies the snapshot protocol, **not a real Redis/RQ/B2 deployment**. Before enabling distributed mode, complete the staging workflow above with real infrastructure and exercise upload, second upload from another worker, deletion and restart.

Last hosted configuration observed during the 2026-10-16 audit was local JSON / process memory / thread-pool mode. These local changes have not been deployed. The Blueprint still requires explicit worker/database provisioning.
