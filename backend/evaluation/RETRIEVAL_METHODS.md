# Retrieval strategy evaluation

This report compares six retrieval strategies on Nova's 100-question arXiv
PDF benchmark. It records retrieval quality and warm, steady-state online
latency for every method instead of comparing quality in isolation.

## Production selection

**Select BM25 as Nova's default production retriever for this workload.** It
delivers the best quality/latency trade-off: 82.22% Hit@5 at 2.36 ms P50. The
cross-encoder reranker reaches the highest Hit@5 (84.44%), but the 2.22-point
gain costs approximately 555 times more P50 latency and adds only 0.52 MRR
points. That trade-off does not justify making it the default request path.
The application now enforces this decision with `RETRIEVAL_MODE=bm25`; hybrid
embedding generation and FAISS query search require an explicit `hybrid`
opt-in.

| Method | Hit@5 | Recall@5 | MRR | Mean | P50 | P95 | P50 vs BM25 | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **BM25** | **0.8222** | 0.8222 | 0.5722 | 2.47 ms | **2.36 ms** | **3.93 ms** | 1.0x | **Production default** |
| Dense retrieval | 0.5667 | 0.5444 | 0.3413 | 22.24 ms | 21.15 ms | 26.07 ms | 8.9x | Not selected as a standalone method |
| Equal RRF | 0.7556 | 0.7500 | 0.5119 | 24.73 ms | 23.61 ms | 29.17 ms | 10.0x | Not selected for this corpus |
| Weighted RRF | 0.7889 | 0.7833 | 0.5384 | 24.75 ms | 23.62 ms | 29.19 ms | 10.0x | Outperforms equal RRF; not selected |
| Reranked | **0.8444** | **0.8333** | **0.5774** | 1,319.81 ms | 1,312.34 ms | 1,524.19 ms | 555.2x | Conditional quality tier |
| Multi-query | 0.7889 | 0.7889 | 0.5508 | 56.77 ms | 49.27 ms | 82.29 ms | 20.8x | Not selected for the default path |

Quality metrics are averaged over the 90 answerable questions. All methods
score 0% on the 10 unanswerable questions because none has a calibrated
abstention threshold. That remains a separate production blocker for reliable
no-answer behavior.

## Measurement protocol

- Corpus: 10 checksum-pinned arXiv PDFs, 160 pages, and 549 production-sized
  chunks.
- Questions: 100 total (90 answerable and 10 intentionally unanswerable).
- Retrieval depth: top 50 chunk candidates; quality measured over the first 5
  unique PDF pages.
- Runtime: Windows CPU, 6 PyTorch threads, models and indexes preloaded.
- Latency: warm steady-state online request path. Model loading and corpus
  indexing are recorded separately below.
- Hybrid latency is the measured sequential CPU cost of BM25 plus dense search
  plus fusion. Running the two branches concurrently may reduce wall time in a
  deployed service, but does not change the quality result.
- Model revisions, method settings, per-query rankings, and raw measurements
  are committed in [`advanced_results.json`](./advanced_results.json).

The fixed fusion weights were selected before the run and were not tuned on the
100-question test set. This avoids reporting a test-set-optimized production
configuration.

## BM25 retrieval

### Configuration

BM25 ranks Nova's 220-word overlapping chunks using exact lexical evidence.
The same deterministic acronym expansion used by the application is applied to
the query. Chunk results are deduplicated into PDF pages before evaluation.

### Measurements

- Hit@5: **0.8222**
- Recall@5: **0.8222**
- MRR: **0.5722**
- Latency: **2.36 ms P50**, **3.93 ms P95**
- One-time index build: **75.16 ms**

### Assessment

This dataset contains technical names, model acronyms, dataset names, metrics,
and numeric results that benefit from exact term matching. BM25 has the second
highest Hit@5 and is hundreds of times faster than reranking. It is the most
defensible default under an interactive latency budget.

## Neural dense retrieval

### Configuration

Dense retrieval uses `BAAI/bge-small-en-v1.5` at pinned revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`. Documents are embedded once into
384-dimensional normalized vectors and searched with FAISS inner product. The
recommended English retrieval instruction is prepended to each query.

### Measurements

- Hit@5: **0.5667**
- Recall@5: **0.5444**
- MRR: **0.3413**
- Latency: **21.15 ms P50**, **26.07 ms P95**
- One-time corpus encoding: **67.40 seconds** on CPU

### Assessment

Dense retrieval is 8.9 times slower than BM25 at P50 and loses 25.56 Hit@5
points. It should not be used alone for this technical-paper workload. The
result does not imply that dense retrieval is universally weak; a different
domain, fine-tuned embedding model, or paraphrase-heavy dataset can change the
trade-off and requires a new benchmark.

## Equal-weight RRF

### Configuration

Equal Reciprocal Rank Fusion gives BM25 and dense retrieval the same 0.50
weight, with RRF constant `k = 60`. It uses the same candidates and timing
scope as weighted RRF, making it a direct fusion-weight control.

### Measurements

- Hit@5: **0.7556**
- Recall@5: **0.7500**
- MRR: **0.5119**
- Latency: **23.61 ms P50**, **29.17 ms P95**

### Assessment

Equal RRF is 10 times slower than BM25 and loses 6.67 Hit@5 points. Giving the
weaker dense branch equal influence displaces more correct lexical results. It
also trails weighted RRF by 3.33 Hit@5 points at essentially identical latency.
Equal RRF is therefore not selected for this corpus.

## Weighted RRF

### Configuration

Weighted Reciprocal Rank Fusion combines the BM25 page ranking with the neural
dense ranking using fixed weights of 0.65 and 0.35 respectively, with RRF
constant `k = 60`.

### Measurements

- Hit@5: **0.7889**
- Recall@5: **0.7833**
- MRR: **0.5384**
- Latency: **23.62 ms P50**, **29.19 ms P95**

### Assessment

The weaker dense ranking still displaces useful lexical results, but the 0.65
BM25 weight recovers 3.33 Hit@5 points over equal RRF at no material latency
cost. Weighted RRF remains roughly 10 times slower than BM25 while losing 3.33
Hit@5 points and 3.38 MRR points. It is not selected for production. Further
weight tuning must use a separate development split, not these final 100
questions.

## Cross-encoder reranking

### Configuration

The first-stage candidate set is the top 20 pages from weighted RRF. The most
competitive chunk for each page is scored jointly with the query by
`cross-encoder/ms-marco-MiniLM-L6-v2`, pinned at revision
`c5ee24cb16019beea0893ab7796b1df96625c6b8`.

### Measurements

- Hit@5: **0.8444** — highest tested
- Recall@5: **0.8333** — highest tested
- MRR: **0.5774** — highest tested
- Latency: **1,312.34 ms P50**, **1,524.19 ms P95**

### Assessment

Reranking improves BM25 by 2.22 Hit@5 points but adds approximately 1.30
seconds of median CPU latency. The MRR gain is only 0.52 points. It is therefore
not suitable as the default interactive path. It can be offered as an explicit
high-quality mode, or reconsidered after benchmarking a smaller candidate set,
ONNX quantization, batching, or GPU inference against a defined latency SLO.

## Multi-query retrieval

### Configuration

For reproducibility and zero external API cost, multi-query uses three
deterministic variants: the original question, Nova's acronym-expanded query,
and a keyword-focused query. Each variant runs through BM25 and dense retrieval;
their rankings are combined with weighted RRF. This is not presented as
LLM-generated paraphrasing.

### Measurements

- Hit@5: **0.7889**
- Recall@5: **0.7889**
- MRR: **0.5508**
- Latency: **49.27 ms P50**, **82.29 ms P95**

### Assessment

Multi-query is 20.8 times slower than BM25 and loses 3.33 Hit@5 points. The
queries in this benchmark are already concise and rich in discriminative
technical terms, so deterministic expansion adds little useful recall and can
amplify noisy matches. It is not selected for the default production path.

## Production recommendations

1. Keep **BM25** as the default retriever and use its measured P95 of 3.93 ms as
   the local retrieval baseline, not as an end-to-end API SLO.
2. Implement and calibrate an **abstention/confidence gate** using a development
   split; all six methods currently fail unanswerable questions.
3. Keep the neural models behind an optional feature flag. Do not pay their
   memory and latency cost on every request while they underperform BM25 here.
4. If a quality tier is required, optimize the **reranker** first and rerun the
   same benchmark. Its quality signal is positive, unlike dense-only,
   equal/weighted RRF, and multi-query in this run.
5. Revisit the decision whenever the document domain, embedding model, chunking
   policy, hardware, or latency SLO changes.

## Reproduction

From `backend`:

```bash
pip install -r requirements-evaluation.txt
python evaluation/arxiv_corpus/download_papers.py
python evaluation/arxiv_corpus/extract_corpus.py
python evaluation/arxiv_corpus/build_dataset.py
python -m evaluation.advanced_retrieval_eval \
  --allow-model-download \
  --output evaluation/advanced_results.json
```

Without `--allow-model-download`, the runner operates offline and requires both
pinned models in the local Hugging Face cache. The script disables TensorFlow
imports because the benchmark uses the PyTorch CPU backend.
