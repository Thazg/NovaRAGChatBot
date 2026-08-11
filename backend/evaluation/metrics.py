from __future__ import annotations

import re
from statistics import mean
from typing import Any, Iterable

from rag.vector_store import HybridVectorStore

_CITATION_PATTERN = re.compile(r"\(Source:\s*([^)]+?)\s*\)", re.IGNORECASE)


def recall_at_k(retrieved_ids: list[str], relevant_ids: Iterable[str], k: int) -> float:
    relevant = set(relevant_ids)
    if not relevant:
        return 1.0
    hits = relevant.intersection(retrieved_ids[:k])
    return len(hits) / len(relevant)


def reciprocal_rank(retrieved_ids: list[str], relevant_ids: Iterable[str]) -> float:
    relevant = set(relevant_ids)
    for rank, item_id in enumerate(retrieved_ids, start=1):
        if item_id in relevant:
            return 1.0 / rank
    return 0.0


def extract_citations(answer: str) -> list[str]:
    return [match.strip() for match in _CITATION_PATTERN.findall(answer)]


def citation_precision(answer: str, relevant_sources: Iterable[str]) -> float:
    citations = extract_citations(answer)
    if not citations:
        return 0.0
    relevant = {source.casefold() for source in relevant_sources}
    correct = sum(citation.casefold() in relevant for citation in citations)
    return correct / len(citations)


def evaluate_dataset(dataset: dict[str, Any], k: int = 5) -> dict[str, Any]:
    corpus = dataset.get("corpus", [])
    store = HybridVectorStore(documents=[
        {
            "content": item["content"],
            "metadata": {**item.get("metadata", {}), "evaluation_id": item["id"]},
        }
        for item in corpus
    ])
    store._build_bm25()

    query_results = []
    for sample in dataset.get("queries", []):
        retrieved = store.retrieve(sample["query"], top_k=k)
        retrieved_ids = [
            node.get("metadata", {}).get("evaluation_id", "")
            for node in retrieved
        ]
        recall = recall_at_k(retrieved_ids, sample["relevant_ids"], k)
        rr = reciprocal_rank(retrieved_ids, sample["relevant_ids"])
        query_results.append({
            "query": sample["query"],
            "retrieved_ids": retrieved_ids,
            "recall_at_k": recall,
            "reciprocal_rank": rr,
        })

    citation_scores = [
        citation_precision(sample["answer"], sample["relevant_sources"])
        for sample in dataset.get("citation_samples", [])
    ]
    return {
        "k": k,
        "query_count": len(query_results),
        "recall_at_k": mean(item["recall_at_k"] for item in query_results) if query_results else 0.0,
        "mrr": mean(item["reciprocal_rank"] for item in query_results) if query_results else 0.0,
        "citation_precision": mean(citation_scores) if citation_scores else 0.0,
        "queries": query_results,
    }
