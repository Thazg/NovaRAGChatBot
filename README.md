# Nova AI Agent

Nova is a production-minded **Retrieval-Augmented Generation (RAG) workspace** for asking grounded questions about private documents. It combines a motion-rich React interface with a FastAPI backend, streaming responses, account-isolated indexes, hybrid retrieval, and optional cloud persistence.

## Why this project stands out

- **End-to-end RAG pipeline** — ingestion, parsing, overlapping chunks, retrieval, prompt construction, citations, and streamed generation.
- **Hybrid search** — BM25 works with no embedding bill; an OpenAI-compatible embedding endpoint enables FAISS + reciprocal-rank fusion.
- **True streaming UX** — Server-Sent Events deliver tokens and action events while supporting cancellation and regeneration.
- **Private multi-user workspaces** — PBKDF2 password hashing, signed tokens, isolated uploads, indexes, and conversations.
- **Production signals** — liveness/readiness probes, provider/model verification, request correlation IDs, response timing, automated tests, and CI.
- **Measured quality** — an offline benchmark enforces Recall@5, mean reciprocal rank, and citation precision; Chromium E2E covers the complete portfolio flow.
- **Resilient persistence** — local storage for development and optional Backblaze B2 synchronization for cloud deployments.
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
| Persistence | Local JSON/filesystem with optional Backblaze B2 |
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

The committed portfolio benchmark currently targets Recall@5 ≥ 0.90, MRR ≥ 0.80, citation precision ≥ 0.90, and backend coverage ≥ 40%. See the [evaluation report](backend/evaluation/README.md) for the recorded scores, per-query results, methodology, and limitations. See `docs/PORTFOLIO_CHECKLIST.md` for the demo-video storyboard, deployment checklist, and PostgreSQL migration plan.

## Operations

| Endpoint | Purpose |
|---|---|
| `GET /health` | Fast liveness check with version, environment, retrieval mode, and uptime |
| `GET /health/ready` | Cached provider check that verifies the configured Groq/Ollama model is actually reachable |
| `GET /docs` | OpenAPI / Swagger documentation |

Every API response includes `X-Request-ID`, `X-Response-Time-Ms`, and `Server-Timing` headers for debugging and latency inspection.

## Security choices

- Passwords use salted PBKDF2-HMAC-SHA256 with 310,000 iterations.
- Tokens are signed with HMAC-SHA256 and expire after 30 days.
- Usernames are normalized and validated before becoming filesystem/storage identifiers.
- Upload size and accepted file types are restricted.
- Sliding-window limits protect authentication and API endpoints and expose standard retry/remaining headers.
- Documents, indexes, and conversations are namespaced by authenticated user ID.
- Secrets stay in environment variables and are excluded from Git.

For a public production deployment, add rate limiting, managed secret rotation, malware scanning, and an external identity provider.

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
- **Filesystem JSON persistence** is easy to inspect and demo; PostgreSQL plus migrations would be the next step for higher concurrency.
- **SSE** is ideal for one-way token streaming; WebSockets would only be justified for collaborative or bidirectional realtime features.
- Next portfolio milestones: expand the human-labeled evaluation dataset, add semantic retrieval ablations, move long-running ingestion to a background queue, and use a shared rate-limit store for multi-replica deployments.

## Deployment

- Live frontend: [novachatbot.vercel.app](https://novachatbot.vercel.app/)
- Production API: `https://novaaiagent-4.onrender.com`
- `render.yaml` provisions the FastAPI service on Render.
- The Vite production build uses the Render API URL from `frontend/.env.production`; a Vercel environment variable can override it.
- Render allows the production frontend origin plus preview URLs belonging to this Vercel project.
- Backblaze B2 variables enable durable uploads, indexes, users, and conversations.

## License

MIT
