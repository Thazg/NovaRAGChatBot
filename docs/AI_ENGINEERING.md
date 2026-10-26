# AI engineering: changes, experiments and failure contracts

Nova RAG Workspace separates document processing, retrieval, context packing, generation and evaluation. This guide explains how to change that system with evidence. Read [RAG pipeline](RAG_PIPELINE.md) for implementation details and the [evaluation guide](../backend/evaluation/README.md) for commands and recorded results.

## Decisions and their practical consequences

| Decision | Reason | Consequence to test |
| --- | --- | --- |
| BM25 is the default; dense/hybrid is opt-in | The recorded corpus comparison supports the simpler quality/latency trade-off | Do not enable embedding calls in default ingestion/query paths; rerun representative quality and latency experiments before changing the default |
| Upload storage ID differs from display filename | A user can upload two files with the same visible name | Scope by storage ID before display-name fallback; summary requests with ambiguous names must fail rather than combine files |
| One production retrieval/packing path | A second benchmark-only implementation can report quality the product does not deliver | Evaluators call production parsing, chunking, ranking and packing; labels are used only after context selection |
| Follow-up expansion uses bounded user questions | Generated answers can contain mistakes that should not become search evidence | Standalone new topics/overviews stay independent; prior assistant text never enters the retrieval query |
| Embedding identity accompanies snapshots | Equal vector dimensions do not imply the same semantic space | Model/endpoint/prefix changes invalidate dense use and query caches; legacy unknown vectors fall back to BM25 until rebuilt |
| Grounding is explicit but not a factuality certificate | A valid citation ID can still be attached to an unsupported claim | Reject invented IDs, retain interruption semantics, and evaluate claim support separately; do not describe ID validation as entailment |
| Only explicit completion is success | Providers and transports can terminate after producing partial text | Preserve the generated prefix, mark it interrupted, omit `[DONE]`, and let explicit regeneration retry |

## Change a retriever or embedding model

1. State the failure using a synthetic or separately reviewed development fixture. Record the current selected passages, packed evidence and expected behavior. Do not tune using the held-out arXiv answers.
2. Freeze the comparison inputs: dataset hash/review state, chunking, K, document scope, context budgets, model ID and measurement hardware. Compare identical scope; warm retrieval milliseconds cannot be compared with HTTP or generated-answer latency.
3. Run lexical-only and opt-in dense paths independently. Check row order/count/dimensions/finiteness, deletion barriers, same-name document collisions, and model-change behavior before interpreting retrieval scores.
4. Use a revisioned embedding model identifier. Snapshots record the requested ID, hashed endpoint and document/query prefixes, not the provider's weight checksum. Switching a provider's weights behind an unchanged ID is an operator-managed migration.
5. Reindex with the intended model and verify the new snapshot. Missing/mismatched identity intentionally leaves BM25 available. A successful incremental hybrid update re-embeds all old/new rows when rebuilding a previously unusable dense index.
6. Compare relevant-page ranking, post-packing span retention, ingestion/index size, query latency and provider cost. Keep a failed candidate's report and failure cases; do not change the CI floors to make it win.

Use [operations](OPERATIONS.md) and [production persistence](PRODUCTION_PERSISTENCE.md) for drain/backup/migration/restore procedures. An index revision is not an automatic rollback or backup-retention service.

## Evaluate generated answers

From `backend`, after building the documented corpus and configuring the intended provider:

```bash
python -m evaluation.live_answer_eval --limit 10 --k 5 --output evaluation/live_results.json
```

This is an opt-in provider operation. A local Ollama smoke on synthetic text verifies integration; it does not establish benchmark quality. Groq receives the packed text/history/instructions when selected. Review the data/provider and sample limit before a real run.

Version 3 reports include a canonical dataset hash, per-sample prompt hash, effective non-secret configuration, provider/model, packed evidence, generated or partial failed answers, and unknown citation IDs. Failed attempts stay in the quality denominator. Character-derived token/cost estimates are not billing usage. Generation, failed-attempt and first-token timings have different denominators and exclude HTTP/retrieval/packing; none is an application SLO.

| Measurement | Appropriate interpretation | Additional evidence needed |
| --- | --- | --- |
| Page Hit/Recall/MRR | Relevant pages ranked on the specified dataset | Independent data/review and representative user documents |
| Conditional evidence retention | Retrieved annotated spans survive packing | Recall of missing evidence and support for each answer claim |
| Valid evidence IDs and annotated-page citation scores | References point to packed passages with known page labels | Claim-level entailment/correct attribution, including mixed supported/unsupported answers |
| Lexical faithfulness and reference token F1 | Deterministic diagnostic overlap | Human or separately validated semantic evaluation, particularly for paraphrases and multilingual answers |
| Provider failure rate and time to first token | Reliability/latency of the configured generation experiment | HTTP/proxy concurrency, queue delay, cancellation and distributed staging |
| Unanswerable responses | Saved outputs for review | An independently reviewed calibration split and refusal/false-answer evaluation |

The separate `/documents/summarize` helper selects one document and truncates joined text at 20,000 characters. It does not return chat evidence IDs, prove full-document coverage, or participate in the generated-answer benchmark. Treat its output accordingly.

## Acceptance before publishing a change

- Keep a reproducible failure fixture and a test of the corrected behavior. Cover provider failure before a full SSE batch, unknown citation IDs, document scope collisions and a changed embedding model with the same dimensions.
- Run the appropriate [testing commands](TESTING.md). Offline CI must not silently begin calling a paid provider or sending private upload text to an evaluator.
- Update the API/configuration/pipeline/user guide that owns the changed contract. The docs gate catches missing local targets, undocumented settings and route inventory drift; semantic claims still need review.
- Record the actual code/working-tree scope, commands, reports and untested assumptions. Distinguish synthetic provider stubs, local Ollama, recorded benchmark results and real PostgreSQL/Redis/RQ/B2 staging.

## Current quality limits

The held-out regression still exposes 0/10 unanswerable accuracy. There is no validated abstention classifier, OCR pipeline, exact tokenizer-backed input budget, claim-entailment validator or complete prompt-injection defense. Prompt boundaries and citation-ID checks reduce specific failures; they do not establish those capabilities. JSON mode remains single-process, and real distributed storage/recovery must be validated separately. These gaps should guide the next experiment rather than be hidden by adding more model components.
