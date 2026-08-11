# Nova portfolio delivery checklist

## Automated evidence already in the repository

- Backend unit/API tests with a 40% coverage floor.
- Offline retrieval evaluation with Recall@K, MRR, and citation precision thresholds.
- Chromium E2E for registration, document upload, chat streaming, and a grounded citation.
- Frontend lint, TypeScript build, npm audit, Playwright trace/video support, and GitHub Actions.
- Liveness, provider readiness, request IDs, response timings, and rate-limit headers.

## 60–90 second demo storyboard

| Time | Shot | Narration |
|---|---|---|
| 0–8s | Title and architecture diagram | “Nova is a private RAG workspace built with React, FastAPI, BM25/FAISS, and streamed Groq responses.” |
| 8–22s | Register and upload `portfolio.txt` | “Each account owns an isolated document index and conversation store.” |
| 22–42s | Ask a retrieval question and show streamed citation | “BM25 or hybrid retrieval ranks evidence, then the answer streams over SSE with source citations.” |
| 42–56s | Developer Settings readiness panel | “Readiness verifies the provider/model; every API response carries request ID and latency headers.” |
| 56–70s | Terminal evaluation output | “Offline gates enforce Recall@5, MRR, citation precision, backend coverage, and browser E2E.” |
| 70–85s | GitHub Actions and closing screen | “The same quality gates run on every pull request.” |

Generate a clean 1280×720 product-flow capture with:

```bash
cd frontend
npm run demo:record
```

The WebM video, screenshots, and trace are written to `frontend/demo-artifacts/`. Use the product clip as the middle section of the storyboard, add the architecture/evaluation shots in an editor, export MP4, and place a short optimized GIF under `docs/assets/` for the README.

## Render deployment checklist

1. Create a Render Blueprint from `render.yaml`.
2. Set `GROQ_API_KEY`, a long random `JWT_SECRET`, and optional B2 credentials.
3. Confirm `ENVIRONMENT=production`, `CORS_ORIGINS=https://novachatbot.vercel.app`, and the project-scoped `CORS_ORIGIN_REGEX` from `render.yaml`.
4. Verify `/health`, then `/health/ready?refresh=true`.
5. Send a real chat request and inspect `X-Request-ID`, `X-Response-Time-Ms`, and rate-limit headers.

## Vercel deployment checklist

1. Set the project root to `frontend`.
2. Confirm `VITE_API_BASE_URL=https://novaaiagent-4.onrender.com` (already committed in `frontend/.env.production`, and optionally overridden in Vercel).
3. Deploy using `frontend/vercel.json` and verify SPA refresh routes.
4. Test sign-up, upload, streaming, citation rendering, logout, and a mobile viewport.

## PostgreSQL migration plan

Treat this as a separate migration instead of coupling it to UI work:

1. Introduce a `ConversationRepository` protocol with JSON and PostgreSQL implementations.
2. Add `conversations` and `messages` tables keyed by `user_id`; index `(user_id, updated_at)` and enforce foreign keys.
3. Add Alembic migrations and a one-time JSON-to-PostgreSQL importer.
4. Run dual-read validation in staging, comparing counts and message checksums.
5. Switch writes to PostgreSQL, retain JSON export as a backup format, then remove dual reads.
6. Replace the single-process rate-limit store with Redis when deploying multiple API replicas.
