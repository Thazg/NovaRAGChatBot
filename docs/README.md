# Documentation

Nova's documentation describes the implemented private-document application, its failure behavior and its operational boundaries. Start with the task you need to perform.

| Task | Read |
| --- | --- |
| Run the application locally | [Project quick start](../README.md#quick-start), [backend guide](../backend/README.md), [frontend guide](../frontend/README.md) |
| Use documents, source locations and chat | [User guide](USER_GUIDE.md) |
| Trace ownership and a request across services | [Architecture](ARCHITECTURE.md) |
| Integrate a client or debug HTTP/SSE | [API reference](API_REFERENCE.md), [interactive OpenAPI](http://127.0.0.1:8000/docs) after starting the API |
| Configure providers, cookies, storage and limits | [Configuration reference](CONFIGURATION.md) |
| Change parsing, retrieval, citations or evaluation | [RAG pipeline](RAG_PIPELINE.md), [evaluation methodology](../backend/evaluation/README.md) |
| Design and evaluate AI/backend changes | [AI engineering guide](AI_ENGINEERING.md) |
| Reproduce the saved retrieval report from a clean checkout | [Reproduction recipe](REPRODUCIBILITY.md) |
| Run checks and understand what they prove | [Testing guide](TESTING.md) |
| Deploy, recover data or diagnose an incident | [Operations](OPERATIONS.md), [persistence/migration runbook](PRODUCTION_PERSISTENCE.md) |
| Understand security boundaries | [Security policy](../SECURITY.md), [session design](SESSION_SECURITY.md), [upload/SSRF design](UPLOAD_SECURITY.md) |
| Contribute a change | [Contribution guide](../CONTRIBUTING.md), [PR template](../.github/pull_request_template.md) |

## Read claims with their verification scope

Source review, tests against adapters/SQLite, and real multi-host staging are different evidence. Offline retrieval metrics do not measure generated-answer accuracy; a green readiness response does not certify an entire deployment. Individual guides state which mode they describe.
