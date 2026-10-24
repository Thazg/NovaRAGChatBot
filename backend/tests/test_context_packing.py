from rag import load, prompts
from rag.chunking import split_documents


def test_default_packing_retains_tails_of_five_production_chunks():
    nodes = [{"content": " ".join([f"study{i}"] * 215 + [f"tail_evidence_{i}"] * 5),
              "metadata": {"file_name": "paper.pdf", "page": i + 1}} for i in range(5)]
    context, evidence = prompts.build_context_and_evidence(nodes, "research findings")
    assert len(evidence) == 5
    assert all(item["content"] == node["content"] for item, node in zip(evidence, nodes))
    assert len(context) <= prompts.settings.MAX_CONTEXT_CHARS


def test_query_window_under_custom_budget_keeps_exact_source_lines(monkeypatch):
    text = "ordinary filler line\n" * 50 + "needle experiment supports the conclusion.\nlast supporting line."
    document = load.Document(text=text, metadata={"file_name": "notes.txt",
        "_line_spans": [{"line": i + 1, "start": sum(len(line) for line in text.splitlines(keepends=True)[:i]),
                         "end": sum(len(line) for line in text.splitlines(keepends=True)[:i + 1])}
                        for i, _ in enumerate(text.splitlines())]})
    nodes = split_documents([document])
    monkeypatch.setattr(prompts.settings, "MAX_CHUNK_CHARS", 160)
    monkeypatch.setattr(prompts.settings, "MAX_CONTEXT_CHARS", 350)
    context, evidence = prompts.build_context_and_evidence(nodes, "What does the needle experiment support?")
    assert "needle experiment supports the conclusion." in evidence[0]["content"]
    assert evidence[0]["line_start"] > 1
    assert evidence[0]["line_end"] == 52
    assert evidence[0]["content"] in context
    assert len(context) <= 350
    prompt = prompts.build_prompt("What does the needle experiment support?", nodes, [])
    assert context in prompt


def test_line_mapping_scales_without_word_times_line_scan():
    # Count interval accesses instead of using a flaky wall-clock deadline.
    class Span(dict):
        accesses = 0
        def __getitem__(self, key):
            Span.accesses += 1
            return super().__getitem__(key)
    text = "short text line\n" * 2000
    spans = [Span(line=i + 1, start=i * 16, end=i * 16 + 15) for i in range(2000)]
    nodes = split_documents([load.Document(text=text, metadata={"_line_spans": spans})])
    assert len(nodes) > 30
    assert Span.accesses < 150_000
    assert nodes[0]["metadata"]["line_start"] == 1
    assert nodes[-1]["metadata"]["line_end"] == 2000
