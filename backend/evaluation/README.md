# Nova Retrieval Evaluation

This directory contains Nova's reproducible offline quality benchmark. It is intentionally small and deterministic so it can run in CI without an external model, embedding API, or network connection.

## Benchmark snapshot

Last recorded: **2026-08-11**<br>
Configuration: **K = 5**, 8 corpus passages, 6 retrieval queries, 3 citation samples

| Metric | Result | Required | Status |
| --- | ---: | ---: | :---: |
| Recall@5 | **1.000** | >= 0.900 | Pass |
| Mean Reciprocal Rank | **0.917** | >= 0.800 | Pass |
| Citation precision | **1.000** | >= 0.900 | Pass |

All configured evaluation thresholds passed. The machine-readable output is committed in [`results.json`](./results.json).

### Per-query retrieval results

| Query | Relevant result rank | Recall@5 | Reciprocal rank |
| --- | ---: | ---: | ---: |
| How are BM25 and FAISS rankings combined? | 1 | 1.0 | 1.0 |
| How does Nova hash user passwords? | 1 | 1.0 | 1.0 |
| How are generated tokens streamed to React? | 2 | 1.0 | 0.5 |
| How does startup verify the Groq model is reachable? | 1 | 1.0 | 1.0 |
| Where are uploaded files persisted in cloud object storage? | 1 | 1.0 | 1.0 |
| Which platforms host the backend and frontend? | 1 | 1.0 | 1.0 |

## Metric definitions

- **Recall@K** measures the fraction of known relevant passages that appear in the first `K` retrieved results. The report averages this value across all queries.
- **Mean Reciprocal Rank (MRR)** rewards putting the first relevant passage near the top. A relevant result at rank 1 scores `1.0`; rank 2 scores `0.5`.
- **Citation precision** is the fraction of citations in the generated answer whose `(Source: filename)` matches an expected source.

## Reproduce the result

Run from the `backend` directory:

```bash
python -m evaluation.run --k 5 --output evaluation/results.json
```

The command prints the complete report, writes the JSON artifact, and exits with a non-zero status if any threshold fails. Custom thresholds are supported:

```bash
python -m evaluation.run \
  --k 5 \
  --min-recall 0.90 \
  --min-mrr 0.80 \
  --min-citation-precision 0.90
```

GitHub Actions runs the same benchmark on every pull request and push to `main`.

## Files

| File | Purpose |
| --- | --- |
| [`dataset.json`](./dataset.json) | Versioned corpus, relevance labels, queries, and citation samples |
| [`metrics.py`](./metrics.py) | Recall@K, reciprocal rank, citation parsing, and report aggregation |
| [`run.py`](./run.py) | CLI, threshold enforcement, and JSON report output |
| [`results.json`](./results.json) | Latest committed benchmark output |
| [`../tests/test_evaluation.py`](../tests/test_evaluation.py) | Unit tests for metric correctness |

## Scope and limitations

This benchmark validates the deterministic lexical retrieval path and citation formatting. The dataset is deliberately compact and project-specific, so the scores are regression indicators rather than claims of general RAG quality. A production-grade follow-up should add a larger human-labeled dataset, semantic retrieval ablations, answer faithfulness, citation recall, and latency/cost measurements.
