# Production persistence and background indexing

## Runtime architecture

Nova deliberately keeps local development dependency-light while enabling shared production infrastructure:

| Concern | No service URL | Production URL configured |
|---|---|---|
| Users, refresh sessions, conversations | Atomic JSON files and process lock | PostgreSQL through SQLAlchemy |
| Rate limiting | Process-local sliding window | Atomic Redis sorted-set window |
| Document indexing | Two-thread local executor | RQ queue and Redis worker |
| Upload and index artifacts | Local filesystem, optionally B2 | B2 is required for workers on separate hosts |

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
Index mutations are serialized per user with a Redis lock (or a local lock in
development), preventing concurrent workers from overwriting the same retrieval
artifacts. BM25 is the production default; FAISS artifacts exist only when the
hybrid retrieval mode is explicitly enabled.

When `REDIS_URL` is configured, uploads must be durably copied to B2 before enqueueing because a separate worker cannot rely on the API container's ephemeral filesystem. Configure the B2 variables in both services.

## Deployment sequence

1. Provision PostgreSQL, Redis, B2, and a worker service in staging.
2. Run `alembic upgrade head`.
3. Run the JSON importer with `--dry-run`, then without it.
4. Start the RQ worker and confirm it listens on `nova-index`.
5. Deploy the API with `DATABASE_URL` and `REDIS_URL`.
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
