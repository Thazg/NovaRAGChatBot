from typing import Any
import re
from bisect import bisect_right
from tqdm import tqdm

MAX_CHUNK_SIZE = 220
CHUNK_OVERLAP = 40


def chunk_text(
    text: str,
    chunk_size: int = MAX_CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    file_path: str | None = None,
) -> list[str]:
    del file_path  # Kept for backwards-compatible call sites.
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between zero and chunk_size - 1")
    if not text:
        return []

    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = min(len(words), start + chunk_size)
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)

        if end == len(words):
            break

        start += chunk_size - overlap

    return chunks


def split_text(text: str, file_path: str | None = None) -> list[str]:
    return chunk_text(text, file_path=file_path)


def split_documents(documents: list[Any], show_progress: bool = False) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    iterator = tqdm(documents, desc="Chunking", unit="doc") if show_progress else documents

    for document in iterator:
        metadata = document.metadata or {}
        chunks = split_text(document.text, file_path=metadata.get("file_path"))
        words = list(re.finditer(r"\S+", document.text))
        source_lines = sorted(metadata.get("_line_spans", []), key=lambda line: line["start"])
        line_ends = [line["end"] for line in source_lines]

        for idx, chunk in enumerate(chunks):
            chunk_metadata = {
                **{key: value for key, value in metadata.items() if key != "_line_spans"},
                "chunk_index": idx + 1,
                "chunk_size": len(chunk),
            }
            start_word = idx * (MAX_CHUNK_SIZE - CHUNK_OVERLAP)
            window = words[start_word:start_word + MAX_CHUNK_SIZE]
            rendered_offset = 0
            line_locations: dict[int, dict] = {}
            for word in window:
                # Jump to the first overlapping interval, including words
                # joined across PDF line breaks by dehyphenation.
                line_index = bisect_right(line_ends, word.start())
                while line_index < len(source_lines) and source_lines[line_index]["start"] < word.end():
                    line = source_lines[line_index]
                    start, end = max(word.start(), line["start"]), min(word.end(), line["end"])
                    if start < end:
                        number = line["line"]
                        location = line_locations.setdefault(number, {"line": number, "start": rendered_offset + start - word.start(), "end": 0})
                        location["end"] = rendered_offset + end - word.start()
                    line_index += 1
                rendered_offset += len(word.group()) + 1
            if line_locations:
                chunk_metadata["line_spans"] = list(line_locations.values())
                chunk_metadata["line_start"] = min(line_locations)
                chunk_metadata["line_end"] = max(line_locations)
            nodes.append({
                "content": chunk,
                "metadata": chunk_metadata,
            })

    return nodes


def print_chunk_summary(documents: list[Any], nodes: list[dict[str, Any]]) -> None:
    counts = {}

    for node in nodes:
        file_type = node["metadata"].get("file_type", "unknown")
        counts[file_type] = counts.get(file_type, 0) + 1

    print(f"Chunked {len(documents)} documents into {len(nodes)} nodes")
    for file_type, count in sorted(counts.items()):
        print(f"- {file_type}: {count}")

    if nodes:
        print("\nFirst chunk preview:")
        print(nodes[0]["content"][:500])


if __name__ == "__main__":
    from load import load_documents

    documents = load_documents()
    nodes = split_documents(documents, show_progress=True)
    print_chunk_summary(documents, nodes)
