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


def test_line_mapping_preserves_overlap_and_dehyphenated_word_offsets():
    from rag.load import Document, normalize_pdf_with_lines
    import re
    text, lines = normalize_pdf_with_lines("retrieval-\naugmented evidence.\n" + "one two three\n" * 180)
    nodes = split_documents([Document(text=text, metadata={"_line_spans": lines})])
    words = list(re.finditer(r"\S+", text))
    # Compare to a simple exhaustive interval reference, including overlapping
    # chunks and the word that straddles the first two extracted PDF lines.
    for index, node in enumerate(nodes):
        expected, offset = {}, 0
        for word in words[index * 180:index * 180 + 220]:
            for line in lines:
                start, end = max(word.start(), line["start"]), min(word.end(), line["end"])
                if start < end:
                    span = expected.setdefault(line["line"], {"line": line["line"], "start": offset + start - word.start(), "end": 0})
                    span["end"] = offset + end - word.start()
            offset += len(word.group()) + 1
        assert node["metadata"]["line_spans"] == list(expected.values())
