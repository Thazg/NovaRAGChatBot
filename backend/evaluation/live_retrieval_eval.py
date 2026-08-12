"""Evaluate Nova with the embedding provider that is configured at runtime.

Unlike the deterministic CI benchmark, this command makes external embedding
API calls and measures genuine dense FAISS and hybrid RRF retrieval.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import faiss
import numpy as np

from config.settings import settings
from evaluation.metrics import (
    _calibrate_lexical_ranking,
    _percentile,
    _rrf,
    recall_at_k,
    reciprocal_rank,
)
from rag.embeddings import get_embeddings_batch
from rag.vector_store import HybridVectorStore, expand_query

DEFAULT_DATASET = Path(__file__).with_name("dataset.json")


def _summary(records: list[dict[str, Any]], latencies: list[float]) -> dict[str, float]:
    answerable = [record for record in records if record["answerable"]]
    unanswerable = [record for record in records if not record["answerable"]]
    return {
        "recall_at_k": mean(record["recall_at_k"] for record in answerable) if answerable else 0.0,
        "mrr": mean(record["reciprocal_rank"] for record in answerable) if answerable else 0.0,
        "unanswerable_accuracy": (
            mean(record["correctly_abstained"] for record in unanswerable) if unanswerable else 0.0
        ),
        "latency_ms_p50": _percentile(latencies, 50),
        "latency_ms_p95": _percentile(latencies, 95),
    }


def evaluate_live_retrieval(dataset: dict[str, Any], k: int, min_dense_score: float) -> dict[str, Any]:
    corpus = dataset.get("corpus", [])
    queries = dataset.get("queries", [])
    if not settings.EMBEDDING_BASE_URL:
        raise RuntimeError("EMBEDDING_BASE_URL is required for a real dense retrieval evaluation.")

    corpus_vectors = get_embeddings_batch(
        [item["content"] for item in corpus], prefix="search_document:"
    )
    query_vectors = get_embeddings_batch(
        [item["query"] for item in queries], prefix="search_query:"
    )
    if corpus_vectors is None or query_vectors is None:
        raise RuntimeError("The configured embedding provider did not return usable vectors.")
    if len(corpus_vectors) != len(corpus) or len(query_vectors) != len(queries):
        raise RuntimeError("Embedding rows do not align with the evaluation dataset.")

    corpus_vectors = np.asarray(corpus_vectors, dtype=np.float32)
    query_vectors = np.asarray(query_vectors, dtype=np.float32)
    faiss.normalize_L2(corpus_vectors)
    faiss.normalize_L2(query_vectors)
    dense_index = faiss.IndexFlatIP(corpus_vectors.shape[1])
    dense_index.add(corpus_vectors)
    corpus_ids = [item["id"] for item in corpus]
    corpus_by_id = {item["id"]: item["content"] for item in corpus}

    documents = [{
        "content": item["content"],
        "metadata": {**item.get("metadata", {}), "evaluation_id": item["id"]},
    } for item in corpus]
    bm25_store = HybridVectorStore(documents=documents)
    bm25_store._build_bm25()

    modes = {"bm25": [], "dense_faiss": [], "hybrid_rrf": []}
    latencies = {mode: [] for mode in modes}
    search_k = min(max(k, 10), len(corpus_ids))
    for query_index, sample in enumerate(queries):
        started = time.perf_counter()
        bm25_nodes = bm25_store.retrieve(sample["query"], top_k=search_k)
        bm25_ids = [node.get("metadata", {}).get("evaluation_id", "") for node in bm25_nodes]
        bm25_ids = _calibrate_lexical_ranking(expand_query(sample["query"]), bm25_ids, corpus_by_id)
        bm25_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        scores, indices = dense_index.search(query_vectors[query_index:query_index + 1], search_k)
        dense_ids = [
            corpus_ids[index]
            for score, index in zip(scores[0], indices[0])
            if index >= 0 and score >= min_dense_score
        ]
        dense_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        hybrid_ids = _rrf(bm25_ids, dense_ids)
        fusion_ms = (time.perf_counter() - started) * 1000
        latencies["bm25"].append(bm25_ms)
        latencies["dense_faiss"].append(dense_ms)
        latencies["hybrid_rrf"].append(bm25_ms + dense_ms + fusion_ms)

        for mode, retrieved_ids in {
            "bm25": bm25_ids,
            "dense_faiss": dense_ids,
            "hybrid_rrf": hybrid_ids,
        }.items():
            relevant = sample.get("relevant_ids", [])
            modes[mode].append({
                "query": sample["query"],
                "answerable": bool(relevant),
                "retrieved_ids": retrieved_ids[:k],
                "recall_at_k": recall_at_k(retrieved_ids, relevant, k),
                "reciprocal_rank": reciprocal_rank(retrieved_ids, relevant),
                "correctly_abstained": not relevant and not retrieved_ids,
            })

    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_base_url": settings.EMBEDDING_BASE_URL,
        "k": k,
        "min_dense_score": min_dense_score,
        "corpus_count": len(corpus),
        "query_count": len(queries),
        "ablations": {mode: _summary(records, latencies[mode]) for mode, records in modes.items()},
        "queries": modes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("embedding_results.json"))
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--min-dense-score", type=float, default=0.25)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    try:
        report = evaluate_live_retrieval(dataset, max(1, args.k), args.min_dense_score)
    except RuntimeError as exc:
        print(f"Evaluation not run: {exc}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "queries"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
