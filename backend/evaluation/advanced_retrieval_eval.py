"""Benchmark production retrieval candidates on the arXiv PDF dataset.

The benchmark uses a local neural bi-encoder for dense retrieval and a local
cross-encoder for reranking. Model downloads are disabled by default so a run
cannot silently make network calls; pass --allow-model-download explicitly.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import time
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

import numpy as np
from rank_bm25 import BM25Okapi

from rag.vector_store import expand_query

DEFAULT_DATASET = Path(__file__).with_name("arxiv_corpus") / "generated_dataset.json"
DEFAULT_OUTPUT = Path(__file__).with_name("advanced_results.json")

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
DENSE_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
RERANKER_REVISION = "c5ee24cb16019beea0893ab7796b1df96625c6b8"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_WORD_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_QUESTION_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "does",
    "for", "from", "how", "in", "is", "it", "of", "on", "or", "that", "the",
    "their", "this", "to", "was", "were", "what", "when", "where", "which",
    "who", "why", "with",
}


def _tokenize(text: str) -> list[str]:
    return _WORD_PATTERN.findall(text.casefold())


def _percentile(values: list[float], percentile: float) -> float:
    return float(np.percentile(np.asarray(values), percentile)) if values else 0.0


def hit_at_k(retrieved: list[str], relevant: Iterable[str], k: int) -> float:
    return float(bool(set(relevant).intersection(retrieved[:k])))


def recall_at_k(retrieved: list[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    return len(relevant_set.intersection(retrieved[:k])) / len(relevant_set) if relevant_set else 1.0


def reciprocal_rank(retrieved: list[str], relevant: Iterable[str]) -> float:
    relevant_set = set(relevant)
    return next((1.0 / rank for rank, item in enumerate(retrieved, 1) if item in relevant_set), 0.0)


def keyword_query(query: str) -> str:
    """Create a deterministic keyword-only query without external LLM calls."""
    terms = [
        token for token in _tokenize(query)
        if len(token) > 2 and token not in _QUESTION_STOPWORDS
    ]
    return " ".join(dict.fromkeys(terms)) or query


def multi_query_variants(query: str) -> list[str]:
    """Return original, acronym-expanded, and keyword-focused query variants."""
    return list(dict.fromkeys((query, expand_query(query), keyword_query(query))))


def weighted_rrf(
    rankings: Iterable[tuple[list[str], float]],
    rrf_k: int = 60,
) -> list[str]:
    scores: dict[str, float] = {}
    for ranking, weight in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + weight / (rrf_k + rank)
    return [item_id for item_id, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]


def _unique_pages(indices: Iterable[int], page_ids: list[str]) -> tuple[list[str], dict[str, int]]:
    pages: list[str] = []
    representative_chunks: dict[str, int] = {}
    for index in indices:
        page_id = page_ids[index]
        if page_id not in representative_chunks:
            pages.append(page_id)
            representative_chunks[page_id] = index
    return pages, representative_chunks


def _summarize(records: list[dict[str, Any]], latencies: list[float]) -> dict[str, float]:
    answerable = [record for record in records if record["answerable"]]
    unanswerable = [record for record in records if not record["answerable"]]
    return {
        "hit_at_5": mean(record["hit_at_5"] for record in answerable) if answerable else 0.0,
        "recall_at_5": mean(record["recall_at_5"] for record in answerable) if answerable else 0.0,
        "mrr": mean(record["reciprocal_rank"] for record in answerable) if answerable else 0.0,
        "unanswerable_accuracy": (
            mean(record["correctly_abstained"] for record in unanswerable) if unanswerable else 0.0
        ),
        "latency_ms_mean": mean(latencies) if latencies else 0.0,
        "latency_ms_p50": _percentile(latencies, 50),
        "latency_ms_p95": _percentile(latencies, 95),
    }


def evaluate(
    dataset: dict[str, Any],
    *,
    allow_model_download: bool = False,
    candidate_chunks: int = 50,
    rerank_pages: int = 20,
) -> dict[str, Any]:
    if not allow_model_download:
        os.environ["HF_HUB_OFFLINE"] = "1"
    from sentence_transformers import CrossEncoder, SentenceTransformer
    import sentence_transformers
    import torch
    import transformers
    import faiss

    corpus = dataset["corpus"]
    queries = dataset["queries"]
    texts = [item["content"] for item in corpus]
    page_ids = [item["metadata"].get("relevance_id", item["id"]) for item in corpus]
    search_k = min(candidate_chunks, len(corpus))

    started = time.perf_counter()
    bm25 = BM25Okapi([_tokenize(text) for text in texts])
    bm25_build_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    dense_model = SentenceTransformer(
        DENSE_MODEL,
        revision=DENSE_REVISION,
        device="cpu",
        local_files_only=not allow_model_download,
    )
    dense_model_load_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    corpus_embeddings = dense_model.encode(
        texts,
        batch_size=32,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).astype(np.float32)
    dense_index_build_ms = (time.perf_counter() - started) * 1000
    dense_index = faiss.IndexFlatIP(corpus_embeddings.shape[1])
    dense_index.add(corpus_embeddings)

    started = time.perf_counter()
    reranker = CrossEncoder(
        RERANKER_MODEL,
        revision=RERANKER_REVISION,
        device="cpu",
        local_files_only=not allow_model_download,
    )
    reranker_load_ms = (time.perf_counter() - started) * 1000

    # Warm up both neural models before measuring steady-state request latency.
    dense_model.encode([BGE_QUERY_PREFIX + "warmup query"], normalize_embeddings=True)
    reranker.predict([["warmup query", "warmup document"]], show_progress_bar=False)

    method_names = (
        "bm25", "dense", "equal_rrf", "weighted_rrf", "reranked", "multi_query",
    )
    records: dict[str, list[dict[str, Any]]] = {name: [] for name in method_names}
    latencies: dict[str, list[float]] = {name: [] for name in method_names}

    def bm25_search(query: str) -> tuple[list[str], dict[str, int], float]:
        started_at = time.perf_counter()
        scores = np.asarray(bm25.get_scores(_tokenize(expand_query(query))))
        ranked = np.argsort(-scores)
        indices = [int(index) for index in ranked[:search_k] if scores[index] > 0]
        pages, representatives = _unique_pages(indices, page_ids)
        return pages, representatives, (time.perf_counter() - started_at) * 1000

    def dense_search(query: str) -> tuple[list[str], dict[str, int], float]:
        started_at = time.perf_counter()
        vector = dense_model.encode(
            [BGE_QUERY_PREFIX + query],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)
        _, indices = dense_index.search(vector, search_k)
        ranked = [int(index) for index in indices[0] if index >= 0]
        pages, representatives = _unique_pages(ranked, page_ids)
        return pages, representatives, (time.perf_counter() - started_at) * 1000

    for query_index, sample in enumerate(queries, start=1):
        query = sample["query"]
        relevant = sample.get("relevant_ids", [])

        bm25_pages, bm25_representatives, bm25_ms = bm25_search(query)
        dense_pages, dense_representatives, dense_ms = dense_search(query)

        fusion_started = time.perf_counter()
        fused_pages = weighted_rrf(((bm25_pages, 0.65), (dense_pages, 0.35)))
        fusion_ms = (time.perf_counter() - fusion_started) * 1000

        equal_fusion_started = time.perf_counter()
        equal_fused_pages = weighted_rrf(((bm25_pages, 0.50), (dense_pages, 0.50)))
        equal_fusion_ms = (time.perf_counter() - equal_fusion_started) * 1000

        representative_chunks = {**dense_representatives, **bm25_representatives}
        rerank_candidates = fused_pages[:rerank_pages]
        rerank_started = time.perf_counter()
        rerank_scores = reranker.predict(
            [[query, texts[representative_chunks[page_id]]] for page_id in rerank_candidates],
            batch_size=16,
            show_progress_bar=False,
        )
        reranked_pages = [
            page_id for page_id, _ in sorted(
                zip(rerank_candidates, np.asarray(rerank_scores).reshape(-1)),
                key=lambda item: float(item[1]),
                reverse=True,
            )
        ]
        rerank_ms = (time.perf_counter() - rerank_started) * 1000

        variants = multi_query_variants(query)
        multi_rankings: list[tuple[list[str], float]] = [
            (bm25_pages, 0.65),
            (dense_pages, 0.35),
        ]
        multi_extra_ms = 0.0
        variant_weights = (0.75, 0.60)
        for variant, variant_weight in zip(variants[1:], variant_weights):
            variant_bm25, _, variant_bm25_ms = bm25_search(variant)
            variant_dense, _, variant_dense_ms = dense_search(variant)
            multi_extra_ms += variant_bm25_ms + variant_dense_ms
            multi_rankings.extend((
                (variant_bm25, 0.65 * variant_weight),
                (variant_dense, 0.35 * variant_weight),
            ))
        multi_started = time.perf_counter()
        multi_pages = weighted_rrf(multi_rankings)
        multi_fusion_ms = (time.perf_counter() - multi_started) * 1000

        rankings = {
            "bm25": bm25_pages,
            "dense": dense_pages,
            "equal_rrf": equal_fused_pages,
            "weighted_rrf": fused_pages,
            "reranked": reranked_pages,
            "multi_query": multi_pages,
        }
        method_latencies = {
            "bm25": bm25_ms,
            "dense": dense_ms,
            "equal_rrf": bm25_ms + dense_ms + equal_fusion_ms,
            "weighted_rrf": bm25_ms + dense_ms + fusion_ms,
            "reranked": bm25_ms + dense_ms + fusion_ms + rerank_ms,
            "multi_query": bm25_ms + dense_ms + multi_extra_ms + multi_fusion_ms,
        }
        for method, ranking in rankings.items():
            answerable = bool(relevant)
            records[method].append({
                "id": sample["id"],
                "answerable": answerable,
                "relevant_ids": relevant,
                "retrieved_ids": ranking[:5],
                "hit_at_5": hit_at_k(ranking, relevant, 5) if answerable else None,
                "recall_at_5": recall_at_k(ranking, relevant, 5) if answerable else None,
                "reciprocal_rank": reciprocal_rank(ranking, relevant),
                "correctly_abstained": not relevant and not ranking,
            })
            latencies[method].append(method_latencies[method])
        if query_index % 10 == 0 or query_index == len(queries):
            print(f"Evaluated {query_index}/{len(queries)} queries", flush=True)

    summaries = {
        method: _summarize(records[method], latencies[method])
        for method in method_names
    }
    return {
        "benchmark": {
            "paper_count": dataset["metadata"]["paper_count"],
            "page_count": dataset["metadata"]["page_count"],
            "chunk_count": len(corpus),
            "question_count": len(queries),
            "answerable_count": dataset["metadata"]["answerable_count"],
            "unanswerable_count": dataset["metadata"]["unanswerable_count"],
            "candidate_chunks": search_k,
            "rerank_pages": rerank_pages,
        },
        "models": {
            "dense": {"name": DENSE_MODEL, "revision": DENSE_REVISION},
            "reranker": {"name": RERANKER_MODEL, "revision": RERANKER_REVISION},
        },
        "method_configuration": {
            "bm25": "BM25 over production chunks with acronym expansion",
            "dense": "BGE-small neural embeddings, cosine/IP FAISS search",
            "equal_rrf": "BM25 weight 0.50 + dense weight 0.50; RRF k=60",
            "weighted_rrf": "BM25 weight 0.65 + dense weight 0.35; RRF k=60",
            "reranked": "Weighted-RRF top 20 pages reranked by MS MARCO MiniLM-L6 cross-encoder",
            "multi_query": "Original + acronym-expanded + keyword query; weighted BM25/dense fusion",
        },
        "indexing": {
            "bm25_build_ms": bm25_build_ms,
            "dense_model_load_ms": dense_model_load_ms,
            "dense_corpus_encode_ms": dense_index_build_ms,
            "reranker_model_load_ms": reranker_load_ms,
        },
        "runtime": {
            "device": "cpu",
            "platform": platform.platform(),
            "processor": platform.processor(),
            "torch_threads": torch.get_num_threads(),
            "sentence_transformers": sentence_transformers.__version__,
            "transformers": transformers.__version__,
            "torch": torch.__version__,
            "latency_scope": "warm steady-state query path; indexes and models preloaded; sequential CPU",
        },
        "methods": summaries,
        "queries": {method: records[method] for method in method_names},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-model-download", action="store_true")
    parser.add_argument("--candidate-chunks", type=int, default=50)
    parser.add_argument("--rerank-pages", type=int, default=20)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    report = evaluate(
        dataset,
        allow_model_download=args.allow_model_download,
        candidate_chunks=max(5, args.candidate_chunks),
        rerank_pages=max(5, args.rerank_pages),
    )
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["methods"], indent=2))
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
