# API reference and client contracts

The backend routes have no `/api` prefix. Local examples use `http://127.0.0.1:8000`; the deployed browser uses its same-origin `/api` proxy. Swagger is at `/docs`, ReDoc at `/redoc`, and the generated schema at `/openapi.json`. These are public and describe Bearer authentication for private operations. This guide covers behavior beyond request schemas, especially streaming, job completion and retry rules.

## Authentication

All application-data endpoints require `Authorization: Bearer <access_token>`. Register/login/refresh/logout and health endpoints do not require an access token. An authenticated request still needs an existing account; ownership is derived from that account, never a `user_id` JSON field.

| Method and path | Request | Result |
| --- | --- | --- |
| `POST /auth/register` | `username` (2–40), `password` (8–256) | Access token/user ID/username; refresh cookie. Username is normalized and restricted to letters/digits/`_.-`. 400 if unavailable/invalid. |
| `POST /auth/login` | `username`, `password` | Same session response; 401 for invalid credentials. |
| `POST /auth/refresh` | Refresh cookie, no JSON required | Rotates single-use refresh record and cookie; returns a fresh access token. 401 if expired/consumed. |
| `POST /auth/logout` | Refresh cookie | Revokes that refresh record, expires cookie, returns success. |
| `GET /auth/me` | Bearer token | `user_id`, `username`. |
| `GET /auth/preferences` | Bearer token | Current preferences; display name falls back to username. |
| `PUT /auth/preferences` | Full preference object | Replaces preferences; omitted fields receive model defaults. |
| `PATCH /auth/preferences` | Changed preference fields | Merges non-null supplied fields. |
| `POST /auth/change-password` | `current_password`, `new_password` (8–256) | Changes password, revokes existing refresh records, issues a replacement refresh cookie. |
| `GET /auth/export` | Bearer token | Account metadata, preferences, conversations/evidence and document metadata; no document binaries. |
| `DELETE /auth/account` | Bearer token | Removes active artifacts before deleting credentials and clearing the refresh cookie. 503 keeps the account available for authenticated cleanup retry. |

Cookie POSTs reject untrusted `Origin` with 403; production also rejects a missing `Origin`. Production defaults are a Secure, HttpOnly, SameSite=Strict, host-only `__Host-nova_refresh` cookie. Access tokens default to 600 seconds, refresh records to 30 days. Refresh tokens never belong in the Bearer header or JSON/localStorage. Logout revokes the refresh record, not every already-issued access token; a previously issued access token can remain usable until expiry while the account still exists.

Preference fields: `display_name` ≤80, `theme` = `dark|light|system`, `language` = `auto|english|vietnamese`, `character_style` = `warm|enthusiastic|professional|concise|friendly|custom`, `nickname` ≤80, `custom_instructions` ≤4000. Read the [session security](SESSION_SECURITY.md) and [architecture](ARCHITECTURE.md) notes before using local preferences across replicas.

### Local login example (Bash)

```bash
curl --cookie-jar cookies.txt \
  --header 'Origin: http://127.0.0.1:5173' \
  --header 'Content-Type: application/json' \
  --data '{"username":"example.user","password":"replace-with-your-password"}' \
  http://127.0.0.1:8000/auth/login
```

Copy the returned access token to a local `ACCESS_TOKEN` variable for the examples below. Keep the cookie jar and token out of Git. PowerShell users should use `curl.exe` and adapt environment-variable syntax, or use Swagger's Authorize button.

## Documents and background jobs

| Method and path | Input | Completion contract |
| --- | --- | --- |
| `GET /documents` | Bearer token | Array of `{id,name,size,indexed,chunks,source_url?}`; merged local/remote IDs, excluding deleted documents. |
| `GET /documents/{id}/download` | Bearer token, storage ID | Original file bytes as an attachment with the original display filename; private/no-store. Owner-only, 404 for missing/deleted documents, 503 when remote storage is unavailable. |
| `POST /documents/upload` | Multipart field `file` | **202** with storage `id`, display `filename`, `job_id`, `indexed:false`, `status:"queued"`, `progress:0`. |
| `GET /documents/jobs/{job_id}` | Returned job ID | Owner-only state/progress/result. 404 for missing, expired or another user's job. |
| `POST /documents/reindex` | No JSON required | Queues full reindex; JSON includes `job_id`. Current route returns 200 with `status:"queued"`; it is still asynchronous. |
| `DELETE /documents/{id}` | Storage ID from listing/upload | Removes that document. Failed cleanup is retryable; deletion barriers exclude old evidence. |
| `DELETE /documents/clear-all` | No JSON required | Removes current documents and publishes empty index; retained deletion barriers prevent old jobs from reviving uploads. |
| `POST /documents/summarize` | `{"filename":"<storage-id-or-display-name>"}` | JSON `{summary,chunks,filename}`; no streaming or evidence IDs. Storage IDs take precedence; ambiguous display names return 400, missing chunks 404, provider failure/empty output 503. Input is capped at the first 20,000 joined characters. |
| `POST /documents/search-download` | `query` 2–300, `max_results` 1–5 (default 3) | Downloads validated PDFs and may return a reindex `job_id`. `downloaded` entries contain `{id,file_name,new}`. Search failure may return 502; no results is a successful empty list. |

Use storage IDs for actions/scope when display names collide. An upload filename is not its storage ID. Supported extensions are `.pdf`, `.docx`, `.txt`, `.md`, `.markdown`, `.rst`, `.py`, `.ipynb`; byte/MIME/parser safety checks also apply. The default byte limit is 25 MiB; malformed/unsupported uploads return 415 and oversize uploads return 413.

```bash
curl --header "Authorization: Bearer $ACCESS_TOKEN" \
  --form 'file=@notes.pdf' http://127.0.0.1:8000/documents/upload

curl --header "Authorization: Bearer $ACCESS_TOKEN" \
  http://127.0.0.1:8000/documents/jobs/RETURNED_JOB_ID
```

Job JSON contains `id`, `status`, `progress`, optional `result` and optional `error`. Local states are `queued → started → finished|failed`; RQ may additionally report `deferred`, `scheduled`, `stopped` or `canceled`. `finished` includes counts in `result`; failed jobs expose a public error, not a traceback. RQ results expire after one hour, failed jobs after one day; local state is purged after one day and lost on process restart. Polling a vanished job is not proof that indexing succeeded. Refresh document listing and, if needed, request an explicit reindex.

## Chat: POST-based SSE

`POST /chat/stream` and `POST /chat` are aliases. Both return `text/event-stream`; `stream` is retained as a compatibility field and does not select a JSON response.

```json
{
  "session_id": "2e3bd840-9cac-4fb3-9a59-c245b71c2907",
  "question": "What does the evaluation section conclude?",
  "document_name": "stored-document-id.pdf",
  "instructions": "Answer concisely.",
  "language": "english",
  "regenerate": false,
  "stream": true
}
```

| Field | Constraint/meaning |
| --- | --- |
| `session_id` | Required, 1–36 letters/digits/`_-`; clients should use a conversation UUID. This is a key, never a path. |
| `question` | Required, 1–8000 characters. Whitespace-only input receives a local prompt to enter a question. |
| `document_name` | Optional, ≤180 characters; scope by storage ID or display name. Empty means all current documents. |
| `instructions` | Optional, ≤4000 characters. |
| `language` | Empty/`auto`, `english`, or `vietnamese`. |
| `regenerate` | Explicitly replace the matching latest assistant reply, reusing its user turn. |

Use `fetch`/a streaming HTTP client, not browser `EventSource`, because this is a POST with a body and Bearer header. Frames are delimited by a blank line. JSON may be split across arbitrary network chunks; decode incremental UTF-8 and accumulate complete frames.

```text
data: {"evidence":[{"id":"E1","document_id":"stored.pdf","file_name":"notes.pdf","page":2,"line_start":6,"line_end":9,"chunk_index":1,"content":"Supporting extracted text."}]}

data: {"token":"The evaluation found ... [E1]."}

data: [DONE]

```

Normal document-answer streams begin with `evidence`, then tokens. `page`/line positions may be null for legacy indexes or formats without page metadata. After completion, the UI renders known IDs as plain `Source: notes.pdf, Page 2, Lines 6–9`; streaming previews hide citations and source lists. PDF lines are 1-based per extracted page, including blanks. These positions describe extraction; they are not fabricated by the model. Standalone greetings and whitespace-only input are local token streams with `[DONE]`, without an evidence frame.

Unknown reserved `[E#]` IDs prevent successful completion: the API retains the attempt as interrupted and emits an error without `[DONE]`. This validates identifiers only, not claim entailment. A provider failure also preserves any short buffered token batch already produced; the browser receives that prefix followed by an error. Follow-up retrieval expansion uses bounded prior user questions, not generated assistant answers; standalone summaries and short new topics do not inherit the earlier answer as search terms.

If no evidence is found, the stream may also send `{"action":"search_offer","query":"..."}`. That event is a suggestion, not an automatic download. The client must interpret only supported events and must not treat an action as answer text.

**Only `[DONE]` confirms completion.** Once headers are sent, a provider error cannot become an HTTP 503; the server sends `{"error":"Response interrupted. Regenerate the answer to try again."}` and omits `[DONE]`. EOF, a fetch exception, abort or malformed protocol must leave the answer incomplete. Do not automatically replay the POST: a first request may already have saved messages or generated a different partial answer. Explicit regeneration is the recovery operation. The server saves a completed assistant answer/evidence before acknowledging `[DONE]`; interrupted answers are marked `interrupted:true`.

## Conversations

| Method and path | Behavior |
| --- | --- |
| `GET /conversation` | Owner's conversations, latest update first. |
| `POST /conversation/new` | Optional body with UUID `id`, `title` (1–120, default New Chat), `messages` (≤200) and `pinned`. Existing same-owner ID is returned rather than overwritten. |
| `GET /conversation/{id}` | Full owned conversation; 404 when missing/not owned. |
| `PUT /conversation/{id}` | Update optional `title` and/or `pinned`. |
| `DELETE /conversation/{id}` | Delete one owned conversation. |
| `DELETE /conversation` | Clear owner's conversations; response includes deleted count. |

Conversation JSON uses `id`, `title`, `messages`, `createdAt`, `updatedAt`, `pinned`. Timestamps are Unix milliseconds. Message fields include `id`, `role` (`user|assistant|system`), `content` (≤200,000 characters on create), `createdAt`, `retrievedDocs` (≤15 objects) and `interrupted`. Evidence remains structured in account JSON exports. Treat imported/client-authored evidence as supplied data, not as independently verified citations.

## Health, errors and cleanup

`GET|HEAD /health` (also `/health/`) reports configuration/liveness. `GET /health/ready` returns 200 when configured probes pass, otherwise 503; `?refresh=true` bypasses its brief cache. `X-Readiness-Cache` reports HIT/MISS. Readiness probes provider/model and required infrastructure, not generated-answer accuracy.

| Status | Client action |
| --- | --- |
| 400 | Correct invalid filename/ID/credentials or business input. |
| 401 | Restore the session once through refresh, or sign in. Never use refresh-token JSON/Bearer workarounds. |
| 403 | Correct cookie endpoint Origin/proxy configuration. |
| 404 | Resource absent/not owned, job expired, or no indexed content. |
| 409 | Account cleanup has begun and new writes are blocked; retry `DELETE /auth/account` to finish. A conflicting resource ID may also require a new ID. |
| 413 / 415 | Reduce upload size / supply a supported, valid document. |
| 422 | Correct fields using the generated request schema; `detail` is a validation-error array. |
| 429 | Honor `Retry-After`; rate-limit headers report limit/remaining. |
| 500 / 502 / 503 | Preserve request ID and diagnose storage/provider/queue failure. Retry mutations only using their documented semantics. |

Most application errors use `{"detail":"..."}`; unexpected exceptions use a generic detail plus `request_id`. Routine responses include `X-Request-ID`, `X-Response-Time-Ms` and `Server-Timing`; timing is response setup, not end-to-end generation duration. Logs/worker tracebacks are not a client API.

Deletion cannot promise erasure from provider-level backups or retained operational logs. Document cleanup can fail after a durable deletion barrier is committed; repeat the same DELETE rather than re-uploading it or removing barriers. Migration, retained snapshots, account cleanup and recovery procedures belong in [production persistence](PRODUCTION_PERSISTENCE.md). No endpoint serves a user's original document through a public citation link.

Contract regression tests: [`test_api.py`](../backend/tests/test_api.py), [`test_chat_contracts.py`](../backend/tests/test_chat_contracts.py), [`test_chat_evidence.py`](../backend/tests/test_chat_evidence.py), [`test_document_lifecycle.py`](../backend/tests/test_document_lifecycle.py), and [`test_integration_stack.py`](../backend/tests/test_integration_stack.py).
