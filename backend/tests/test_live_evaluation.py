import asyncio

import pytest

from evaluation import live_answer_eval
from rag.llm_client import LLMStreamError


def dataset():
    return {"corpus": [{"id": "security-1", "content": "Passwords use PBKDF2 HMAC SHA-256.",
                        "metadata": {"file_name": "security.md", "page": 2}}],
            "queries": [{"id": "passwords-1", "query": "How are passwords hashed?",
                         "reference_answer": "Passwords use PBKDF2 HMAC SHA-256.", "relevant_ids": ["security-1"]}]}


def test_live_evaluation_selects_runtime_context_before_consulting_labels(monkeypatch):
    fixture = dataset()
    fixture["corpus"].append({"id": "other-1", "content": "An unrelated selected passage.",
                               "metadata": {"file_name": "other.md", "page": 8}})
    wrong_node = {"content": "An unrelated selected passage.", "metadata": {
        "file_name": "other.md", "page": 8, "evaluation_id": "other-1"}}
    monkeypatch.setattr(live_answer_eval, "retrieve_from_store", lambda query, store, top_k: [wrong_node])
    async def generate(prompt):
        assert "An unrelated selected passage." in prompt
        assert "Passwords use PBKDF2" not in prompt  # No oracle evidence leakage.
        yield "A fabricated claim [E99] [E0]."
    monkeypatch.setattr(live_answer_eval, "stream_tokens", generate)
    report = asyncio.run(live_answer_eval.evaluate_live(fixture, None, 0, 0, 0))
    record = report["samples"][0]
    assert record["retrieved_ids"] == ["other-1"]
    assert record["unsupported_citation_ids"] == ["E0", "E99"]
    assert record["citation_precision"] == record["citation_recall"] == 0
    assert report["pipeline"]["retrieval"] == "rag.rag_chain.retrieve_from_store"


def test_provider_failure_keeps_remaining_samples_and_penalizes_aggregate(monkeypatch):
    fixture = dataset()
    fixture["queries"] *= 2
    attempts = 0
    async def generate(prompt):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise LLMStreamError("simulated provider outage")
        yield "Passwords use PBKDF2 HMAC SHA-256. [E1]"
    monkeypatch.setattr(live_answer_eval, "stream_tokens", generate)
    report = asyncio.run(live_answer_eval.evaluate_live(fixture, None, 0, 0, 0))
    assert attempts == 2
    assert report["successful_samples"] == 1
    assert report["provider_failure_rate"] == 0.5
    assert report["samples"][0]["provider_error_type"] == "LLMStreamError"
    assert report["citation_precision"] == report["citation_recall"] == 0.5


def test_partial_failed_generation_is_retained_and_fingerprinted_without_becoming_success(monkeypatch):
    async def generate(prompt):
        yield "Passwords use PBKDF2 [E1]."
        raise LLMStreamError("simulated disconnect")
    monkeypatch.setattr(live_answer_eval, "stream_tokens", generate)
    first = asyncio.run(live_answer_eval.evaluate_live(dataset(), 1, 0, 0, 0))
    second = asyncio.run(live_answer_eval.evaluate_live(dataset(), 1, 0, 0, 0))
    record = first["samples"][0]
    assert record["answer"] == "Passwords use PBKDF2 [E1]."
    assert record["provider_error"] and first["successful_samples"] == 0
    assert record["faithfulness"] == record["citation_precision"] == 0
    assert record["estimated_output_tokens"] > 0
    assert record["first_token_ms"] >= 0
    assert first["dataset_sha256"] == second["dataset_sha256"]
    assert record["prompt_sha256"] == second["samples"][0]["prompt_sha256"]
    altered = dataset()
    altered["queries"][0]["query"] = "Which password hashing algorithm is configured?"
    third = asyncio.run(live_answer_eval.evaluate_live(altered, 1, 0, 0, 0))
    assert first["dataset_sha256"] != third["dataset_sha256"]
    assert record["prompt_sha256"] != third["samples"][0]["prompt_sha256"]
    assert not any("KEY" in name or "SECRET" in name for name in first["configuration"])


def test_unanswerable_questions_are_recorded_without_fake_accuracy(monkeypatch):
    fixture = dataset()
    fixture["queries"] = [{"id": "absent-1", "query": "What is the launch schedule?", "relevant_ids": []}]
    async def generate(prompt):
        yield "The supplied documents do not specify a launch schedule."
    monkeypatch.setattr(live_answer_eval, "stream_tokens", generate)
    report = asyncio.run(live_answer_eval.evaluate_live(fixture, None, 0, 0, 0))
    assert report["unanswerable_samples"] == 1
    assert report["samples"][0]["citation_precision"] is None
    assert "accuracy" not in report
    assert "human review" in report["unanswerable_evaluation"]


@pytest.mark.parametrize("bad_dataset,limit,k", [({}, None, 5), (dataset(), 0, 5), (dataset(), None, 16)])
def test_invalid_live_evaluation_fails_before_calling_provider(bad_dataset, limit, k):
    with pytest.raises(ValueError):
        asyncio.run(live_answer_eval.evaluate_live(bad_dataset, limit, 0, 0, 0, k))
