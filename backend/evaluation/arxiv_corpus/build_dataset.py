from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CORPUS_PATH = ROOT / "corpus.json"
SPECS_PATH = ROOT / "annotation_specs.json"
DATASET_PATH = ROOT / "generated_dataset.json"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def build_dataset() -> dict[str, Any]:
    if not CORPUS_PATH.is_file():
        raise ValueError(
            "Missing extracted corpus. Run download_papers.py and extract_corpus.py first."
        )
    extracted = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    specs = json.loads(SPECS_PATH.read_text(encoding="utf-8"))
    samples = specs["samples"]
    if len(samples) != 100:
        raise ValueError(f"Expected exactly 100 questions, found {len(samples)}")
    if len({sample["id"] for sample in samples}) != len(samples):
        raise ValueError("Question IDs must be unique")

    corpus = extracted["corpus"]
    chunks_by_slug: dict[str, list[dict[str, Any]]] = {}
    for chunk in corpus:
        chunks_by_slug.setdefault(chunk["id"].split("--", 1)[0], []).append(chunk)

    queries: list[dict[str, Any]] = []
    citation_samples: list[dict[str, Any]] = []
    reviewed_counts: Counter[str] = Counter()
    for sample in samples:
        slug = sample["paper_slug"]
        candidates = chunks_by_slug.get(slug, [])
        if not candidates:
            raise ValueError(f"{sample['id']} references unknown paper slug: {slug}")
        evidence_match = sample.get("evidence_match", "").strip()
        relevant_ids: list[str] = []
        relevant_sources: list[str] = []
        evidence_chunk_ids: list[str] = []
        evidence_pages: list[int] = []
        if evidence_match:
            needle = _normalize(evidence_match)
            matches = [chunk for chunk in candidates if needle in _normalize(chunk["content"])]
            if not matches:
                raise ValueError(f"{sample['id']} evidence was not found in {slug}: {evidence_match}")
            pages = sorted({int(chunk["metadata"]["page"]) for chunk in matches})
            page = pages[0]
            relevant_ids = [f"{slug}--p{matched_page:03d}" for matched_page in pages]
            evidence_chunk_ids = [chunk["id"] for chunk in matches]
            evidence_pages = pages
            pdf_file = matches[0]["metadata"]["file_name"]
            relevant_sources = [f"{pdf_file}#page={page}"]
        elif sample["question_type"] != "unanswerable":
            raise ValueError(f"{sample['id']} has no evidence but is not marked unanswerable")

        query = {
            "id": sample["id"],
            "query": sample["query"],
            "question_type": sample["question_type"],
            "paper_slug": slug,
            "relevant_ids": relevant_ids,
            "relevant_sources": relevant_sources,
            "reference_answer": sample["reference_answer"],
            "evidence": evidence_match,
            "evidence_pages": evidence_pages,
            "evidence_chunk_ids": evidence_chunk_ids,
            "review_status": sample["review_status"],
        }
        queries.append(query)
        reviewed_counts[sample["review_status"]] += 1
        if relevant_ids:
            citation_samples.append({
                "query_id": sample["id"],
                "answer": f"{sample['reference_answer']} (Source: {relevant_sources[0]})",
                "relevant_sources": relevant_sources,
                "relevant_ids": relevant_ids,
            })

    page_ids = {
        f"{chunk['id'].split('--', 1)[0]}--p{int(chunk['metadata']['page']):03d}"
        for chunk in corpus
    }
    for chunk in corpus:
        slug = chunk["id"].split("--", 1)[0]
        page = int(chunk["metadata"]["page"])
        chunk["metadata"]["relevance_id"] = f"{slug}--p{page:03d}"

    return {
        "metadata": {
            "name": "Nova arXiv PDF retrieval benchmark",
            "version": "1.0.0",
            "language": "English",
            "source_kind": "version-pinned arXiv PDF papers",
            "paper_count": extracted["metadata"]["paper_count"],
            "page_count": len(page_ids),
            "chunk_count": len(corpus),
            "question_count": len(queries),
            "answerable_count": sum(bool(query["relevant_ids"]) for query in queries),
            "unanswerable_count": sum(not query["relevant_ids"] for query in queries),
            "chunk_size_words": extracted["metadata"]["chunk_size_words"],
            "chunk_overlap_words": extracted["metadata"]["chunk_overlap_words"],
            "annotation_method": specs["metadata"]["annotation_method"],
            "review_status": specs["metadata"]["review_status"],
            "independent_review_status": specs["metadata"]["independent_review_status"],
            "reviewed_counts": dict(reviewed_counts),
        },
        "papers": extracted["papers"],
        "corpus": corpus,
        "queries": queries,
        "citation_samples": citation_samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the reviewed arXiv PDF benchmark dataset.")
    parser.add_argument("--output", type=Path, default=DATASET_PATH)
    args = parser.parse_args()
    dataset = build_dataset()
    args.output.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {dataset['metadata']['question_count']} questions over "
        f"{dataset['metadata']['paper_count']} PDFs / {dataset['metadata']['chunk_count']} chunks "
        f"to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
