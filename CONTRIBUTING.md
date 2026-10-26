# Contributing

Nova is an application with private account/document data, streamed model output and optional distributed persistence. Changes should preserve those boundaries and be reviewable against actual behavior.

## Set up

Use Python 3.12+ and Node.js 22.12+ (or a compatible newer release). Follow the [quick start](README.md#local-development), install `backend/requirements-dev.txt` for backend tests, and run `npm ci` in `frontend`. Use disposable accounts and synthetic documents. Provider-backed evaluation is optional and may send text to the configured provider.

Read the [architecture](docs/ARCHITECTURE.md), the relevant module README, and the [testing guide](docs/TESTING.md) before changing a contract. Settings are loaded when backend modules are imported; restart the API and workers after changing environment configuration.

## Make a change

1. Describe the user-visible problem with a minimal reproduction. For a feature, state its scope and failure behavior. Do not attach private source documents or authentication tokens to a public issue.
2. Create a focused branch such as `fix/document-job-status` or `docs/storage-recovery`. Keep unrelated formatting, dependency changes and generated benchmark output separate unless they are part of the fix.
3. Preserve tenant isolation, backend-owned source metadata, explicit stream completion, and account/document deletion barriers. Document source locations as filename/page/extracted-line text; do not invent page numbers for text formats.
4. Add a regression for a meaningful behavior change. Use isolated temporary storage and deterministic adapters. Cosmetic or prose-only changes need the relevant lightweight checks, not artificial unit tests.
5. Update user/developer documentation when configuration, API responses, migrations or limitations change. Record measurement scope, hardware/provider context and failures when reporting performance or answer quality.

## Validate and submit

Run the checks relevant to your module and then the cross-module checks described in [testing](docs/TESTING.md). At minimum, validate documentation links for prose changes; validate frontend types/build for client changes; run backend tests for service changes. Never lower quality/coverage thresholds to make a failing implementation pass.

Use the [PR template](.github/pull_request_template.md). Explain the concrete trigger, resulting behavior, tests actually run, rollout/migration needs and remaining limitations. A passing local adapter test must not be presented as a real Redis/PostgreSQL/B2 integration test.

Do not commit `.env`, user uploads, account exports, local storage, credentials, downloaded model caches or Playwright artifacts. The [MIT License](LICENSE) applies to the project code; only contribute code and fixtures you are entitled to share. This does not license arbitrary user-uploaded documents or third-party evaluation PDFs.

Report suspected security issues using the [security policy](SECURITY.md), rather than posting exploit details or private data in a public issue.
