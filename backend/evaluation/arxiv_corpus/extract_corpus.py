from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from pypdf import PdfReader

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from rag.chunking import chunk_text


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"
LOCK_PATH = ROOT / "checksums.json"
PDF_DIR = ROOT / "pdfs"
CORPUS_PATH = ROOT / "corpus.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalize_pdf_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    for ligature, replacement in {
        "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    }.items():
        text = text.replace(ligature, replacement)
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_corpus(chunk_size: int = 220, overlap: int = 40) -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    locked = {item["pdf_file"]: item for item in lock["papers"]}
    chunks: list[dict[str, Any]] = []
    papers: list[dict[str, Any]] = []

    for paper in manifest["papers"]:
        pdf_path = PDF_DIR / paper["pdf_file"]
        if not pdf_path.is_file():
            raise ValueError(
                f"Missing {pdf_path}. Run download_papers.py before extraction."
            )
        lock_item = locked.get(paper["pdf_file"])
        if not lock_item or _sha256(pdf_path) != lock_item["sha256"]:
            raise ValueError(f"Checksum mismatch for {pdf_path.name}")

        reader = PdfReader(pdf_path)
        paper_chunk_count = 0
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = _normalize_pdf_text(page.extract_text() or "")
            if not page_text:
                continue
            page_chunks = chunk_text(
                page_text,
                chunk_size=chunk_size,
                overlap=overlap,
                file_path=paper["pdf_file"],
            )
            for chunk_index, content in enumerate(page_chunks, start=1):
                chunk_id = f"{paper['slug']}--p{page_number:03d}-c{chunk_index:02d}"
                chunks.append({
                    "id": chunk_id,
                    "content": content,
                    "metadata": {
                        "file_name": paper["pdf_file"],
                        "title": paper["title"],
                        "arxiv_id": paper["arxiv_id"],
                        "version": paper["version"],
                        "page": page_number,
                        "page_chunk": chunk_index,
                        "source_url": paper["abs_url"],
                        "pdf_sha256": lock_item["sha256"],
                    },
                })
                paper_chunk_count += 1
        papers.append({
            "arxiv_id": paper["arxiv_id"],
            "version": paper["version"],
            "slug": paper["slug"],
            "pdf_file": paper["pdf_file"],
            "pages": len(reader.pages),
            "chunks": paper_chunk_count,
            "sha256": lock_item["sha256"],
        })

    return {
        "metadata": {
            "name": manifest["name"],
            "version": manifest["version"],
            "source_format": "version-pinned arXiv PDFs",
            "extractor": "pypdf plus backend.rag.chunking.chunk_text",
            "chunk_size_words": chunk_size,
            "chunk_overlap_words": overlap,
            "paper_count": len(papers),
            "chunk_count": len(chunks),
        },
        "papers": papers,
        "corpus": chunks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract the pinned arXiv PDF corpus.")
    parser.add_argument("--chunk-size", type=int, default=220)
    parser.add_argument("--overlap", type=int, default=40)
    args = parser.parse_args()
    result = extract_corpus(args.chunk_size, args.overlap)
    CORPUS_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Extracted {result['metadata']['paper_count']} PDFs into "
        f"{result['metadata']['chunk_count']} chunks at {CORPUS_PATH}"
    )
    for paper in result["papers"]:
        print(
            f"- {paper['arxiv_id']}{paper['version']}: "
            f"{paper['pages']} pages, {paper['chunks']} chunks"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
