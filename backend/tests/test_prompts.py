from rag import prompts


def test_build_context_includes_source_and_chunk() -> None:
    nodes = [
        {
            "content": "Reciprocal rank fusion combines multiple ranked result lists.",
            "metadata": {"file_name": "retrieval.pdf", "chunk_index": 4},
        }
    ]

    context = prompts.build_context(nodes)

    assert "Source: retrieval.pdf, Chunk 4" in context
    assert "Reciprocal rank fusion" in context


def test_build_context_respects_total_limit(monkeypatch) -> None:
    monkeypatch.setattr(prompts.settings, "MAX_CHUNK_CHARS", 20)
    monkeypatch.setattr(prompts.settings, "MAX_CONTEXT_CHARS", 120)
    nodes = [
        {"content": "A" * 100, "metadata": {"file_name": f"doc-{index}.txt"}}
        for index in range(5)
    ]

    context = prompts.build_context(nodes)

    assert context.count("Source:") == 1
    assert "..." in context


def test_build_prompt_contains_history_instructions_and_question() -> None:
    prompt = prompts.build_prompt(
        "What is RRF?",
        [{"content": "RRF merges rankings.", "metadata": {"file_name": "rag.md", "chunk_index": 1}}],
        [{"role": "user", "content": "We are discussing retrieval."}],
        instructions="Be concise.",
        lang_instruction="Respond in English.",
    )

    assert "What is RRF?" in prompt
    assert "user: We are discussing retrieval." in prompt
    assert "Respond in English." in prompt
    assert "Be concise." in prompt
    assert "Source: rag.md, Chunk 1" in prompt
