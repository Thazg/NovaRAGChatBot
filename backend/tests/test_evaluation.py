import json
from pathlib import Path

from evaluation.metrics import (
    citation_precision,
    evaluate_dataset,
    extract_citations,
    recall_at_k,
    reciprocal_rank,
)


def test_retrieval_metrics() -> None:
    retrieved = ["chunk-b", "chunk-a", "chunk-c"]

    assert recall_at_k(retrieved, ["chunk-a"], 2) == 1.0
    assert recall_at_k(retrieved, ["missing"], 3) == 0.0
    assert reciprocal_rank(retrieved, ["chunk-a"]) == 0.5
    assert reciprocal_rank(retrieved, ["missing"]) == 0.0


def test_citation_precision_rejects_unsupported_sources() -> None:
    answer = "Grounded fact. (Source: valid.md) Unsupported fact. (Source: wrong.md)"

    assert extract_citations(answer) == ["valid.md", "wrong.md"]
    assert citation_precision(answer, ["valid.md"]) == 0.5
    assert citation_precision("No citation", ["valid.md"]) == 0.0


def test_portfolio_dataset_meets_quality_thresholds() -> None:
    dataset_path = Path(__file__).parents[1] / "evaluation" / "dataset.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    results = evaluate_dataset(dataset, k=5)

    assert results["query_count"] == 6
    assert results["recall_at_k"] >= 0.90
    assert results["mrr"] >= 0.80
    assert results["citation_precision"] >= 0.90
