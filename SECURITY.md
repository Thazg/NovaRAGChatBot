# Security policy

Nova processes user-owned documents and sends selected context to a configured language-model provider. Treat access tokens, refresh cookies, document text, filenames, conversation history, account exports and provider credentials as sensitive.

## Reporting a vulnerability

If this repository offers GitHub private vulnerability reporting, use its **Security → Report a vulnerability** flow. Otherwise contact the maintainer through the [maintainer profile](https://github.com/Thazg) to arrange a private reporting channel before sharing exploit details. Do not open a public issue containing credentials, private documents, account exports or another user's data.

Include the affected commit/version and runtime mode, the smallest synthetic reproduction, the expected and observed behavior, the impact, and whether any real user data was accessed. Stop testing once impact is demonstrated. There is no advertised response-time guarantee or paid vulnerability-reward program.

## Supported security scope

Security fixes target the current maintained code and dependencies; older deployed revisions are not independently supported release lines. Running an older demo deployment is not evidence that all current local fixes have been deployed.

CI runs `python -m pip_audit` against the installed Python environment and `npm audit --audit-level=high` for the full frontend dependency graph, including build tools. See [testing](docs/TESTING.md) for setup. Dependency upgrades that affect parsing must rebuild the checksum-pinned PDF corpus and rerun retrieval gates; do not weaken quality floors to absorb parser changes. A clean advisory report is time-specific and does not establish parser isolation or a penetration test.

Current controls include account-scoped routes/storage, hashed passwords, short-lived in-memory access tokens, rotating hashed refresh sessions, origin checks for cookie-backed endpoints, upload validation, bounded parsing, SSRF defenses and deletion barriers. The [session](docs/SESSION_SECURITY.md), [upload](docs/UPLOAD_SECURITY.md) and [persistence](docs/PRODUCTION_PERSISTENCE.md) documents describe their boundaries.

## Optional evaluation dependencies

The separate optional-evaluation workflow installs and audits `backend/requirements-evaluation.txt` on CPU, on relevant changes and weekly. It exercises embeddings and cross-encoder scoring with tiny local models without model downloads. This checks the optional neural experiment's dependencies; it is not a new quality benchmark. Evaluation model revisions are pinned and remote model code is explicitly disabled. Historical experiment artifacts retain their original package versions and are evidence records, not recommendations to reinstall vulnerable releases.

## Frontend build dependency policy

The npm lockfile is audited with development dependencies included. `postcss-selector-parser` is overridden to the patched 7.1 line (minimum 7.1.6) for Tailwind 3 and its typography/nesting tools because their older dependency ranges otherwise retain the vulnerable parser. This changes the build dependency, not the Tailwind major or runtime styling API. Lint/type/build and the browser suite, including unchanged visual baselines, must pass before accepting an override update. Review or remove the override when upstream ranges support a patched parser. Vite's minimum supported dependency range is also raised to a patched release.

## Deployment responsibilities and limits

- Run with a unique production JWT secret and secure cookies behind HTTPS. Example secrets and insecure production cookie configuration are rejected at startup. Rotate real credentials if they are exposed; changing a README example is not credential rotation.
- Local JSON state and process locks support a single API process. Use the documented shared infrastructure and verify it in staging before claiming multiple-host support. User preferences currently remain local/B2 rather than PostgreSQL-backed.
- Enable and verify required malware scanning before accepting untrusted public uploads. File validation is not a substitute for malware scanning or isolation of complex parsers.
- Review provider data policies and configure secrets outside the browser. BM25 ingestion does not need an embedding service; chat still sends the selected evidence/history to the configured chat provider. Hybrid mode also transmits text to the embedding endpoint.
- Uploaded text is untrusted model input. Evidence labels and prompt instructions help trace output; they do not prove factual correctness or eliminate prompt injection. Never use generated text as authorization or executable instructions.
- Logout/password change revokes refresh sessions according to the session contract; already-issued access tokens remain usable until expiry. Successful account deletion makes the account record unavailable, invalidating subsequent authenticated access.
- Cleanup failures keep the account record so the owner can retry; write barriers prevent late jobs/streams from restoring active data. Minimal UUID deletion barriers, revoked-session metadata and independent backup retention are distinct from active user content. Immutable snapshot retention and backup destruction need explicit operating procedures.

See [operations](docs/OPERATIONS.md) for incident response and recovery. No claim of third-party penetration testing, compliance certification or verified distributed staging is made by this policy.
