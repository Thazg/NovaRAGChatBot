# Nova retrieval evaluation

Nova is evaluated against questions derived from version-pinned arXiv PDFs.
The repository versions the source manifest, SHA-256 lock, 100 annotations,
evidence spans, review state, aggregate metrics, and per-query results.

## Deterministic CI baseline

Last recorded: **2026-08-19**

Configuration: **K = 5**, 10 PDFs, 160 pages, 549 chunks, and 100 questions
(90 answerable + 10 unanswerable).

| Measurement | Result | Regression floor | Status |
| --- | ---: | ---: | :---: |
| Hybrid Hit@5 | **0.7889** | >= 0.78 | Pass |
| Hybrid Recall@5 | **0.7889** | >= 0.78 | Pass |
| Hybrid MRR | **0.5813** | >= 0.55 | Pass |
| Citation-label precision | **1.0000** | >= 0.90 | Pass |
| Citation-label recall | **1.0000** | >= 0.90 | Pass |
| Lexical evidence-support proxy | **0.8346** | >= 0.80 | Pass |
| Unanswerable accuracy | **0.0000** | improvement target | **Known gap** |

The current offline retriever has no calibrated confidence threshold and always
returns a ranking, so it fails all 10 unanswerable questions. The CI floor
remains zero until abstention is implemented and calibrated on a separate
development split. Unanswerable accuracy is therefore reported as an open
limitation rather than a passing quality gate.

The complete machine-readable report is in
[`results.json`](./results.json), including every ranked query and per-paper
breakdowns.

## Production retrieval comparison

A separate CPU benchmark compares BM25, real BGE neural dense retrieval, equal
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

### Deterministic proxy ablation

| Retrieval mode | Hit@5 | Recall@5 | MRR | P50 | P95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 | **0.8000** | **0.8000** | 0.5710 | 216.24 ms | 228.71 ms |
| TF-IDF + FAISS proxy | 0.7556 | 0.7444 | 0.5688 | 221.45 ms | 239.13 ms |
| Hybrid RRF | 0.7889 | 0.7889 | **0.5813** | 439.32 ms | 466.50 ms |

Latency is a local Python micro-benchmark and varies by machine. The offline
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

Each answerable annotation includes a reference answer and a verbatim evidence
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

From `backend`:

```bash
python evaluation/arxiv_corpus/download_papers.py
python evaluation/arxiv_corpus/extract_corpus.py
python evaluation/arxiv_corpus/build_dataset.py
python -m evaluation.run --k 5 --output evaluation/results.json
```

The downloader verifies every PDF against the committed SHA-256 and page-count
lock. The extractor uses `pypdf`, retains PDF page metadata, and calls Nova's
production chunker with 220-word chunks and a 40-word overlap. PDFs, extracted
text, and the generated dataset are ignored build artifacts; this avoids
redistributing full paper text while keeping the benchmark reproducible.

CI executes the same pipeline before tests. Current regression floors can be
overridden with `--min-hit`, `--min-recall`, `--min-mrr`,
`--min-citation-precision`, `--min-citation-recall`, `--min-faithfulness`, and
`--min-unanswerable-accuracy`.

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
`live_answer_eval.py`; they require configured external providers.

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
