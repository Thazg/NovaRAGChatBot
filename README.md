# Nova AI Agent

Nova is a production-minded **Retrieval-Augmented Generation (RAG) workspace** for asking grounded questions about private documents. It combines a motion-rich React interface with a FastAPI backend, streaming responses, account-isolated indexes, hybrid retrieval, and optional cloud persistence.

## Why this project stands out

- **End-to-end RAG pipeline** — ingestion, parsing, overlapping chunks, retrieval, prompt construction, citations, and streamed generation.
- **Hybrid search** — BM25 works with no embedding bill; an OpenAI-compatible embedding endpoint enables FAISS + reciprocal-rank fusion.
- **True streaming UX** — Server-Sent Events deliver tokens and action events while supporting cancellation and regeneration.
- **Private multi-user workspaces** — PBKDF2 password hashing, signed tokens, isolated uploads, indexes, and conversations.
- **Production signals** — liveness/readiness probes, provider/model verification, request correlation IDs, response timing, automated tests, and CI.
- **Measured quality** — 60 labeled queries enforce Recall@5, MRR, citation precision/recall, evidence support, and no-answer behavior; Chromium E2E covers the complete portfolio flow.
- **Resilient persistence** — lightweight local state in development; PostgreSQL, Redis/RQ, and Backblaze B2 for multi-replica production.
- **Polished interface** — light/dark/system themes, responsive layouts, keyboard workflows, smooth motion, and reduced-motion support.

## Architecture

```text
┌─────────────────────────────┐       SSE / REST       ┌─────────────────────────────┐
│ React 19 + TypeScript       │ ─────────────────────▶ │ FastAPI                     │
│ Zustand + Tailwind + Motion │ ◀───────────────────── │ Auth + conversations        │
└─────────────────────────────┘                        └──────────────┬──────────────┘
                                                                    │
                                      ┌─────────────────────────────┼──────────────────────┐
                                      │                             │                      │
                              ┌───────▼────────┐           ┌────────▼────────┐    ┌────────▼────────┐
                              │ BM25 / FAISS   │           │ Groq or Ollama  │    │ Local / B2      │
                              │ RRF re-ranking │           │ Streaming LLM   │    │ Persistence     │
                              └────────────────┘           └─────────────────┘    └─────────────────┘
```

### Request flow

1. A document is parsed, normalized, chunked, and stored in the user's isolated index.
2. A question is expanded and retrieved with BM25 or optional BM25 + FAISS fusion.
3. Ranked chunks, source metadata, conversation history, and user preferences form the prompt.
4. Groq or Ollama streams the grounded response to the browser over SSE.

## Technology

| Layer | Stack |
|---|---|
| Frontend | React 19, TypeScript, Vite, Zustand, Tailwind CSS, shadcn/ui, Framer Motion |
| Backend | Python 3.12, FastAPI, Pydantic, HTTPX |
| Retrieval | rank-bm25, optional FAISS, query expansion, reciprocal-rank fusion |
| Documents | PDF, DOCX, Markdown, RST, TXT, Python, Jupyter Notebook |
| AI providers | Groq cloud API or local Ollama |
| Persistence | PostgreSQL + Redis/RQ in production; Backblaze B2 for file/index artifacts |
| Delivery | Docker Compose, Render, Vercel, GitHub Actions |

## Quick start

### 1. Configure the environment

```bash
git clone <your-repository-url>
cd NovaRAGChatbot
cp .env.example backend/.env
```

Set at least these values in `backend/.env`:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_key
JWT_SECRET=replace_with_a_long_random_secret
```

For local Ollama, set `LLM_PROVIDER=ollama`, `OLLAMA_URL`, and `MODEL_NAME` instead.

### 2. Run the backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

### 3. Run the frontend

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`. Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

### Docker Compose

```bash
docker compose up --build
```

The Compose setup exposes the backend on port `8000` and the frontend on port `3000`.

## Quality gates

```bash
# Backend tests and coverage
pip install -r backend/requirements-dev.txt
pytest --cov --cov-report=term-missing

# Offline retrieval/citation evaluation
cd backend
python -m evaluation.run --k 5

# Frontend lint, typecheck, and production build
cd frontend
npm run check

# Deterministic browser E2E (login → upload → chat → citation)
npm run e2e
```

GitHub Actions runs both quality gates for pushes to `main` and every pull request.

The committed benchmark currently records Recall@5 **0.9821**, MRR **0.9554**, citation precision/recall **1.0000**, and no-answer accuracy **1.0000**. The 79-test backend suite measures **64.35% production-code coverage** with a **64%** CI floor; test modules are excluded from the measurement. See the [evaluation report](backend/evaluation/README.md) for the ablation, provider-backed commands, exact results, and limitations. See `docs/PORTFOLIO_CHECKLIST.md` for the demo and deployment checklists.

## Operations

| Endpoint | Purpose |
|---|---|
| `GET /health` | Fast liveness check with version, environment, retrieval mode, and uptime |
| `GET /health/ready` | Provider/model plus PostgreSQL, Redis, and RQ worker readiness |
| `GET /docs` | OpenAPI / Swagger documentation |

Every API response includes `X-Request-ID`, `X-Response-Time-Ms`, and `Server-Timing` headers for debugging and latency inspection.

## Security choices

- Passwords use salted PBKDF2-HMAC-SHA256 with 310,000 iterations.
- Access tokens are signed with HMAC-SHA256, expire after 10 minutes, and exist only in JavaScript memory.
- Refresh tokens rotate on every use and live in a `Secure; HttpOnly; SameSite=Strict` host-only cookie in production. Only their SHA-256 hashes are persisted server-side.
- Cookie-backed auth endpoints verify the browser `Origin`; Vercel proxies `/api/*` to Render so production authentication remains same-origin.
- Logout revokes the refresh session, expires its cookie, and clears browser cache/cookies. Legacy tokens are removed from persisted Zustand state during migration.
- Production refuses to boot with a missing/default JWT secret or one shorter than 32 bytes.
- Usernames are normalized and validated before becoming filesystem/storage identifiers.
- Uploads are quarantined under a temporary name, bounded by size, checked against an extension/MIME allowlist, parsed by file signature and structure, scanned for malware, and stored under a server-generated UUID.
- PDF/DOCX complexity limits reject encrypted or active PDFs, embedded content, zip bombs, unsafe relationships, and malformed archives before indexing.
- Search-download blocks credentials, unsafe schemes/ports, every non-public DNS answer, DNS rebinding to a private connected peer, and unsafe redirects; downloaded bytes must still pass MIME, size, PDF signature, parser, and malware checks.
- PostgreSQL transactions protect shared users/conversations, Redis provides replica-wide rate limiting, and RQ moves parsing/indexing to monitored jobs.
- Optional Sentry monitoring runs with PII disabled; readiness fails closed when shared workers lack B2 or required ClamAV scanning.
- Sliding-window limits protect authentication and API endpoints and expose standard retry/remaining headers.
- Documents, indexes, and conversations are namespaced by authenticated user ID.
- Secrets stay in environment variables and are excluded from Git.

See [`docs/SESSION_SECURITY.md`](docs/SESSION_SECURITY.md) and [`docs/UPLOAD_SECURITY.md`](docs/UPLOAD_SECURITY.md) for threat models, deployment variables, and verification checklists.

## Repository structure

```text
backend/
├── api/routes/          # Auth, chat, documents, conversations, health
├── rag/                 # Parsing, chunking, retrieval, prompts, LLM clients
├── services/            # Auth, persistence, B2 integration
└── tests/               # Unit and API contract tests

frontend/
└── src/
    ├── components/      # Chat, onboarding, sidebar, settings, UI primitives
    ├── services/        # Typed REST and SSE client
    ├── store/           # Zustand application state
    └── hooks/           # Shared React hooks
```

## Engineering trade-offs and roadmap

- **BM25-first** keeps local development free and predictable, but semantic retrieval needs a separately configured embedding endpoint.
- **Dual runtime modes** keep JSON/thread-local services convenient for development; production switches users, refresh sessions, and conversations to PostgreSQL, rate limiting to Redis, and indexing to RQ workers.
- **B2 stores artifacts, not relational state** when PostgreSQL is enabled. Separate workers require B2 because platform filesystems are ephemeral and not shared.
- **SSE** is ideal for one-way token streaming; WebSockets would only be justified for collaborative or bidirectional realtime features.
- Next portfolio milestone: configure a real embedding endpoint, explicitly approve the provider-backed answer run, and publish those live cost/latency artifacts beside the reproducible offline report.

See [`docs/PRODUCTION_PERSISTENCE.md`](docs/PRODUCTION_PERSISTENCE.md) for migrations, JSON import, RQ worker startup, readiness, and rollout order.

## Deployment

- Live frontend: [novachatbot.vercel.app](https://novachatbot.vercel.app/)
- Production API: `https://novaaiagent-4.onrender.com`
- `render.yaml` provisions the FastAPI service on Render.
- The Vite production build calls same-origin `/api`; `frontend/vercel.json` securely rewrites that path to Render and adds browser security headers.
- Render allows the production frontend origin plus preview URLs belonging to this Vercel project.
- PostgreSQL stores users, refresh sessions, and conversations; Backblaze B2 stores durable upload/index artifacts used by API and worker replicas.

## License

This project is currently shared as part of my portfolio. I haven't added a formal open-source license yet, so please contact me before reusing substantial parts of the repository.
