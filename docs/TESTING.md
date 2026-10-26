# Testing and verification

Run commands from the repository root unless a different working directory is shown. Use isolated/synthetic accounts and documents. Never point failure-injection tests at a real upload bucket or production database.

## Install the test toolchain

Use the project's Python 3.12+ and Node.js 22.12+ toolchains. With your Python virtual environment active:

```bash
python -m pip install --upgrade pip
python -m pip install -r backend/requirements-dev.txt
cd frontend
npm ci
npx playwright install chromium
```

Frontend CI runs inside the pinned `mcr.microsoft.com/playwright:v1.62.1-noble` image, which supplies Chromium and system fonts for the reviewed Linux snapshots. Its version must match the locked `@playwright/test` package when upgrading. This avoids the host runner's OS/font migration changing platform-font layout. Native Linux development can use `npx playwright install --with-deps chromium` to install browser/system dependencies, but that environment is not necessarily the snapshot baseline. These dependencies are separate from application runtime installation.

## Backend and the reproducible corpus

Most focused backend tests use synthetic inputs and do not call a provider. The full suite also verifies the reviewed 100-query dataset, so a clean checkout must first build its ignored generated files from checksum-pinned PDFs:

```bash
cd backend
python evaluation/arxiv_corpus/download_papers.py
python evaluation/arxiv_corpus/extract_corpus.py
python evaluation/arxiv_corpus/build_dataset.py
```

The downloader needs network access when the pinned PDFs are not cached. Extraction, dataset construction and baseline evaluation then run offline; they do not download models or call Groq/Ollama.

From the repository root:

```bash
python -m pip check
python -m pip_audit
python -m pytest -q --tb=short
python -m pytest --cov --cov-report=term-missing --cov-fail-under=64
python scripts/check_docs.py
```

Focused examples while working on a module:

```bash
python -m pytest -q backend/tests/test_auth.py backend/tests/test_token_validation.py backend/tests/test_account_lifecycle.py
python -m pytest -q backend/tests/test_chat_contracts.py backend/tests/test_chat_evidence.py
python -m pytest -q backend/tests/test_index_revisions.py backend/tests/test_index_account_races.py
python -m pytest -q backend/tests/test_postgres_store.py backend/tests/test_index_jobs.py
```

Some Windows environments restrict child processes or pytest temporary directories. Run through a permitted development environment instead of changing production code/tests to hide the restriction. Do not label an environment-blocked check as passed.

## Frontend

From `frontend`:

```bash
npm audit --audit-level=high
npm run test
npm run check
npm run e2e
```

Unit tests cover deterministic parsing/formatting/origin policy. `check` includes lint, TypeScript and a production build. Chromium E2E exercises real browser behavior against deterministic API mocks, including authorization/session recovery, upload/job state, streaming/cancellation/regeneration, source reload/copy/share/export, account errors, responsive layout and accessibility. Native sharing/clipboard effects are intercepted in the relevant tests; no answer is sent to an external sharing service.

The login screenshot is a small visual regression guard, not a complete design audit. Snapshot differences should be inspected; do not blindly accept new baselines to make CI green.

## Retrieval and answer evaluation

From `backend`, after corpus generation:

```bash
python -m evaluation.run --k 5
```

The gate uses production parsing/chunking/retrieval/packing. Existing quality floors and the 64% production-code coverage floor must not be lowered as a substitute for fixing regressions. The reviewed evidence spans are used to score results; runtime passage selection must never read answer annotations.

Keep these measurements distinct:

| Measurement | What it proves | What it does not prove |
| --- | --- | --- |
| Page Hit/Recall/MRR | Relevant page ranking on this dataset | Correct generated answer or calibrated abstention |
| Post-packing span retention | Retrieved annotated text survives context budgets | Every question has evidence or every citation supports its claim |
| Citation-label/lexical proxies | Deterministic checks on specified reference samples | Human/NLI factual verification of arbitrary answers |
| Provider-backed answer evaluation | Production-path responses/failures for the selected provider/model | A guarantee across models, languages or future provider versions |
| SQLite/storage adapters | Application transactions/protocol behavior under isolated failures | Real PostgreSQL locking, Redis lease behavior or B2 consistency under network faults |

Provider-backed evaluation is an explicit opt-in operation: review dataset sensitivity, requested model and cost budget first. The [evaluation guide](../backend/evaluation/README.md) describes report fields and limits. Do not calibrate abstention on the held-out 100-query set.

## Continuous integration and change acceptance

The [workflow](../.github/workflows/ci.yml) audits installed Python dependencies, builds the corpus, runs backend coverage/evaluation, checks documentation, audits frontend runtime and build dependencies, builds/tests the client and runs Chromium. The Python audit includes test tools and the installer; upgrade pip before installing the development requirements. An audit checks published advisories at execution time, not arbitrary application vulnerabilities. Read the failed step before changing code: an audit failure, missing fixture, protocol regression and unavailable package registry require different remedies.

The documentation job first runs `python -m unittest discover -s scripts -p "test_*.py"`, then `python scripts/check_docs.py`. The checker uses only the standard library and AST parsing; it never imports application settings or secrets. It checks local file targets, coverage of `Settings` field names, and the method/path inventory in `docs/API_REFERENCE.md` against the app's literal router registrations/decorators. New undocumented routes and documented removed routes fail, while parameter-name and trailing-slash aliases are normalized. Fixtures prove those failures. This does not verify external URLs, Markdown anchors, numeric defaults, deployment state or the truth of arbitrary prose; those require source review and runtime evidence.

For a change, record the commands/results actually run, the commit/working-tree scope, failure-path coverage and any untested infrastructure. Source inspection and mocks are useful evidence, but do not claim a staging exercise that has not happened. See [operations](OPERATIONS.md) for the separate distributed acceptance workflow.
