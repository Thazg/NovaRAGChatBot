# Nova frontend

React 19, TypeScript, Vite, Zustand, Tailwind and Radix UI power the document workspace. This guide covers the browser application's boundaries and development workflow. See the [user guide](../docs/USER_GUIDE.md) for product tasks and the [root README](../README.md) for backend setup.

UI and chat text use the shared platform font stack observed on ChatGPT Web, defined in `src/index.css` and referenced by Tailwind's `font-sans`. Chat paragraphs, lists and the composer use 16px text with 28px line height. Code retains a separate system monospace stack. No external font stylesheet is required.

Conversation text is left-aligned, including streaming output. User messages sit on the right; assistant answers have no surrounding card or speaker avatar. Unordered Markdown lists display hyphen markers, while ordered lists retain their numbers. Copy/share/source formatting uses the underlying answer text rather than CSS markers.

## Run locally

Use Node.js 22.12 or newer, start the FastAPI service, then run from this directory:

```bash
npm ci
cp .env.example .env
npm run dev -- --host 127.0.0.1
```

On PowerShell, use `Copy-Item .env.example .env`. Open the URL printed by Vite, normally `http://127.0.0.1:5173`. Set `VITE_API_BASE_URL=http://127.0.0.1:8000` if using that host for the API. Keep `localhost` versus `127.0.0.1` consistent: browser cookies are tied to the host, and the backend CORS/origin allowlist must include the frontend origin.

`VITE_*` values are public build inputs. Never place provider keys, signing secrets, or database credentials in them. Without an override, development uses the browser hostname on port 8000 (`127.0.0.1` stays `127.0.0.1`; `localhost` stays `localhost`); production deliberately uses `/api` even if a stale `VITE_API_BASE_URL` override exists. Vercel and nginx proxy that same-origin path to FastAPI. `npm run preview` serves static build output and does not create a backend proxy by itself.

## Source map and ownership

| Area | Responsibility |
| --- | --- |
| `src/App.tsx` | Session bootstrap/recovery, provider startup and first-document gate |
| `src/services/apiOrigin.ts` | Same-origin production policy and hostname-aligned development default |
| `src/services/api.ts` | Credentialed fetch, single-flight refresh, session-bound responses, Zod validation and job polling |
| `src/services/eventStream.ts` | Incremental UTF-8/SSE parsing and explicit completion detection |
| `src/services/sources.ts` | Plain filename/page/line references for display, clipboard, sharing and TXT export |
| `src/store/useChatStore.ts` | In-memory account/conversation state and a small persisted UI preference whitelist |
| `src/components/chat/` | Composer, one active request, cancellation/regeneration, rendering and conversation search |
| `src/components/sidebar/DocumentManager.tsx` | Upload/download/reindex/delete actions, document scope and recoverable listing errors |
| `src/components/layout/SettingsDrawer.tsx` | Server preferences, account controls, knowledge base and diagnostics |
| `src/components/ui/` | Shared Radix-based controls; preserve accessible labels/focus behavior when editing |
| `tests/` / `e2e/` | Node unit tests / Chromium workspace and failure scenarios |

Rename, pin, duplicate and delete await server confirmation before updating saved conversation state. Failures retain the prior state and are shown so the user can retry; a new empty-chat placeholder is local until creation/first-turn persistence is acknowledged.

The backend is authoritative for conversations, document IDs, indexing, account preferences and evidence. A document ID is a storage identifier, not its display filename. Send that ID as `document_name` when scoping questions. Do not infer a PDF page or line from answer text.

## Authentication and browser storage

Access tokens remain in module/Zustand memory. The refresh token is an HttpOnly cookie. Requests include credentials; simultaneous 401 responses share one refresh promise. Refreshing after a rejected 401 is an authentication retry, not a retry after an uncertain transport failure.

Login, registration and logout change a session revision. Old refresh/login responses, old authenticated responses and pending preference loads cannot restore credentials or account context after that revision changes. Logout invalidates local credentials immediately, before waiting for its HTTP request.

The `rag-chat-storage` blob stores only theme, sidebar state/tab and the developer-mode toggle. Version 5 migrates older blobs by discarding tokens, account identity, chats, document scope, custom instructions, nickname and avatar. Account context is reset at login/bootstrap/logout and reloaded from server preferences. Avatar images are session-only; they are not uploaded to the backend. Removing browser storage clears UI preferences, not server documents or conversations.

## Chat request lifecycle

```text
Send → create local user/assistant messages → POST /chat/stream
     → evidence + token events → explicit [DONE] → completed answer
                         ↘ failure/Stop/navigation → interrupted answer
```

Only the current request owns its token/evidence callbacks and busy controls. Stop releases ownership before aborting, so a delayed rejection cannot finish a replacement request. Changing conversations or leaving the workspace stops the active browser operation. Regenerate is unavailable while another operation is active; it reuses the latest user turn.

The client requires `[DONE]`; an HTTP 200 followed by EOF is incomplete. It never automatically replays a chat POST after a disconnect because the server may already have accepted the turn. Explicit Regenerate passes `regenerate: true`. Source references are text, such as `Source: paper.pdf, Page 2, Lines 6–9`; neither rendering nor copying requires an uploaded-document viewer. During streaming, source lists and evidence markers are hidden; the empty preview shows only the thinking indicator. A completed citation is not a semantic-factuality guarantee.

`search for …` and `tìm kiếm …` use `/documents/search-download`. A returned `job_id` must finish before the UI claims indexing completed. Stop cancels browser download/polling requests, not an indexing job already accepted by the server. Search progress messages are local UI status; ordinary chat answers are saved through the backend chat lifecycle.

## Document behavior

Uploads accept PDF, DOCX, Markdown, RST, TXT, Python and notebook files, with a client-side 25 MB limit. This is an early usability check; backend validation remains authoritative. Upload/reindex flows poll returned jobs, surface failure messages, and offer document refresh. Listing only exposes `indexed`, not a complete job history: `false` is shown as **Not indexed**, never assumed to mean a job is running. Use Re-index to retry a failed/old index and Refresh to read current shared state.

## Verify changes

Run these commands from `frontend`:

```bash
npm run test
npm run check
npm run e2e:install
npm run e2e -- --workers=2
npm audit --audit-level=high
```

`test` uses Node's TypeScript stripping to exercise the SSE parser and citation formatter. `check` runs oxlint, TypeScript and a production build. Browser tests use deterministic API fixtures, including cancellation races, stale refresh, cross-account storage migration, indexing failure, account-delete retry, source retention after reload, IME input, mobile layout and axe checks. They do not call a paid LLM or send native shares externally. CI runs Chromium on Linux with Node 22; visual baselines are platform-specific.

When adding a response field, update its Zod schema and fixture, then add a test for the observable behavior. Keep failure cases explicit instead of weakening schemas to accept unexpected data. Use a focused `--grep` while developing, then run the full suite after integration. Respect `prefers-reduced-motion`; CSS and the root `MotionConfig` handle their respective animation systems.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Session recovery screen | Restore API connectivity and choose Retry session; a temporary error should not force a false logout. |
| Repeated 401/refresh failure | Verify the same browser host, backend origin allowlist and proxy cookies; sign in again after an expired/revoked session. |
| JSON/Zod error | Compare the backend response with the schema/fixture; check whether the frontend and API versions match. |
| Document unavailable after upload | Read the indexing error, Refresh, then Re-index if appropriate; a successful upload is not proof of completed indexing. |
| Interrupted answer | Keep the partial text as incomplete and use Regenerate. Do not add transport retries to the POST. |
| Copy contains no page/line | Legacy answers/indexes may lack provenance; reindex and ask again. Do not invent locations for old messages. |
| Local test `spawn EPERM` | Windows execution restrictions can block Node/browser subprocesses; run the approved test command with the necessary execution permissions. |

The deterministic suite verifies browser contracts. Real proxy cookie behavior, distributed workers/storage and provider generation still require staging tests; frontend test success is not proof that those services are configured.
