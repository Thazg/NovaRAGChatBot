from typing import Any
from tqdm import tqdm

MAX_CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


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

        for idx, chunk in enumerate(chunks):
            chunk_metadata = {
                **metadata,
                "chunk_index": idx + 1,
                "chunk_size": len(chunk),
            }
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
