from types import SimpleNamespace

import pytest

from rag.chunking import chunk_text, split_documents


def test_chunk_text_preserves_overlap() -> None:
    chunks = chunk_text("one two three four five", chunk_size=3, overlap=1)

    assert chunks == ["one two three", "three four five"]


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [(0, 0), (3, -1), (3, 3), (3, 4)],
)
def test_chunk_text_rejects_invalid_window(chunk_size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size=chunk_size, overlap=overlap)


def test_split_documents_keeps_source_metadata() -> None:
    document = SimpleNamespace(
        text="alpha beta gamma delta",
        metadata={"file_name": "notes.txt", "file_type": "txt"},
    )

    nodes = split_documents([document])

    assert len(nodes) == 1
    assert nodes[0]["content"] == "alpha beta gamma delta"
    assert nodes[0]["metadata"]["file_name"] == "notes.txt"
    assert nodes[0]["metadata"]["chunk_index"] == 1
