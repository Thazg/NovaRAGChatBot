# Configuration reference

Backend settings are defined in [`config/settings.py`](../backend/config/settings.py). Python loads `backend/.env` on import; existing process environment variables take precedence. Restart every API and worker process after changes. The frontend reads Vite variables at dev-server start/build time; never put provider or storage secrets in a `VITE_` variable.

## Working local configurations

Copy the [backend example](../.env.example) to `backend/.env`, and [frontend example](../frontend/.env.example) to `frontend/.env`. Generate your own JWT secret, for example with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Keep the generated value in your local environment; do not commit it.

For the default cloud-chat/local-storage workflow:

```dotenv
ENVIRONMENT=development
LLM_PROVIDER=groq
GROQ_API_KEY=your-provider-key
RETRIEVAL_MODE=bm25
COOKIE_SECURE=false
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Set `JWT_SECRET` separately to your generated value. For local Ollama, use `LLM_PROVIDER=ollama`, `OLLAMA_URL=http://localhost:11434`, and an installed `MODEL_NAME`; a Groq key is then unnecessary. Starting a provider or downloading a model is a separate operator action.

Use matching hostnames in the browser and API (`127.0.0.1` with `127.0.0.1`, or `localhost` with `localhost`) so refresh-cookie behavior is consistent. Different ports are separate origins and must be allowed by CORS; changing from `localhost` to `127.0.0.1` is also a cookie-host/site change.

## Application, provider and retrieval

Defaults below are code defaults, not a promise about a running deployment. Durations are seconds unless stated otherwise.

| Setting | Default | Behavior |
| --- | --- | --- |
| `APP_VERSION` | `1.0.0` | API/monitoring release label; not an automatic migration mechanism |
| `ENVIRONMENT` | `development` | `development`, `test`, `staging`, `production`; production enables stricter startup checks. Use production security settings for staging with real data |
| `LLM_PROVIDER` | `groq` | `groq` or `ollama` |
| `GROQ_API_KEY` | empty | Server-side chat credential; only needed for Groq |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Requested model ID; availability is checked against the provider, not guaranteed by this repository |
| `OLLAMA_URL` | `http://localhost:11434` | API/worker-reachable local-model server |
| `MODEL_NAME` | `qwen3:4b-instruct` | Local model name |
| `OLLAMA_KEEP_ALIVE` | `30m` | Provider keep-alive option |
| `RETRIEVAL_MODE` | `bm25` | Default lexical retrieval; `hybrid` opts into embeddings/FAISS |
| `TOP_K` | `5` | Production result count, runtime clamps requested counts to 1–15 |
| `RRF_K` | `60` | Fusion constant for optional hybrid ranking |
| `EMBEDDING_BASE_URL` | empty | OpenAI-compatible embedding endpoint; leave empty for BM25 |
| `EMBEDDING_API_KEY` | empty | Server-side embedding credential |
| `EMBEDDING_MODEL` | `nomic-embed-text-v1.5` | Embedding model identifier |
| `EMBEDDING_DIM` | `768` | Legacy declared dimension; current arrays/FAISS use actual validated returned dimensions and reject a query/index mismatch |
| `BROAD_TOP_K` | `20` | Legacy configuration surface; current production query entry clamps counts independently, not an abstention policy |
| `MIN_SIMILARITY_SCORE` | `0.0` | Legacy surface; current production wrapper does not use this value as a calibrated rejection threshold |
| `RETRIEVAL_CONFIDENCE_THRESHOLD` | `0.0` | Legacy surface; setting it does not implement validated abstention |

Neither BM25 scores nor hybrid score normalization are probabilities of answer correctness. See [RAG contracts](RAG_PIPELINE.md) before changing retrieval policy.

New dense snapshots record the configured embedding model, endpoint hash and document/query prefixes. Changing that identity, or loading a legacy vector snapshot without it, falls back to BM25. Reindex to restore dense retrieval with the new model. Rotating only the credential does not change the embedding identity; changing provider weights behind the same ID is not automatically detectable.

## Prompt and generation budgets

| Setting | Default | Behavior |
| --- | --- | --- |
| `TEMPERATURE` | `0.1` | Chat sampling setting |
| `LLM_TOP_K` | `40` | Ollama sampling option |
| `LLM_TOP_P` | `0.9` | Sampling option |
| `LLM_SEED` | `42` | Provider request seed when supported; not an exact-output guarantee |
| `MAX_TOKENS` | `2048` | Requested output budget |
| `NUM_CTX` | `8192` | Ollama context option; not a Groq context override |
| `MAX_HISTORY_MESSAGES` | `4` | Number of prompt-history messages, each additionally truncated by prompt construction |
| `MAX_CHUNK_CHARS` | `2400` | Per-passage character cap; smaller caps select query windows |
| `MAX_CONTEXT_CHARS` | `10000` | Total packed context including evidence headers |

Character budgets are not token counts. Verify full input/history/output budgets for the provider/model and languages you operate; do not infer context-window safety from an English-corpus character benchmark.

## Authentication, origins and request limiting

| Setting | Default | Behavior |
| --- | --- | --- |
| `JWT_SECRET` | Development-only default | Production rejects the built-in/example secret and secrets shorter than 32 UTF-8 bytes; generate a unique value |
| `ACCESS_TOKEN_TTL_SECONDS` | `600` | Short-lived bearer token lifetime |
| `REFRESH_TOKEN_TTL_SECONDS` | `2592000` | Refresh lifetime; server records store hashes |
| `COOKIE_SECURE` | true in production, false otherwise | Production requires true; use HTTPS |
| `REFRESH_COOKIE_NAME` | `__Host-nova_refresh` when secure, otherwise `nova_refresh` | Host-prefixed cookies require secure transport and path `/`; no Domain attribute is set |
| `REFRESH_COOKIE_SAMESITE` | `strict` when secure, otherwise `lax` | `lax`, `strict`, `none`; `none` requires secure cookies |
| `CORS_ORIGINS` | Local ports 3000/5173 on localhost/127.0.0.1 and the hosted frontend | Comma-separated exact browser origins. Cookie-backed auth uses the same allowlist; production rejects missing/untrusted Origin |
| `CORS_ORIGIN_REGEX` | Project/team-specific Vercel preview pattern | Full regex match; set deliberately, never a blanket all-preview rule |
| `RATE_LIMIT_ENABLED` | `true` | Disable only deliberately in isolated tests/development |
| `RATE_LIMIT_REQUESTS` | `120` | General request count per window |
| `AUTH_RATE_LIMIT_REQUESTS` | `10` | Login/registration count per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Sliding window duration |

API `/docs` and `/openapi.json` are public documentation, while private operations require Bearer authorization. Calling login from Swagger still requires an allowed browser Origin. Production builds use the same-origin `/api` proxy regardless of an old `VITE_API_BASE_URL` override.

## Persistence, jobs and observability

| Setting | Default | Behavior |
| --- | --- | --- |
| `DATABASE_URL` | empty | Empty: single-process JSON users/sessions/conversations. Configured: SQLAlchemy database; production requires Alembic schema. Preferences remain separate local/B2 files |
| `REDIS_URL` | empty | Empty: local rate limiter/two-thread indexing. Configured: Redis limiting, RQ queue and per-user shared locks; remote artifact storage is required |
| `B2_KEY_ID`, `B2_APP_KEY` | empty | Both enable remote index/barrier authority. Failed required reads/writes fail closed; these are not browser credentials |
| `B2_BUCKET` | `nova-ai-storage` | Object-store bucket |
| `B2_ENDPOINT` | `https://s3.us-west-004.backblazeb2.com` | S3-compatible endpoint |
| `UPLOAD_FOLDER` | `backend/uploads` | Absolute resolved upload root. Compose sets `/app/Dataset/uploads` to match its named volume |
| `READINESS_CACHE_SECONDS` | `10` | Readiness result cache; use `?refresh=true` for a fresh operator check |
| `LOG_LEVEL` | `INFO` | Application logging level |
| `SENTRY_DSN` | empty | Optional error/trace destination; no monitoring events when empty |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.05` | Trace sampling fraction, clamped at initialization |

The process is configured at import time; setting `DATABASE_URL` in a shell does not migrate existing JSON state. Follow [the migration runbook](PRODUCTION_PERSISTENCE.md). Multiple hosts need shared configuration and a real staging exercise.

## Upload and parser budgets

| Setting | Default | Meaning |
| --- | --- | --- |
| `MAX_UPLOAD_BYTES` | `26214400` | 25 MiB backend upload limit; frontend currently also has a fixed 25 MiB UX check |
| `MAX_PDF_PAGES` | `500` | PDF page cap |
| `MAX_PDF_OBJECTS` | `100000` | PDF object cap |
| `MAX_PDF_DECOMPRESSED_STREAM_BYTES` | `10485760` | Per-stream PDF decompression budget |
| `MAX_PDF_EXTRACTED_CHARS` | `5000000` | Total extracted PDF text cap |
| `MAX_ARCHIVE_ENTRIES` | `2000` | DOCX/notebook-related archive validation budget |
| `MAX_ARCHIVE_UNCOMPRESSED_BYTES` | `104857600` | Archive uncompressed-byte cap |
| `MAX_ARCHIVE_COMPRESSION_RATIO` | `100` | Archive compression-ratio cap |
| `MAX_NOTEBOOK_CELLS` | `2000` | Notebook cell cap |
| `CLAMAV_HOST` | empty | Optional scanner host |
| `CLAMAV_PORT` | `3310` | Scanner port |
| `MALWARE_SCAN_REQUIRED` | `false` | When true, missing/unresponsive scanner fails readiness and uploads fail closed |

Positive limits, provider/retrieval enums and cookie combinations are validated at startup. Size budgets do not provide process isolation or OCR support. See [upload security](UPLOAD_SECURITY.md) for type/signature/parser checks and network-download restrictions.
