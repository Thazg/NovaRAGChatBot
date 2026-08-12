"""Run an opt-in, real-LLM grounded answer evaluation.

This command makes provider API calls. It records generated answers, citation
metrics, a deterministic lexical faithfulness proxy, reference token F1,
latency, estimated token usage, and user-supplied cost rates.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import numpy as np

from config.settings import settings
from evaluation.metrics import citation_precision, citation_recall, lexical_faithfulness
from rag.llm_client import stream_tokens

DEFAULT_DATASET = Path(__file__).with_name("dataset.json")
_CITATION_PATTERN = re.compile(r"\(Source:\s*([^)]+?)\s*\)", re.IGNORECASE)
_WORD_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in _WORD_PATTERN.findall(_CITATION_PATTERN.sub("", text))]


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


def _question_for(source_id: str, queries: list[dict]) -> str:
    for sample in queries:
        if source_id in sample.get("relevant_ids", []):
            return sample["query"]
    raise ValueError(f"No labeled query exists for {source_id}")


def _looks_like_provider_error(answer: str) -> bool:
    lowered = answer.casefold()
    markers = (
        "[error:", "cannot reach the ai service", "too many requests",
        "service returned an error", "service connection was interrupted",
        "service took too long", "service encountered an error",
    )
    return any(marker in lowered for marker in markers)


async def _generate(prompt: str) -> str:
    parts: list[str] = []
    async for token in stream_tokens(prompt):
        parts.append(token)
    return "".join(parts).strip()


async def evaluate_live(dataset: dict, limit: int | None, delay_seconds: float,
                        input_cost_per_million: float, output_cost_per_million: float) -> dict:
    corpus = dataset["corpus"]
    corpus_by_source = {
        item["metadata"]["file_name"]: item for item in corpus
    }
    samples = dataset.get("citation_samples", [])[:limit]
    records: list[dict] = []
    for index, sample in enumerate(samples):
        sources = sample["relevant_sources"]
        evidence_items = [corpus_by_source[source] for source in sources]
        source_id = evidence_items[0]["id"]
        question = _question_for(source_id, dataset["queries"])
        evidence = "\n\n".join(
            f"[Source: {item['metadata']['file_name']}]\n{item['content']}"
            for item in evidence_items
        )
        prompt = (
            "Answer the question using only the evidence below. "
            "If the evidence is insufficient, say you do not know. "
            "Keep the answer concise and cite every factual claim using exactly "
            "(Source: filename).\n\n"
            f"Question: {question}\n\nEvidence:\n{evidence}\n\nAnswer:"
        )
        started = time.perf_counter()
        answer = await _generate(prompt)
        latency_ms = (time.perf_counter() - started) * 1000
        failed = not answer or _looks_like_provider_error(answer)
        input_tokens = math.ceil(len(prompt) / 4)
        output_tokens = math.ceil(len(answer) / 4)
        record = {
            "question": question,
            "answer": answer,
            "reference_answer": sample["answer"],
            "relevant_sources": sources,
            "provider_error": failed,
            "citation_precision": 0.0 if failed else citation_precision(answer, sources),
            "citation_recall": 0.0 if failed else citation_recall(answer, sources),
            "faithfulness": 0.0 if failed else lexical_faithfulness(
                answer, [item["content"] for item in evidence_items]
            ),
            "reference_token_f1": 0.0 if failed else token_f1(answer, sample["answer"]),
            "latency_ms": latency_ms,
            "estimated_input_tokens": input_tokens,
            "estimated_output_tokens": output_tokens,
        }
        records.append(record)
        if delay_seconds > 0 and index + 1 < len(samples):
            await asyncio.sleep(delay_seconds)

    successful = [record for record in records if not record["provider_error"]]
    latencies = [record["latency_ms"] for record in successful]
    total_input = sum(record["estimated_input_tokens"] for record in records)
    total_output = sum(record["estimated_output_tokens"] for record in records)
    estimated_cost = (
        total_input * input_cost_per_million / 1_000_000
        + total_output * output_cost_per_million / 1_000_000
    )
    aggregate = lambda key: mean(record[key] for record in successful) if successful else 0.0
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "provider": settings.LLM_PROVIDER,
        "model": settings.GROQ_MODEL if settings.LLM_PROVIDER == "groq" else settings.MODEL_NAME,
        "sample_count": len(records),
        "successful_samples": len(successful),
        "citation_precision": aggregate("citation_precision"),
        "citation_recall": aggregate("citation_recall"),
        "faithfulness": aggregate("faithfulness"),
        "faithfulness_method": "lexical_evidence_support_proxy",
        "reference_token_f1": aggregate("reference_token_f1"),
        "latency_ms_p50": float(np.percentile(latencies, 50)) if latencies else 0.0,
        "latency_ms_p95": float(np.percentile(latencies, 95)) if latencies else 0.0,
        "estimated_input_tokens": total_input,
        "estimated_output_tokens": total_output,
        "token_estimation_method": "ceil(unicode_character_count/4); provider streaming usage unavailable",
        "input_cost_per_million_usd": input_cost_per_million,
        "output_cost_per_million_usd": output_cost_per_million,
        "estimated_cost_usd": estimated_cost,
        "samples": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("live_results.json"))
    parser.add_argument("--limit", type=int, default=None)
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
    ))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "samples"}, indent=2))
    return 0 if report["successful_samples"] == report["sample_count"] and report["sample_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
