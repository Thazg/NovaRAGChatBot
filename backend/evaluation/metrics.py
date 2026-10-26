from __future__ import annotations

import re
import hashlib
import json
import time
from statistics import mean
from typing import Any, Iterable

import faiss
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from rag.vector_store import HybridVectorStore, expand_query
from rag.rag_chain import retrieve_from_store
from rag.chunking import MAX_CHUNK_SIZE, CHUNK_OVERLAP
from rag.prompts import build_context_and_evidence
from evaluation.text_matching import normalize_evidence_span

_CITATION_PATTERN = re.compile(r"\(Source:\s*([^)]+?)\s*\)", re.IGNORECASE)
_WORD_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "with",
    "nova", "project",
}


def _stem_token(token: str) -> str:
    token = token.casefold()
    irregular = {
        "recovery": "recover", "cancellation": "cancel", "lived": "live",
        "stored": "store", "stores": "store", "reported": "report",
    }
    if token in irregular:
        return irregular[token]
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    for suffix in ("ingly", "edly", "ments", "ment", "ation", "tion", "ing", "ed", "es", "ly", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[:-len(suffix)]
    return token


def recall_at_k(retrieved_ids: list[str], relevant_ids: Iterable[str], k: int) -> float:
    relevant = set(relevant_ids)
    if not relevant:
        return 1.0
    return len(relevant.intersection(retrieved_ids[:k])) / len(relevant)


def reciprocal_rank(retrieved_ids: list[str], relevant_ids: Iterable[str]) -> float:
    relevant = set(relevant_ids)
    for rank, item_id in enumerate(retrieved_ids, start=1):
        if item_id in relevant:
            return 1.0 / rank
    return 0.0


def hit_at_k(retrieved_ids: list[str], relevant_ids: Iterable[str], k: int) -> float:
    relevant = set(relevant_ids)
    if not relevant:
        return 1.0
    return float(bool(relevant.intersection(retrieved_ids[:k])))


def _deduplicate(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def extract_citations(answer: str) -> list[str]:
    return [match.strip() for match in _CITATION_PATTERN.findall(answer)]


def citation_precision(answer: str, relevant_sources: Iterable[str]) -> float:
    citations = extract_citations(answer)
    if not citations:
        return 0.0
    relevant = {source.casefold() for source in relevant_sources}
    return sum(citation.casefold() in relevant for citation in citations) / len(citations)


def citation_recall(answer: str, relevant_sources: Iterable[str]) -> float:
    relevant = {source.casefold() for source in relevant_sources}
    if not relevant:
        return 1.0 if not extract_citations(answer) else 0.0
    cited = {citation.casefold() for citation in extract_citations(answer)}
    return len(cited.intersection(relevant)) / len(relevant)


def lexical_faithfulness(answer: str, evidence_texts: Iterable[str]) -> float:
    """Deterministic evidence-support proxy; not an LLM/NLI faithfulness judge."""
    evidence_tokens = {
        token.casefold()
        for text in evidence_texts
        for token in _WORD_PATTERN.findall(text)
        if token.casefold() not in _STOPWORDS
    }
    clean_answer = _CITATION_PATTERN.sub("", answer)
    claims = [part for part in re.split(r"[.!?\n]+", clean_answer) if part.strip()]
    scores: list[float] = []
    for claim in claims:
        claim_tokens = {
            token.casefold() for token in _WORD_PATTERN.findall(claim)
            if token.casefold() not in _STOPWORDS
        }
        if claim_tokens:
            scores.append(len(claim_tokens.intersection(evidence_tokens)) / len(claim_tokens))
    return mean(scores) if scores else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values), percentile))


def _rrf(*rankings: list[str], rrf_k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (rrf_k + rank)
    return [item_id for item_id, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]


def _calibrate_lexical_ranking(query: str, ranking: list[str], corpus_by_id: dict[str, str],
                               tokenized_corpus: dict[str, set[str]] | None = None) -> list[str]:
    """Remove rankings supported only by corpus-common/question boilerplate."""
    query_terms = {
        _stem_token(token) for token in _WORD_PATTERN.findall(query)
        if len(token) > 2 and token.casefold() not in _STOPWORDS
    }
    if not query_terms or not corpus_by_id:
        return ranking
    if tokenized_corpus is None:
        tokenized_corpus = {
            item_id: {_stem_token(token) for token in _WORD_PATTERN.findall(content)}
            for item_id, content in corpus_by_id.items()
        }
    max_document_frequency = max(1, int(len(tokenized_corpus) * 0.4))
    informative_terms = {
        term for term in query_terms
        if sum(term in tokens for tokens in tokenized_corpus.values()) <= max_document_frequency
    }
    if not informative_terms:
        informative_terms = query_terms
    required_overlap = 2 if len(informative_terms) >= 3 else 1
    return [
        item_id for item_id in ranking
        if len(informative_terms.intersection(tokenized_corpus.get(item_id, set()))) >= required_overlap
    ]


def evaluate_dataset(dataset: dict[str, Any], k: int = 5) -> dict[str, Any]:
    if not 1 <= k <= 15:
        raise ValueError("k must be between 1 and 15, matching production retrieval")
    corpus = dataset.get("corpus", [])
    if not corpus:
        raise ValueError("Evaluation requires a non-empty corpus")
    documents = [{
        "content": item["content"],
        "metadata": {
            **item.get("metadata", {}),
            "evaluation_id": item.get("metadata", {}).get("relevance_id", item["id"]),
        },
    } for item in corpus]
    bm25_store = HybridVectorStore(documents=documents)
    bm25_store._build_bm25()

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
    corpus_vectors = vectorizer.fit_transform([item["content"] for item in corpus]).astype(np.float32).toarray()
    faiss.normalize_L2(corpus_vectors)
    dense_index = faiss.IndexFlatIP(corpus_vectors.shape[1])
    dense_index.add(corpus_vectors)
    corpus_ids = [
        item.get("metadata", {}).get("relevance_id", item["id"])
        for item in corpus
    ]
    corpus_by_id: dict[str, str] = {}
    for item, evaluation_id in zip(corpus, corpus_ids):
        corpus_by_id[evaluation_id] = (
            f"{corpus_by_id.get(evaluation_id, '')} {item['content']}"
        ).strip()
    # Corpus preprocessing is independent of a query. Reusing these token sets
    # avoids repeatedly tokenizing every page for every proxy ablation.
    calibration_tokens = {
        item_id: {_stem_token(token) for token in _WORD_PATTERN.findall(content)}
        for item_id, content in corpus_by_id.items()
    }

    mode_results: dict[str, list[dict[str, Any]]] = {
        "production": [], "bm25": [], "tfidf_faiss_proxy": [], "hybrid_rrf": [],
    }
    candidate_k = min(max(k * 5, 25), len(corpus_ids))
    latencies: dict[str, list[float]] = {mode: [] for mode in mode_results}
    packing_results = []
    packing_latencies = []
    for sample in dataset.get("queries", []):
        started = time.perf_counter()
        production_nodes = retrieve_from_store(sample["query"], bm25_store, top_k=k)
        latencies["production"].append((time.perf_counter() - started) * 1000)
        if sample.get("evidence"):
            normalize = normalize_evidence_span
            annotated_span = normalize(sample["evidence"])
            raw_present = any(annotated_span in normalize(node["content"]) for node in production_nodes)
            packing_started = time.perf_counter()
            _, packed = build_context_and_evidence(production_nodes, sample["query"])
            packing_latencies.append((time.perf_counter() - packing_started) * 1000)
            packed_present = any(annotated_span in normalize(item["content"]) for item in packed)
            packing_results.append({"id": sample.get("id"), "retrieved_span": raw_present,
                                    "packed_span": packed_present})
        production_ids = _deduplicate(node["metadata"]["evaluation_id"] for node in production_nodes)
        started = time.perf_counter()
        bm25_nodes = bm25_store.retrieve(sample["query"], top_k=candidate_k)
        bm25_ids = _deduplicate(
            node.get("metadata", {}).get("evaluation_id", "") for node in bm25_nodes
        )
        bm25_ids = _calibrate_lexical_ranking(expand_query(sample["query"]), bm25_ids, corpus_by_id, calibration_tokens)
        bm25_latency = (time.perf_counter() - started) * 1000
        latencies["bm25"].append(bm25_latency)

        started = time.perf_counter()
        query_vector = vectorizer.transform([sample["query"]]).astype(np.float32).toarray()
        dense_ids: list[str] = []
        if np.count_nonzero(query_vector):
            faiss.normalize_L2(query_vector)
            scores, indices = dense_index.search(query_vector, candidate_k)
            dense_ids = _deduplicate(
                corpus_ids[index]
                for score, index in zip(scores[0], indices[0])
                if index >= 0 and score > 0.02
            )
            dense_ids = _calibrate_lexical_ranking(expand_query(sample["query"]), dense_ids, corpus_by_id, calibration_tokens)
        dense_latency = (time.perf_counter() - started) * 1000
        latencies["tfidf_faiss_proxy"].append(dense_latency)

        started = time.perf_counter()
        hybrid_ids = _rrf(bm25_ids, dense_ids)
        fusion_latency = (time.perf_counter() - started) * 1000
        latencies["hybrid_rrf"].append(bm25_latency + dense_latency + fusion_latency)

        for mode, retrieved_ids in {
            "production": production_ids,
            "bm25": bm25_ids,
            "tfidf_faiss_proxy": dense_ids,
            "hybrid_rrf": hybrid_ids,
        }.items():
            relevant_ids = sample.get("relevant_ids", [])
            mode_results[mode].append({
                "id": sample.get("id", sample["query"]),
                "query": sample["query"],
                "question_type": sample.get("question_type", "unspecified"),
                "paper_slug": sample.get("paper_slug", "unspecified"),
                "answerable": bool(relevant_ids),
                "relevant_ids": relevant_ids,
                "retrieved_ids": retrieved_ids[:k],
                "hit_at_k": hit_at_k(retrieved_ids, relevant_ids, k) if relevant_ids else None,
                "recall_at_k": recall_at_k(retrieved_ids, relevant_ids, k) if relevant_ids else None,
                "reciprocal_rank": reciprocal_rank(retrieved_ids, relevant_ids),
                "correctly_abstained": not relevant_ids and not retrieved_ids,
            })

    ablations: dict[str, Any] = {}
    for mode, results in mode_results.items():
        answerable = [result for result in results if result["answerable"]]
        unanswerable = [result for result in results if not result["answerable"]]
        ablations[mode] = {
            "hit_at_k": mean(item["hit_at_k"] for item in answerable) if answerable else 0.0,
            "recall_at_k": mean(item["recall_at_k"] for item in answerable) if answerable else 0.0,
            "mrr": mean(item["reciprocal_rank"] for item in answerable) if answerable else 0.0,
            "unanswerable_accuracy": mean(item["correctly_abstained"] for item in unanswerable) if unanswerable else 0.0,
            "latency_ms_p50": _percentile(latencies[mode], 50),
            "latency_ms_p95": _percentile(latencies[mode], 95),
        }

    citation_samples = dataset.get("citation_samples", [])
    citation_precision_scores = [citation_precision(item["answer"], item["relevant_sources"]) for item in citation_samples]
    citation_recall_scores = [citation_recall(item["answer"], item["relevant_sources"]) for item in citation_samples]
    faithfulness_scores = [
        lexical_faithfulness(
            item["answer"],
            [corpus_by_id[item_id] for item_id in item.get("relevant_ids", []) if item_id in corpus_by_id],
        )
        for item in citation_samples
    ]
    primary = ablations["production"]
    hybrid_answerable = [item for item in mode_results["production"] if item["answerable"]]
    per_paper: dict[str, Any] = {}
    for paper_slug in sorted({item["paper_slug"] for item in hybrid_answerable}):
        paper_results = [item for item in hybrid_answerable if item["paper_slug"] == paper_slug]
        per_paper[paper_slug] = {
            "query_count": len(paper_results),
            "hit_at_k": mean(item["hit_at_k"] for item in paper_results),
            "recall_at_k": mean(item["recall_at_k"] for item in paper_results),
            "mrr": mean(item["reciprocal_rank"] for item in paper_results),
        }
    return {
        "evaluation_version": 2,
        "primary_method": "production_bm25",
        "context_packing": {
            "method": "annotated character span, case/whitespace insensitive; not token boundaries or answer accuracy",
            "annotated_queries": len(packing_results),
            "retrieved_spans": sum(item["retrieved_span"] for item in packing_results),
            "packed_spans": sum(item["packed_span"] for item in packing_results),
            "retention": (sum(item["retrieved_span"] and item["packed_span"] for item in packing_results)
                          / sum(item["retrieved_span"] for item in packing_results)
                          if any(item["retrieved_span"] for item in packing_results) else None),
            "queries": packing_results,
            "latency_ms_p50": _percentile(packing_latencies, 50),
            "latency_ms_p95": _percentile(packing_latencies, 95),
            "latency_scope": "packing only for annotated queries; excludes annotation matching and retrieval",
        },
        "pipeline": {
            "ingestion": "rag.load.load_pdf + rag.chunking.split_documents",
            "retrieval": "rag.rag_chain.retrieve_from_store",
            "chunk_size_words": MAX_CHUNK_SIZE,
            "chunk_overlap_words": CHUNK_OVERLAP,
            "pypdf_version": dataset.get("metadata", {}).get("pypdf_version"),
            "fonttools_version": dataset.get("metadata", {}).get("fonttools_version"),
            "corpus_sha256": hashlib.sha256(json.dumps(corpus, sort_keys=True).encode()).hexdigest(),
            "latency_scope": "warm store; uncached production retrieval only; excludes packing, annotation matching, HTTP and generation",
        },
        "k": k,
        "corpus_count": len(corpus),
        "query_count": len(mode_results["production"]),
        "hit_at_k": primary["hit_at_k"],
        "recall_at_k": primary["recall_at_k"],
        "mrr": primary["mrr"],
        "citation_precision": mean(citation_precision_scores) if citation_precision_scores else 0.0,
        "citation_recall": mean(citation_recall_scores) if citation_recall_scores else 0.0,
        "faithfulness": mean(faithfulness_scores) if faithfulness_scores else 0.0,
        "faithfulness_method": "lexical_evidence_support_proxy",
        "unanswerable_accuracy": primary["unanswerable_accuracy"],
        "ablations": ablations,
        "per_paper": per_paper,
        "queries": mode_results["production"],
    }
