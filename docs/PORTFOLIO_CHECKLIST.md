# Nova portfolio delivery checklist

## Automated evidence already in the repository

- 77 backend tests with 64.09% production-code coverage and a 64% CI floor (test modules excluded).
- Offline evaluation over 60 labeled queries with retrieval ablations, Recall@K, MRR, citation precision/recall, evidence support, no-answer accuracy, and latency.
- Real-stack FastAPI test with a deterministic LLM, real upload/parsing/index/retrieval, SSE, and final citation.
- Eight Chromium E2E scenarios covering upload/chat/citation, cookie recovery, accessibility, visual regression, and pre/mid-stream reconnect.
- Frontend lint, TypeScript build, npm audit, Playwright trace/video support, and GitHub Actions.
- Liveness, provider readiness, request IDs, response timings, and rate-limit headers.

## 60–90 second demo storyboard

| Time | Shot | Narration |
|---|---|---|
| 0–8s | Title and architecture diagram | “Nova is a private RAG workspace built with React, FastAPI, BM25/FAISS, and streamed Groq responses.” |
| 8–22s | Register and upload `portfolio.txt` | “Each account owns an isolated document index and conversation store.” |
| 22–42s | Ask a retrieval question and show streamed citation | “BM25 or hybrid retrieval ranks evidence, then the answer streams over SSE with source citations.” |
| 42–56s | Developer Settings readiness panel | “Readiness verifies the provider/model; every API response carries request ID and latency headers.” |
| 56–70s | Terminal evaluation output | “Sixty labeled questions enforce retrieval, citation, no-answer, coverage, and browser quality gates.” |
| 70–85s | GitHub Actions and closing screen | “The same quality gates run on every pull request.” |

Generate a clean 1280×720 product-flow capture with:

```bash
cd frontend
npm run demo:record
```

The WebM video, screenshots, and trace are written to `frontend/demo-artifacts/`. Use the product clip as the middle section of the storyboard, add the architecture/evaluation shots in an editor, export MP4, and place a short optimized GIF under `docs/assets/` for the README.

## Render deployment checklist

1. Create a Render Blueprint from `render.yaml`.
2. Set `GROQ_API_KEY`, a unique random `JWT_SECRET` of at least 32 bytes, and optional B2 credentials.
3. Confirm `ENVIRONMENT=production`, `COOKIE_SECURE=true`, `CORS_ORIGINS=https://novachatbot.vercel.app`, and the project-scoped `CORS_ORIGIN_REGEX` from `render.yaml`.
4. Provision ClamAV, set `CLAMAV_HOST`, then set `MALWARE_SCAN_REQUIRED=true` before opening uploads publicly. Verify the EICAR test file is rejected.
5. Verify `/health`, then `/health/ready?refresh=true`.
6. Send a real chat request and inspect `X-Request-ID`, `X-Response-Time-Ms`, and rate-limit headers.

## Vercel deployment checklist

1. Set the project root to `frontend`.
2. Keep `VITE_API_BASE_URL=/api` (already committed); do not point browser auth directly at Render.
3. Deploy using `frontend/vercel.json`, then verify the `/api/*` rewrite, CSP, and SPA refresh routes.
4. Verify login, hard refresh/session restoration, automatic access-token refresh, logout, and that localStorage contains no token.
5. Test a valid upload plus spoofed PDF, oversized file, and unsafe remote-PDF cases; then verify streaming, citations, and a mobile viewport.

## PostgreSQL/Redis rollout

The repository now contains SQLAlchemy repositories, Alembic migrations, an idempotent JSON importer, Redis rate limiting, RQ indexing, job progress, and infrastructure readiness checks. Follow `docs/PRODUCTION_PERSISTENCE.md`; managed services and any paid Render worker must still be provisioned explicitly.
