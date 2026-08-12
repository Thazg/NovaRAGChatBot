import json
import asyncio
from pathlib import Path

from evaluation.metrics import (
    citation_precision,
    citation_recall,
    evaluate_dataset,
    extract_citations,
    lexical_faithfulness,
    recall_at_k,
    reciprocal_rank,
)
from evaluation.live_answer_eval import evaluate_live, token_f1


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
    assert citation_recall("Fact. (Source: valid.md)", ["valid.md", "second.md"]) == 0.5
    assert lexical_faithfulness(
        "Nova combines BM25 and FAISS. (Source: retrieval.md)",
        ["Hybrid retrieval combines BM25 lexical ranking with FAISS dense vectors."],
    ) >= 0.75


def test_portfolio_dataset_meets_quality_thresholds() -> None:
    dataset_path = Path(__file__).parents[1] / "evaluation" / "dataset.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    results = evaluate_dataset(dataset, k=5)

    assert results["query_count"] >= 50
    assert results["recall_at_k"] >= 0.90
    assert results["mrr"] >= 0.80
    assert results["citation_precision"] >= 0.90
    assert results["citation_recall"] >= 0.90
    assert results["faithfulness"] >= 0.60
    assert results["unanswerable_accuracy"] == 1.0
    assert set(results["ablations"]) == {"bm25", "tfidf_faiss_proxy", "hybrid_rrf"}


def test_live_answer_evaluator_records_grounding_and_usage(monkeypatch) -> None:
    async def fake_stream(_prompt: str):
        yield "Passwords use PBKDF2 HMAC SHA-256. (Source: security.md)"

    monkeypatch.setattr("evaluation.live_answer_eval.stream_tokens", fake_stream)
    dataset = {
        "corpus": [{
            "id": "security-1",
            "content": "Passwords use PBKDF2 HMAC SHA-256.",
            "metadata": {"file_name": "security.md"},
        }],
        "queries": [{"query": "How are passwords hashed?", "relevant_ids": ["security-1"]}],
        "citation_samples": [{
            "answer": "Passwords use PBKDF2 HMAC SHA-256. (Source: security.md)",
            "relevant_sources": ["security.md"],
        }],
    }

    report = asyncio.run(evaluate_live(dataset, 1, 0, 0.10, 0.20))

    assert token_f1("Alpha beta beta", "alpha beta") > 0.75
    assert report["successful_samples"] == 1
    assert report["citation_precision"] == 1.0
    assert report["citation_recall"] == 1.0
    assert report["faithfulness"] == 1.0
    assert report["estimated_input_tokens"] > 0
    assert report["estimated_output_tokens"] > 0
    assert report["estimated_cost_usd"] > 0
