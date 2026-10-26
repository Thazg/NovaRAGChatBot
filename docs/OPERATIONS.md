# Operations, recovery and troubleshooting

This guide covers operational behavior implemented by Nova. For database migration, worker provisioning and local-upload cutover, use [production persistence](PRODUCTION_PERSISTENCE.md). Those procedures still require a real isolated staging environment; passing adapter tests does not certify a deployment.

## Choose the operating mode deliberately

| Mode | Supported boundary | Data that must survive restart |
| --- | --- | --- |
| Local development/demo | One API process, JSON/process locks, two indexing threads | `backend/storage`, configured upload root, configuration/secrets |
| Shared deployment | PostgreSQL relational state, Redis/RQ jobs/locks/limits, B2 uploads/snapshots/barriers | PostgreSQL backup, B2 object versions/pointers/barriers, worker configuration; Redis policy depends on queue recovery design |

Preferences remain local/B2 files even when PostgreSQL is configured; cross-replica preference authority is a known design gap. B2-backed copies of local JSON are not a transactional replacement for PostgreSQL.

Compose persists `/app/storage` and `/app/Dataset/uploads` through named volumes, and explicitly sets `UPLOAD_FOLDER` to the upload-volume path. Before upgrading an older container whose uploads were written to `/app/uploads` in its writable layer, copy/verify those originals while that old container still exists. Recreating it first can discard the only original copy. Do not use `docker compose down -v` as a routine upgrade command.

## Hosted demo and deployment diagnostics

The linked demo uses a Vercel frontend with a same-origin `/api` proxy to Render. It is a separate deployment and can lag the source branch; the public version string does not identify its Git commit. Render can require a cold start.

Read-only observations on 2026-10-26 returned200 for the frontend, `/health` and `/health/ready`:

| Signal | Observed value |
| --- | --- |
| App label | 2.1.0, production; no Git revision reported |
| Retrieval / model | BM25 / Groq `openai/gpt-oss-20b` |
| Provider readiness | Reachable, model available; no generated-answer test performed |
| Persistence / limits / jobs | JSON / process-local / thread-local |
| Reported RAG budgets | K=5, context window4096, max tokens2048, max context6000 characters |
| Object storage / scanner | Optional-mode markers; these do not verify optional credentials/services |

These hosted budgets differ from the saved offline experiment and current repository defaults. Do not present its benchmark latency or quality as measurements of the live deployment. For a fresh observation, repeat the probes below and record time, configuration and revision if known. A reachable frontend or green readiness response is not an ingestion/answer-quality test.

The source supports shared adapters, but `render.yaml` does not provision PostgreSQL, Redis/RQ workers or B2 for you. The earlier2026-10-16 fallback-mode observation is superseded by the dated values above.

## Health and diagnostics

```bash
curl -f http://127.0.0.1:8000/health
curl -f 'http://127.0.0.1:8000/health/ready?refresh=true'
```

Liveness means the process is serving; readiness reports the configured provider/model and required infrastructure. It is not an ingestion/answer-quality test. Optional components are reported separately. Record the environment/commit and response, without copying credentials into tickets.

Responses include `X-Request-ID`, `X-Response-Time-Ms` and `Server-Timing`. Request timing for a streamed response does not represent total generation completion time. Use request IDs and job IDs to correlate application/provider/worker failures. Keep document text, tokens and private filenames out of public incident reports.

## Background work and reindexing

Uploads and reindexing return a `job_id`. Poll `GET /documents/jobs/{job_id}` with the owning account's bearer token until `finished` or `failed`; HTTP 202 is acceptance, not completion. Local jobs disappear after process restart and local metadata expires after one day. The UI stopping chat generation does not cancel an accepted indexing job.

RQ workers must use the same secrets/storage configuration and compatible code/schema as the API. Jobs use a 900-second timeout; the per-user Redis lease is 960 seconds and is not renewed automatically. Nested synchronous operations on the same thread reuse that lease. Long operations need explicit capacity/lease design; do not silently raise timeouts beyond the lock lease.

The worker resolves a validated storage ID under its own upload root, rather than trusting the API host's absolute local path. Remote storage is required for distinct hosts. If no worker is available, diagnose the queue/readiness result rather than repeatedly uploading another copy.

Safe manual reindex, from `backend`:

```bash
python rebuild_index.py --user-id ACCOUNT_UUID
```

The command requires an existing account and uses the same per-account locks, manifest and deletion barriers as the application. There is no anonymous recursive rebuild of all accounts. For local-to-B2 cutover, run the explicit migration described in the persistence guide before reindexing; a missing remote name is not permission to delete a local original.

## Deletion and partial failure

Document deletion records a permanent storage-ID barrier before destructive effects. A failed cleanup/index publication stays excluded from retrieval; repeat the same DELETE to finish cleanup. Do not remove barriers to “repair” an index, and do not reuse storage IDs.

Account deletion records a UUID-only account barrier outside per-user artifact prefixes and serializes cleanup against mutations and read-cache hydration. Credentials are removed last. If required storage cleanup fails, the API returns **503** and retains the account so the authenticated owner can retry `DELETE /auth/account`. Ordinary writes during pending deletion return **409**. New streams/jobs cannot persist into a blocked account; late cache readers cannot republish after cleanup. Successful deletion invalidates subsequent authentication through the removed account record.

Account barriers are retained intentionally; revoked refresh-session metadata and independent backups have separate retention. This is not a promise that a storage provider's historic versions/backups have been destroyed. Document active-data removal, backup expiry and legal/organizational retention separately.

## Backup and restore

Before a migration or destructive maintenance action, stop new writes and drain/stop workers. Take consistent copies of relational/JSON state and artifact storage, including immutable snapshot files, `current.json`, document deletion sets, account-deletion markers, original uploads and display-name manifests. Protect backups as sensitive data and keep secrets in your secret-management channel.

For a restore drill:

1. Restore into an isolated environment with provider calls disabled or explicitly budgeted.
2. Restore credentials/schema plus matching upload/index/session/preference state and all deletion barriers. Never restore an old snapshot pointer without its referenced immutable artifacts.
3. Verify artifact hashes, account/document counts, owner isolation and the continued exclusion of deleted IDs/accounts.
4. Reindex a synthetic account, ask representative queries, test a failed job/delete retry, and restart API/worker readers.
5. Record observed recovery time and data-loss window before setting an RTO/RPO promise. This repository does not provide an automated production backup schedule or a measured RTO/RPO.

Old immutable index revisions are currently retained to protect readers; scheduled garbage collection is not implemented. Cleanup must preserve active pointers, deletion markers and in-flight reader/job safety. Design and stage retention before automating deletion of old revisions.

## Troubleshooting

| Symptom | First checks | Recovery direction |
| --- | --- | --- |
| Startup rejects configuration | Read named setting; check provider/mode, positive budgets, JWT secret and secure-cookie combinations | Correct environment and restart API/workers; do not weaken production validation |
| Local account/history JSON is unreadable | Preserve the exact file and inspect a protected copy; check disk/write failures and available backups | Restore/repair deliberately; registration/append fail instead of replacing corrupt state with an empty mapping |
| Login works but reload loses session | Browser/API hostname, cookie Secure/SameSite, allowed Origin, production `/api` routing | Use matching local hostnames; same-origin production proxy; inspect cookie metadata without exposing its value |
| Swagger login returns403 | Browser Origin of the API docs page vs `CORS_ORIGINS` | Supply an access token via Authorize, or deliberately allow the trusted API-doc origin; retain origin protection |
| Upload accepted but remains unindexed | Owning job result, parser limits, queue/worker readiness, required B2/scanner | Fix the reported cause and reindex; do not equate acceptance with success |
| Reindex reports local-only originals | Actual upload directory vs durable listing, migration manifest | Keep originals; migrate explicitly, verify bytes, then reindex |
| Document/account deletion fails | 503 response/request ID, object-store permissions/readability, local filesystem errors | Retain barriers and owner; retry cleanup after storage recovery |
| Answer stops early | Upstream disconnect, explicit SSE `[DONE]`, cancellation/account status | Keep partial answer marked incomplete; regenerate explicitly rather than auto-replaying POST |
| Sources lack locations | Legacy index, text extraction/image-only PDF, existing answer metadata | Reindex originals; old answers cannot gain evidence retroactively; OCR is not implemented |
| CI fails at dependency audit | Advisory and installed lockfile version | Apply a scoped supported fix, rerun audit/build/tests; do not disable the gate |

## Incident handling

For suspected cross-account access, leaked credentials or unsafe downloads, preserve redacted request/job IDs and affected versions, restrict the affected ingress/workers, and follow [security reporting](../SECURITY.md). Rotate exposed real credentials and assess existing sessions/artifacts before resuming. A passing rerun alone does not establish the incident's scope.
