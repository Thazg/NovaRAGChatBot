# Nova retrieval evaluation

Nova is evaluated against questions derived from version-pinned arXiv PDFs.
The repository versions the source manifest, SHA-256 lock, 100 annotations,
evidence spans, review state, aggregate metrics, and per-query results.

## Deterministic CI baseline

Recorded production-path baseline: **2026-10-26**, rebuilt with pypdf 6.21.2 and its font-decoding extra under Linux/Python 3.12.15. The parser upgrade changes extraction and chunk boundaries; the previous 2026-10-25 report used 549 chunks. Case-invariant acronym expansion also removes duplicate capitalized query terms. Annotations and quality floors are unchanged. Treat this as a new pipeline baseline, not a controlled attribution of gains to one change.

Configuration: **K = 5**, 10 PDFs, 160 pages, 555 chunks, and 100 questions
(90 answerable + 10 unanswerable).

| Measurement | Result | Regression floor | Status |
| --- | ---: | ---: | :---: |
| Production BM25 Hit@5 | **0.8333** | >= 0.78 | Pass |
| Production BM25 Recall@5 | **0.8333** | >= 0.78 | Pass |
| Production BM25 MRR@5 | **0.5541** | >= 0.55 | Pass |
| Context evidence retention | **57/57 (1.0000)** | >= 1.00 | Pass |
| Citation-label precision | **1.0000** | >= 0.90 | Pass |
| Citation-label recall | **1.0000** | >= 0.90 | Pass |
| Lexical evidence-support proxy | **0.8390** | >= 0.80 | Pass |
| Unanswerable accuracy | **0.0000** | improvement target | **Known gap** |

The primary gate uses `rag.rag_chain.retrieve_from_store`, the same query entry point as runtime `retrieve_context`. Corpus construction calls production `rag.load.load_pdf` and `rag.chunking.split_documents` directly. The runtime parser preserves PDF page and extracted-line metadata and uses the same 220-word / 40-word chunk window. PDF evidence is diversified by page before selecting K passages.

The context gate calls production `build_context_and_evidence(nodes, query)`. Of the 90 answerable questions, 57 have their annotated character span in the retrieved chunks; all 57 survive packing with the default 2,400-character passage / 10,000-character total budgets. Matching ignores case and all whitespace because parser versions can join words or insert spaces around symbols. Every other character, including punctuation and negation, must match. This can conflate word boundaries and is not semantic support verification. The same helper resolves annotations during dataset construction and scores post-packing retention. Labels never select runtime excerpts. Retention is conditional on retrieval, **not answer accuracy**, and does not count the other 33 questions as correct. Custom smaller budgets must pass the same gate (`--min-context-retention`, default 1.0).

Recorded production-path latency: **5.80 ms P50 / 10.19 ms P95**, with a warm store and no query cache, in the local Linux/Python 3.12 container. Report version 2 excludes context packing and annotation matching as well as HTTP, B2 revision synchronization, history rewriting and LLM generation. Context packing is reported separately: **0.138 ms P50 / 0.265 ms P95** on annotated queries. These are local diagnostics, not a deployment SLO. Proxy ablations reuse corpus tokenization performed once during setup, outside warm query latency. `results.json` records parser versions, corpus SHA-256, pipeline names and primary method. The historical neural comparison below uses a different parser/ranking scope and is not a like-for-like comparison with this baseline.

The current offline retriever has no calibrated confidence threshold and always
returns a ranking, so it fails all 10 unanswerable questions. The CI floor
remains zero until abstention is implemented and calibrated on a separate
development split. Unanswerable accuracy is therefore reported as an open
limitation rather than a passing quality gate.

The complete machine-readable report is in
[`results.json`](./results.json), including every ranked query and per-paper
breakdowns.

## Production retrieval comparison

The historical candidate benchmark (not rerun on 2026-10-25) compares BM25, real BGE neural dense retrieval, equal
and weighted RRF, MS MARCO cross-encoder reranking, and deterministic multi-query
retrieval. It measures end-to-end warm query latency for each method.

| Method | Hit@5 | MRR | P50 | P95 | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| **BM25** | **0.8222** | 0.5722 | **2.36 ms** | **3.93 ms** | **Production default** |
| BGE dense | 0.5667 | 0.3413 | 21.15 ms | 26.07 ms | Not selected as a standalone method |
| Equal RRF | 0.7556 | 0.5119 | 23.61 ms | 29.17 ms | Not selected for this corpus |
| Weighted RRF | 0.7889 | 0.5384 | 23.62 ms | 29.19 ms | Outperforms equal RRF; not selected |
| Reranked | **0.8444** | **0.5774** | 1,312.34 ms | 1,524.19 ms | Conditional quality tier |
| Multi-query | 0.7889 | 0.5508 | 49.27 ms | 82.29 ms | Not selected for the default path |

The quality gain from reranking is too small for its roughly 555-times P50
latency cost over BM25. Full configurations, indexing cost, limitations, and
the production decision are documented in
[`RETRIEVAL_METHODS.md`](./RETRIEVAL_METHODS.md); raw per-query results are in
[`advanced_results.json`](./advanced_results.json). The runtime default is
therefore `RETRIEVAL_MODE=bm25`; neural hybrid retrieval requires explicit
configuration.

### Deterministic proxy ablation (historical timing)

| Retrieval mode | Hit@5 | Recall@5 | MRR | P50 | P95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 | **0.8000** | **0.8000** | 0.5710 | 216.24 ms | 228.71 ms |
| TF-IDF + FAISS proxy | 0.7556 | 0.7444 | 0.5688 | 221.45 ms | 239.13 ms |
| Hybrid RRF | 0.7889 | 0.7889 | **0.5813** | 439.32 ms | 466.50 ms |

The proxy table retains the historical comparison timing; the current run is in `results.json`. Latency is a local Python micro-benchmark and varies by machine. The offline
FAISS mode uses normalized TF-IDF vectors to exercise vector indexing and
fusion deterministically; it is not described as neural semantic retrieval.

## Dataset provenance

Exactly 10 questions were authored from each paper: 9 answerable and 1
unanswerable.

| Paper | Pinned arXiv version |
| --- | --- |
| Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks | [2005.11401v4](https://arxiv.org/abs/2005.11401v4) |
| Dense Passage Retrieval for Open-Domain Question Answering | [2004.04906v3](https://arxiv.org/abs/2004.04906v3) |
| REALM: Retrieval-Augmented Language Model Pre-Training | [2002.08909v1](https://arxiv.org/abs/2002.08909v1) |
| ColBERT | [2004.12832v2](https://arxiv.org/abs/2004.12832v2) |
| Precise Zero-Shot Dense Retrieval without Relevance Labels (HyDE) | [2212.10496v1](https://arxiv.org/abs/2212.10496v1) |
| Ragas | [2309.15217v2](https://arxiv.org/abs/2309.15217v2) |
| Self-RAG | [2310.11511v1](https://arxiv.org/abs/2310.11511v1) |
| Lost in the Middle | [2307.03172v3](https://arxiv.org/abs/2307.03172v3) |
| Corrective Retrieval Augmented Generation | [2401.15884v3](https://arxiv.org/abs/2401.15884v3) |
| RAPTOR | [2401.18059v1](https://arxiv.org/abs/2401.18059v1) |

Each answerable annotation includes a reference answer and an evidence
span. The builder searches only within the designated paper and resolves the
span to a PDF page. Page-level relevance labels avoid treating overlapping
chunks containing the same sentence as different answers. The build fails for
missing evidence, duplicated IDs, unknown papers, or any count other than 100.

The labels have completed one verification pass. The committed metadata says
`single_reviewer_verified`; independent second-reviewer status is explicitly
`pending_human_reviewer`. See
[`ANNOTATION_GUIDE.md`](./arxiv_corpus/ANNOTATION_GUIDE.md) for acceptance and
adjudication rules.

## Benchmark reproduction

The optional neural experiment uses [requirements-evaluation.txt](../requirements-evaluation.txt): Sentence Transformers 5.7.0, Transformers 5.10.1 and PyTorch 2.13.0. These replace vulnerable experiment dependencies; `advanced_results.json` retains the original environment and has not been relabeled or regenerated. The [optional dependency workflow](../../.github/workflows/evaluation-dependencies.yml) audits the installed CPU stack and checks embedding/reranker APIs with tiny local models. A full quality rerun with the pinned research models is a separate experiment. Model loading explicitly disables remote code.

For a complete clean-source recipe, use [reproduction](../../docs/REPRODUCIBILITY.md). Paper/excerpt permissions are separate from the project code license; see [third-party notices](../../THIRD_PARTY_NOTICES.md).

From `backend`:

```bash
python evaluation/arxiv_corpus/download_papers.py
python evaluation/arxiv_corpus/extract_corpus.py
python evaluation/arxiv_corpus/build_dataset.py
python -m evaluation.run --k 5 --output evaluation/results.json
```

The downloader verifies every PDF against the committed SHA-256 and page-count
lock. The extractor calls the same `load_pdf` and `split_documents` functions as uploads, retaining PDF page metadata and using 220-word chunks with a 40-word overlap. PDFs, extracted
text, and the generated dataset are ignored build artifacts; this avoids
redistributing full paper text while keeping the benchmark reproducible.

CI executes the same pipeline before tests. Current regression floors can be
overridden with `--min-hit`, `--min-recall`, `--min-mrr`,
`--min-citation-precision`, `--min-citation-recall`, `--min-faithfulness`, and
`--min-unanswerable-accuracy`, and `--min-context-retention`. Runtime/evaluation K is constrained to 1–15.

## Metric definitions and limitations

- **Hit@K** is the fraction of answerable questions with at least one labeled
  evidence page in the first K unique pages.
- **Recall@K** measures how many labeled evidence pages are retrieved. Evidence
  usually resolves to one page, so it can equal Hit@K in this dataset.
- **MRR** rewards the rank of the first relevant page.
- **Citation-label precision/recall** check deterministic reference-answer
  citations against page labels. They validate annotation and citation plumbing,
  not live LLM citation quality.
- **Lexical evidence support** is token overlap between reference answers and
  their evidence. It is a deterministic proxy, not an NLI judge or human
  faithfulness score.
- **Unanswerable accuracy** requires the retriever to return no result for
  intentionally absent claims.

This is a small, domain-focused regression benchmark—not a claim of general RAG
quality. It currently lacks independent dual annotation, a held-out calibration
split, provider-backed semantic embeddings, and human evaluation of generated
answers. Opt-in live evaluators remain available in `live_retrieval_eval.py` and
`live_answer_eval.py`; they require configured model/embedding providers.

## Opt-in generated-answer evaluation

Run from `backend` after building the corpus and configuring the intended model provider:

```bash
python -m evaluation.live_answer_eval --limit 10 --k 5 --output evaluation/live_results.json
```

This command sends retrieved document text to the configured LLM and may incur cost. With Ollama it targets the configured local service; with Groq it sends text to that provider. The offline CI command above does not call either provider. `--input-cost-per-million` and `--output-cost-per-million` accept operator-supplied USD rates; token/cost figures are character-based estimates, not billing records. Partial generated text is retained on failed streams but provider billing usage is unavailable.

Report version 3 builds on version 2's production BM25 `retrieve_from_store`, `build_context_and_evidence` and `build_prompt` functions. Ground-truth relevant IDs and references are consulted **after** selecting context, for scoring only. Version 3 adds a canonical dataset SHA-256, per-query prompt SHA-256, a non-secret effective configuration snapshot, retained failed partial answers, and first-token/attempt latency diagnostics. This remains a stateless query experiment: it does not include HTTP, conversation rewriting or index synchronization. Reports predating the production-path evaluator used oracle evidence and are not directly comparable.

The evaluator processes queries, including unanswerable questions, rather than only citation examples. It records retrieved page IDs, packed evidence, generated answers, unknown `[E#]` IDs, provider failures and reference token F1. Citation precision/recall check the cited packed passages against annotated relevant pages; they do not establish whether each factual claim is entailed. Faithfulness remains a lexical proxy. Unanswerable outputs are retained for human review and are not assigned a fabricated automatic answer-accuracy score.

A provider `LLMStreamError` becomes a failed sample and later queries continue. Partial failed answers remain diagnostic records, never successful samples; failed labeled attempts contribute zero to quality averages. The command exits unsuccessfully when any generation fails. `latency_ms_p50/p95` covers successful provider generations, while `attempt_latency_ms_p50/p95` includes failures. `first_token_ms_p50/p95` includes all attempts that emitted a non-empty token, including later failures, and is null if no token was observed. These timings exclude retrieval, packing, HTTP and index synchronization; they are not application time-to-first-byte or an availability SLO.

Tests exercise this path with a mocked provider. **No real-provider answer evaluation was run during the 2026-10-25 module audit.** Claims about generated-answer quality require an actual opt-in run and review of its saved responses. See [RAG pipeline](../../docs/RAG_PIPELINE.md) for implementation contracts and the separate held-out-calibration requirement.

## Artifact inventory

| File | Purpose |
| --- | --- |
| [`dataset.json`](./dataset.json) | Lightweight dataset registry and build instructions |
| [`manifest.json`](./arxiv_corpus/manifest.json) | Paper titles, arXiv versions, and source URLs |
| [`checksums.json`](./arxiv_corpus/checksums.json) | SHA-256, bytes, and page-count lock |
| [`annotation_specs.json`](./arxiv_corpus/annotation_specs.json) | 100 questions, answers, evidence, and review states |
| [`build_dataset.py`](./arxiv_corpus/build_dataset.py) | Evidence resolver and dataset validator |
| [`metrics.py`](./metrics.py) | Offline metrics and retrieval ablation |
| [`results.json`](./results.json) | Latest aggregate and per-query result |
| [`advanced_results.json`](./advanced_results.json) | Six-method quality and latency benchmark |
| [`RETRIEVAL_METHODS.md`](./RETRIEVAL_METHODS.md) | Per-method analysis and production selection |
