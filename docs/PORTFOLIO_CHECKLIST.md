# Release and demonstration checklist

## Repository verification status

- 90 backend tests pass locally; CI enforces a 64% production-code coverage
  floor with test modules excluded from the denominator.
- The retrieval dataset contains 100 questions derived from 10 checksum-pinned
  arXiv PDFs, with page-level evidence and per-query results.
- The production-method benchmark compares BM25, neural dense retrieval, equal
  RRF, weighted RRF, cross-encoder reranking, and deterministic multi-query
  retrieval with P50/P95 latency.
- BM25 is the configured production default based on the recorded
  quality/latency comparison.
- The integration suite covers real upload, parsing, indexing, retrieval, SSE
  delivery, and final citations with a deterministic LLM adapter.
- Chromium end-to-end scenarios cover authentication, upload, chat, citations,
  session recovery, accessibility, visual regression, and reconnect behavior.
- Operational verification includes liveness, provider readiness, request IDs,
  response timings, rate-limit headers, frontend checks, dependency audit, and
  GitHub Actions.

## Demonstration sequence (60–90 seconds)

| Time | Visual | Technical narrative |
|---|---|---|
| 0–8 s | Product title and architecture diagram | “Nova is a private-document RAG system built with React, FastAPI, production-default BM25 retrieval, and streamed Groq or Ollama responses.” |
| 8–22 s | Registration and document upload | “Each account owns an isolated document namespace, index, and conversation history.” |
| 22–42 s | Retrieval question and streamed citation | “BM25 ranks the evidence; the grounded answer is delivered over SSE with source citations.” |
| 42–56 s | Readiness and diagnostics panel | “Readiness validates the configured provider and infrastructure; each API response carries request and latency metadata.” |
| 56–72 s | Retrieval evaluation report | “One hundred labeled questions compare six retrieval strategies and document the production selection.” |
| 72–85 s | GitHub Actions summary | “The CI workflow reproduces the corpus, runs evaluation gates, and verifies backend and frontend behavior.” |

Generate the deterministic 1280×720 product-flow recording with:

```bash
cd frontend
npm run demo:record
```

Artifacts are written to `frontend/demo-artifacts/`. Use the browser recording
for the product workflow and add architecture, evaluation, and CI views during
editing. Export the final demonstration as MP4; include an optimized GIF only
when repository size and rendering quality remain acceptable.

## Render deployment verification

1. Create a Render Blueprint from `render.yaml`.
2. Configure `GROQ_API_KEY`, a unique `JWT_SECRET` of at least 32 bytes, and the
   required PostgreSQL, Redis, and B2 credentials.
3. Confirm `ENVIRONMENT=production`, `RETRIEVAL_MODE=bm25`,
   `COOKIE_SECURE=true`, `CORS_ORIGINS=https://novachatbot.vercel.app`, and the
   project-scoped `CORS_ORIGIN_REGEX` from `render.yaml`.
4. Provision ClamAV, set `CLAMAV_HOST`, and enable
   `MALWARE_SCAN_REQUIRED=true` before public uploads. Verify that the EICAR
   test file is rejected.
5. Verify `/health` and `/health/ready?refresh=true`.
6. Submit a real chat request and inspect `X-Request-ID`,
   `X-Response-Time-Ms`, and rate-limit headers.

## Vercel deployment verification

1. Set the Vercel project root to `frontend`.
2. Keep `VITE_API_BASE_URL=/api`; browser authentication must not call Render
   directly.
3. Deploy with `frontend/vercel.json`, then verify the `/api/*` rewrite, Content
   Security Policy, and single-page application refresh routes.
4. Verify login, hard-refresh session restoration, automatic access-token
   refresh, logout, and absence of credentials in local storage.
5. Test a valid upload, spoofed PDF, oversized file, and unsafe remote-PDF
   cases; then verify streaming, citations, and a mobile viewport.

## PostgreSQL and Redis rollout

The repository includes SQLAlchemy repositories, Alembic migrations, an
idempotent JSON importer, Redis-backed rate limiting, RQ indexing, job progress,
and infrastructure readiness checks. Follow
[`PRODUCTION_PERSISTENCE.md`](./PRODUCTION_PERSISTENCE.md). Managed services and
any paid Render worker must be provisioned explicitly.
