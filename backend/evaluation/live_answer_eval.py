"""Run an opt-in, real-LLM grounded answer evaluation.

This command makes provider API calls. It records generated answers, citation
metrics, a deterministic lexical faithfulness proxy, reference token F1,
latency, estimated token usage, and user-supplied cost rates.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from dataclasses import dataclass

import numpy as np

from config.settings import settings
from evaluation.metrics import lexical_faithfulness
from rag.llm_client import LLMStreamError, stream_tokens
from rag.rag_chain import retrieve_from_store
from rag.vector_store import HybridVectorStore
from rag.prompts import build_prompt, build_context_and_evidence, no_context_template

DEFAULT_DATASET = Path(__file__).with_name("arxiv_corpus") / "generated_dataset.json"
_CITATION_PATTERN = re.compile(r"\(Source:\s*([^)]+?)\s*\)", re.IGNORECASE)
_EVIDENCE_PATTERN = re.compile(r"\[(E\d+)\]")
_WORD_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in _WORD_PATTERN.findall(_EVIDENCE_PATTERN.sub("", _CITATION_PATTERN.sub("", text)))]


def token_f1(prediction: str, reference: str) -> float:
    predicted = _tokens(prediction)
    expected = _tokens(reference)
    if not predicted or not expected:
        return 0.0
    predicted_counts = {token: predicted.count(token) for token in set(predicted)}
    expected_counts = {token: expected.count(token) for token in set(expected)}
    overlap = sum(min(count, expected_counts.get(token, 0)) for token, count in predicted_counts.items())
    if not overlap:
        return 0.0
    precision = overlap / len(predicted)
    recall = overlap / len(expected)
    return 2 * precision * recall / (precision + recall)


def _reference_answer(query, citation_samples):
    if query.get("reference_answer"):
        return query["reference_answer"]
    for sample in citation_samples:
        if query.get("id") is not None and sample.get("query_id") == query["id"]:
            return sample.get("answer", "")
    # Compatibility with small, single-question fixtures; never used to retrieve.
    return citation_samples[0].get("answer", "") if len(citation_samples) == 1 else ""


def _citation_scores(answer, evidence, relevant_pages):
    cited = _EVIDENCE_PATTERN.findall(answer)
    by_id = {item["id"]: item for item in evidence}
    correct = [citation for citation in cited if citation in by_id
               and (by_id[citation]["file_name"], by_id[citation]["page"]) in relevant_pages]
    supported_pages = {(by_id[citation]["file_name"], by_id[citation]["page"]) for citation in correct}
    return (len(correct) / len(cited) if cited else 0.0,
            len(supported_pages) / len(relevant_pages) if relevant_pages else 0.0,
            sorted(set(cited) - set(by_id)))



@dataclass
class GenerationResult:
    answer: str
    error_type: str | None
    first_token_ms: float | None


async def _generate(prompt: str) -> GenerationResult:
    parts: list[str] = []
    first_token_ms = None
    started = time.perf_counter()
    error_type = None
    try:
        async for token in stream_tokens(prompt):
            if token and first_token_ms is None:
                first_token_ms = (time.perf_counter() - started) * 1000
            parts.append(token)
    except LLMStreamError as exc:
        # Keep diagnostic text/usage for failed attempts, while scoring the
        # failed attempt as zero rather than presenting it as a valid answer.
        error_type = type(exc).__name__
    return GenerationResult("".join(parts).strip(), error_type, first_token_ms)


async def evaluate_live(dataset: dict, limit: int | None, delay_seconds: float,
                        input_cost_per_million: float, output_cost_per_million: float,
                        k: int = 5) -> dict:
    """Evaluate generated answers using production BM25 retrieval and packing.

    Labels are read only after context selection. This is an offline, stateless
    query path: it does not include HTTP, auth, conversation rewriting or B2 I/O.
    """
    if not 1 <= k <= 15:
        raise ValueError("k must be between 1 and 15, matching production retrieval")
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    corpus = dataset.get("corpus", [])
    if not corpus or not dataset.get("queries"):
        raise ValueError("Live evaluation requires a non-empty corpus and query list")
    documents = [{"content": item["content"], "metadata": {
        **item.get("metadata", {}),
        "evaluation_id": item.get("metadata", {}).get("relevance_id", item["id"]),
    }} for item in corpus]
    retriever = HybridVectorStore(documents=documents)
    retriever._build_bm25()
    samples = dataset["queries"][:limit]
    records: list[dict] = []
    dataset_hash = hashlib.sha256(json.dumps(
        dataset, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    for index, sample in enumerate(samples):
        question = sample["query"]
        nodes = retrieve_from_store(question, retriever, top_k=k)
        _, evidence = build_context_and_evidence(nodes, question)
        prompt = (build_prompt(question, nodes, []) if nodes else no_context_template.format(
            question=question, history="", instructions="No specific instructions."))
        # Ground truth is used only for scoring, never to construct the prompt.
        relevant_ids = set(sample.get("relevant_ids", []))
        relevant_pages = {(doc["metadata"].get("file_name", "Unknown"), doc["metadata"].get("page"))
                          for doc in documents if doc["metadata"]["evaluation_id"] in relevant_ids}
        reference = _reference_answer(sample, dataset.get("citation_samples", []))
        started = time.perf_counter()
        generation = await _generate(prompt)
        answer, error_type = generation.answer, generation.error_type
        latency_ms = (time.perf_counter() - started) * 1000
        failed = not answer or error_type is not None
        precision, recall, unsupported_ids = _citation_scores(answer, evidence, relevant_pages)
        input_tokens = math.ceil(len(prompt) / 4)
        output_tokens = math.ceil(len(answer) / 4)
        records.append({
            "id": sample.get("id"), "question": question, "answer": answer,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "reference_answer": reference, "answerable": bool(relevant_ids),
            "retrieved_ids": list(dict.fromkeys(node["metadata"]["evaluation_id"] for node in nodes)),
            "evidence": evidence, "unsupported_citation_ids": unsupported_ids,
            "provider_error": failed, "provider_error_type": error_type,
            # Citation/faithfulness scores are only defined for answerable labels;
            # absent-claim questions are retained for explicit human review.
            "citation_precision": (0.0 if failed else precision) if relevant_ids else None,
            "citation_recall": (0.0 if failed else recall) if relevant_ids else None,
            "faithfulness": (0.0 if failed else lexical_faithfulness(
                _EVIDENCE_PATTERN.sub("", answer), [item["content"] for item in evidence]
            )) if relevant_ids else None,
            "reference_token_f1": (0.0 if failed else token_f1(answer, reference)) if reference else None,
            "latency_ms": latency_ms, "first_token_ms": generation.first_token_ms,
            "estimated_input_tokens": input_tokens,
            "estimated_output_tokens": output_tokens,
        })
        if delay_seconds > 0 and index + 1 < len(samples):
            await asyncio.sleep(delay_seconds)

    successful = [record for record in records if not record["provider_error"]]
    latencies = [record["latency_ms"] for record in successful]
    attempt_latencies = [record["latency_ms"] for record in records]
    first_token_times = [record["first_token_ms"] for record in records if record["first_token_ms"] is not None]
    total_input = sum(record["estimated_input_tokens"] for record in records)
    total_output = sum(record["estimated_output_tokens"] for record in records)
    estimated_cost = (total_input * input_cost_per_million + total_output * output_cost_per_million) / 1_000_000
    def aggregate(key):
        scores = [record[key] for record in records if record[key] is not None]
        return mean(scores) if scores else 0.0
    return {
        "evaluation_version": 3,
        "dataset_sha256": dataset_hash,
        "dataset_hash_method": "canonical UTF-8 JSON; sorted keys, compact separators",
        "configuration": {"RETRIEVAL_MODE": "bm25", "TOP_K": k, **{name: getattr(settings, name) for name in (
            "RRF_K", "MAX_CHUNK_CHARS", "MAX_CONTEXT_CHARS", "MAX_HISTORY_MESSAGES",
            "MAX_TOKENS", "NUM_CTX", "TEMPERATURE", "LLM_TOP_K", "LLM_TOP_P", "LLM_SEED",
        )}},
        "pipeline": {"retrieval": "rag.rag_chain.retrieve_from_store", "mode": "bm25", "k": k,
                     "prompt": "rag.prompts.build_prompt", "context": "rag.prompts.build_context_and_evidence"},
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "provider": settings.LLM_PROVIDER,
        "model": settings.GROQ_MODEL if settings.LLM_PROVIDER == "groq" else settings.MODEL_NAME,
        "sample_count": len(records), "successful_samples": len(successful),
        "provider_failure_rate": (len(records) - len(successful)) / len(records) if records else 0.0,
        "answerable_samples": sum(record["answerable"] for record in records),
        "unanswerable_samples": sum(not record["answerable"] for record in records),
        "quality_denominator": "all labeled attempts, including provider failures scored zero; null scores excluded",
        "citation_method": "evidence-ID validity and annotated page relevance; not claim entailment",
        "unanswerable_evaluation": "answers retained for human review; no automatic answer-accuracy claim",
        "citation_precision": aggregate("citation_precision"), "citation_recall": aggregate("citation_recall"),
        "faithfulness": aggregate("faithfulness"), "faithfulness_method": "lexical_evidence_support_proxy",
        "reference_token_f1": aggregate("reference_token_f1"),
        "latency_ms_p50": float(np.percentile(latencies, 50)) if latencies else 0.0,
        "latency_ms_p95": float(np.percentile(latencies, 95)) if latencies else 0.0,
        "attempt_latency_ms_p50": float(np.percentile(attempt_latencies, 50)) if attempt_latencies else 0.0,
        "attempt_latency_ms_p95": float(np.percentile(attempt_latencies, 95)) if attempt_latencies else 0.0,
        "first_token_ms_p50": float(np.percentile(first_token_times, 50)) if first_token_times else None,
        "first_token_ms_p95": float(np.percentile(first_token_times, 95)) if first_token_times else None,
        "first_token_scope": "first non-empty provider token; includes failed attempts that emitted text; not HTTP time-to-first-byte",
        "latency_scope": "successful provider generations only; excludes retrieval, packing, HTTP and index synchronization",
        "estimated_input_tokens": total_input, "estimated_output_tokens": total_output,
        "token_estimation_method": "ceil(unicode_character_count/4), including retained partial answers; not billing usage; provider usage unavailable",
        "input_cost_per_million_usd": input_cost_per_million,
        "output_cost_per_million_usd": output_cost_per_million,
        "estimated_cost_usd": estimated_cost, "samples": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("live_results.json"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--k", type=int, choices=range(1, 16), default=5)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--input-cost-per-million", type=float, default=0.0)
    parser.add_argument("--output-cost-per-million", type=float, default=0.0)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    report = asyncio.run(evaluate_live(
        dataset,
        args.limit,
        max(0.0, args.delay_seconds),
        max(0.0, args.input_cost_per_million),
        max(0.0, args.output_cost_per_million),
        args.k,
    ))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "samples"}, indent=2))
    return 0 if report["successful_samples"] == report["sample_count"] and report["sample_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
