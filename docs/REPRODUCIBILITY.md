# Reproduce Nova's retrieval results

This recipe rebuilds the corpus and runs the offline gates from a clean checkout. It measures retrieval and packing, not generated-answer accuracy. The [README](../README.md#measured-results) summarizes the saved comparison; [evaluation methodology](../backend/evaluation/README.md) owns metric definitions and historical experiments.

## Inputs and environment

- Use Python 3.12 and Node.js 22.12+. Install from `backend/requirements-dev.txt` and `frontend/package-lock.json`; the latter supports `npm ci`.
- Start from a fresh clone of the revision being evaluated. Do not copy `.env`, user uploads/storage, generated indexes, virtual environments or `node_modules` from another checkout.
- Offline gates do not need Groq, Ollama or an embedding provider. Initial package/PDF/browser downloads require network access.
- The corpus manifest pins 10 arXiv paper versions; `checksums.json` pins the PDF bytes. Read [third-party notices](../THIRD_PARTY_NOTICES.md) before redistributing papers, excerpts or derived artifacts.

The saved report was produced on 2026-10-26 with Python 3.12.15/Linux, pypdf 6.21.2 and fonttools 4.67.0. K=5, chunk size=220 words, overlap=40 words, passage budget=2,400 characters and total context budget=10,000 characters. The report's corpus SHA-256 is `0cf02375395db104d9bf256cbe019d0935887ead198b3a2e6463b60c87fb6201`.

Current requirements pin pypdf 6.21.4 for security fixes. The saved report retains its original parser version and results; it has not been relabeled as a measurement of the patched parser. Rebuild with the current requirements and compare the reported parser versions, corpus fingerprint and quality gates before claiming exact reproduction.

Python dependencies are not a complete transitive hash lock. Record resolved versions with `python -m pip freeze`; compare the corpus hash and parser versions before interpreting differences. Browser snapshots depend on OS fonts as well as Chromium. CI uses `mcr.microsoft.com/playwright:v1.62.1-noble`, matched to the lockfile's Playwright version.

## Backend setup

From the repository root, using Bash:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements-dev.txt
python -m pip check
python -m pip_audit
```

On PowerShell, activate with `.\.venv\Scripts\Activate.ps1`. Do not create an application `.env` for these offline checks; tests supply isolated settings and synthetic provider/storage responses. To run the application instead, follow [quick start](../README.md#quick-start).

## Rebuild the corpus and evaluate

```bash
cd backend
python evaluation/arxiv_corpus/download_papers.py
python evaluation/arxiv_corpus/extract_corpus.py
python evaluation/arxiv_corpus/build_dataset.py
python -m evaluation.run --k 5 --output evaluation/reproduced_results.json
cd ..
```

The downloader fails on changed PDF bytes. Do not use `--update-lock` to hide an upstream change or reduce the quality floors to make a run pass. Corpus/dataset generation uses production parsing/chunking. Reference labels are consulted for scoring, not to select runtime passages.

`reproduced_results.json` is a local experiment output: do not commit it automatically. The existing [results.json](../backend/evaluation/results.json) remains the dated source artifact until a new report is deliberately reviewed.

| Check against the saved report | Expected value or interpretation |
| --- | --- |
| Corpus | 10 PDFs, 160 pages, 555 chunks; compare SHA-256 and parser lineage |
| Questions | 100 total: 90 answerable, 10 unanswerable; independent human review pending |
| Production page Hit/Recall@5 | 75/90 (0.833333...) |
| Production MRR@5 | 0.554074... across 90 answerable questions |
| Conditional packing retention | 57/57 retrieved annotated spans retained; not 90/90 evidence recall |
| Correct unanswerable retrieval abstentions | 0/10; known limitation |
| Latency | Warm retrieval only, 100 queries. Saved P50/P95=5.80/10.19 ms; do not require exact timings on different hardware/load |

Span matching ignores case and whitespace and preserves other characters; it can conflate word boundaries. Static citation-label and lexical-support scores do not establish generated-answer correctness. FAISS/TF-IDF proxy rows are not neural embedding benchmarks.

## Backend and documentation gates

From the repository root:

```bash
python -m pytest --cov --cov-report=term-missing --cov-fail-under=64
python -m unittest discover -s scripts -p "test_*.py"
python scripts/check_docs.py
```

The full suite requires the generated corpus. Its adapters, subprocess/race tests and provider doubles do not certify real PostgreSQL/Redis/RQ/B2 staging. The docs checker covers local targets, setting names and registered API method/path inventory; link fragments, numeric claims and prose still require review.

## Frontend gates

```bash
cd frontend
npm ci
npm audit --audit-level=high
npm run check
npm run test
npx playwright install chromium
npm run e2e
```

Native Linux setup can need `npx playwright install --with-deps chromium`. For baseline-equivalent Linux rendering, run in the pinned Playwright image rather than changing image thresholds when host fonts differ. CI's full recipe lives in [the workflow](../.github/workflows/ci.yml). E2E uses controlled API fixtures; the screenshot in the README has its own [capture context](assets/README.md).

## Provider experiments are separate

The [live evaluator](../backend/evaluation/README.md#opt-in-generated-answer-evaluation) invokes the configured model and can transfer passages or incur cost. Run it only after reviewing data/provider/budget. Save dataset/prompt fingerprints, provider/model, effective settings, failures, partial output and timing denominators. Report model generation separately from retrieval, HTTP and production performance. A local smoke is not a human-reviewed factuality benchmark.
