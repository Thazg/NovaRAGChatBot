# Nova RAG Evaluation

This directory keeps both reproducible CI results and opt-in provider-backed
evaluations. Results are committed as documentation artifacts so the metrics in
the portfolio can be audited instead of relying on screenshots or claims.

## Recorded offline result

Last recorded: **2026-08-12**<br>
Configuration: **K = 5**, 14 corpus passages, 60 labeled queries (56
answerable, 4 unanswerable), and 14 citation samples.

| Quality gate | Result | Required | Status |
| --- | ---: | ---: | :---: |
| Hybrid Recall@5 | **0.9821** | >= 0.90 | Pass |
| Hybrid MRR | **0.9554** | >= 0.80 | Pass |
| Citation precision | **1.0000** | >= 0.90 | Pass |
| Citation recall | **1.0000** | >= 0.90 | Pass |
| Lexical evidence support proxy | **0.6692** | >= 0.60 | Pass |
| Unanswerable accuracy | **1.0000** | >= 1.00 | Pass |

The complete machine-readable report, including every ranked query result, is
stored in [`results.json`](./results.json).

### Retrieval ablation

| Retrieval mode | Recall@5 | MRR | No-answer accuracy | P50 latency | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 | 0.9821 | 0.9554 | 1.0000 | 0.682 ms | 0.798 ms |
| TF-IDF + FAISS proxy | 0.9464 | 0.9196 | 1.0000 | 1.077 ms | 1.166 ms |
| Hybrid RRF | **0.9821** | **0.9554** | 1.0000 | 1.770 ms | 1.951 ms |

Latency is a local micro-benchmark and varies by machine. Hybrid latency is
measured end-to-end (BM25 + proxy dense search + fusion), not fusion alone.

The offline FAISS mode uses normalized TF-IDF vectors. It exercises vector
indexing and fusion deterministically, but it is **not** presented as semantic
dense retrieval. A separate provider-backed command below measures the real
configured embedding model.

## Reproduce the CI benchmark

From `backend`:

```bash
python -m evaluation.run --k 5 --output evaluation/results.json
```

The command updates the JSON report and exits non-zero when a quality gate
regresses. CI runs the same command on pushes and pull requests.

Custom thresholds are available:

```bash
python -m evaluation.run \
  --k 5 \
  --min-recall 0.90 \
  --min-mrr 0.80 \
  --min-citation-precision 0.90 \
  --min-citation-recall 0.90 \
  --min-faithfulness 0.60 \
  --min-unanswerable-accuracy 1.00
```

## Real embedding ablation (opt-in)

Set `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, and `EMBEDDING_MODEL`, then run:

```bash
python -m evaluation.live_retrieval_eval \
  --k 5 \
  --min-dense-score 0.25 \
  --output evaluation/embedding_results.json
```

This batches the labeled corpus and queries through the configured embedding
provider, builds a real FAISS index, and records BM25 vs dense vs hybrid
retrieval, latency, and no-answer accuracy. **No `embedding_results.json` is
committed yet because this environment has no embedding endpoint configured.**
The CLI exits with code 2 instead of silently substituting fake embeddings.

## Real LLM answer evaluation (opt-in)

The LLM evaluator records generated answers, citations, lexical evidence
support, reference token F1, latency, estimated tokens, and estimated cost:

```bash
python -m evaluation.live_answer_eval \
  --output evaluation/live_results.json \
  --input-cost-per-million 0.075 \
  --output-cost-per-million 0.30
```

Pricing arguments must be copied from the provider on the day of the run; they
are intentionally not hardcoded. Token usage is estimated as
`ceil(character_count / 4)` because the current streaming adapter does not
return provider usage metadata.

**No `live_results.json` is committed yet.** Running this command sends the 14
versioned evaluation passages and questions to the configured LLM provider, so
it requires explicit approval for that data transfer.

## Metric definitions

- **Recall@K** is the fraction of labeled relevant passages found in the first
  K results, averaged over answerable questions.
- **MRR** rewards the rank of the first relevant result.
- **Citation precision** penalizes cited filenames outside the labeled sources.
- **Citation recall** measures how many labeled sources were cited.
- **Lexical evidence support** is token overlap between answer claims and the
  supplied evidence. It is a deterministic regression proxy, not an NLI judge
  or human faithfulness score.
- **Unanswerable accuracy** requires retrieval to abstain on questions with no
  labeled answer. Corpus-common terms and question boilerplate are removed
  before a deterministic lexical-evidence gate. All four versioned adversarial
  no-answer questions currently abstain correctly.
- **Reference token F1** is available only in the live answer evaluation and
  measures overlap with the human-authored reference answer.

## Files

| File | Purpose |
| --- | --- |
| [`dataset.json`](./dataset.json) | Versioned corpus, 60 relevance labels, and 14 answer samples |
| [`metrics.py`](./metrics.py) | Offline metrics and deterministic ablation |
| [`run.py`](./run.py) | CI CLI and threshold enforcement |
| [`results.json`](./results.json) | Latest committed offline result |
| [`live_retrieval_eval.py`](./live_retrieval_eval.py) | Real embedding/FAISS ablation |
| [`live_answer_eval.py`](./live_answer_eval.py) | Real LLM grounding, latency, token, and cost evaluation |
| [`../tests/test_evaluation.py`](../tests/test_evaluation.py) | Metric and evaluator tests |

## Interpretation limits

The benchmark is project-specific and suitable for regression testing, not a
claim of general RAG quality. It has reached the requested 50–100 labeled-query
range, but further work should add independent human labeling, more difficult
paraphrases, adversarial no-answer questions, exact provider token accounting,
and an NLI or human faithfulness review.
