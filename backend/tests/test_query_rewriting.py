from rag.rag_chain import rewrite_question


def history():
    return [
        {"role": "user", "content": "How does BM25 compare with dense retrieval?"},
        {"role": "assistant", "content": "UNSUPPORTED_ASSISTANT_FACT from an earlier answer."},
    ]


def test_standalone_summary_does_not_inherit_a_previous_answer():
    assert rewrite_question("summarize", history()) == "summarize"
    assert rewrite_question("Tóm tắt tài liệu này", history()) == "Tóm tắt tài liệu này"


def test_standalone_topic_switch_and_article_the_do_not_trigger_history():
    for question in ("What is Python?", "Explain Redis", "Which algorithm does the document use?"):
        assert rewrite_question(question, history()) == question


def test_followup_uses_bounded_user_questions_without_generated_facts():
    question = "How does it compare?"
    rewritten = rewrite_question(question, history())
    assert rewritten.startswith(question)
    assert "BM25" in rewritten and "dense retrieval" in rewritten
    assert "UNSUPPORTED_ASSISTANT_FACT" not in rewritten
    oversized = [{"role": "user", "content": "older " * 200}] * 10
    assert len(rewrite_question(question, oversized)) < len(question) + 500


def test_regeneration_does_not_add_the_current_question_as_its_own_context():
    question = "How does it compare?"
    rewritten = rewrite_question(question, history() + [{"role": "user", "content": question}])
    assert rewritten.count(question) == 1
    assert "BM25" in rewritten


def test_assistant_only_history_is_not_a_retrieval_source():
    assert rewrite_question("Why?", [{"role": "assistant", "content": "unverified answer"}]) == "Why?"
