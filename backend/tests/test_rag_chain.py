from rag import rag_chain
from rag.vector_store import HybridVectorStore


def _store_with_chunks(chunks: list[str]) -> HybridVectorStore:
    store = HybridVectorStore(
        user_id="retrieval-test-user",
        documents=[
            {
                "content": content,
                "metadata": {"file_name": "paper.pdf", "storage_name": "paper.pdf"},
            }
            for content in chunks
        ],
    )
    store._build_bm25()
    return store


def test_document_overview_query_uses_representative_chunks(monkeypatch) -> None:
    store = _store_with_chunks([
        "The opening introduces a retrieval system.",
        "The middle explains reciprocal rank fusion.",
        "The conclusion reports improved answer quality.",
    ])
    monkeypatch.setattr(rag_chain, "get_retriever", lambda _user_id: store)
    rag_chain.retrieval_cache.clear()

    nodes = rag_chain.retrieve_context(
        "Summarize the main points from this document.",
        "retrieval-test-user",
        top_k=3,
    )

    assert [node["content"] for node in nodes] == [document["content"] for document in store.documents]


def test_retrieval_checks_the_entire_chunk_for_query_terms(monkeypatch) -> None:
    store = _store_with_chunks([
        f"{'introductory material ' * 80} Reciprocal fusion combines ranked result lists.",
    ])
    monkeypatch.setattr(rag_chain, "get_retriever", lambda _user_id: store)
    rag_chain.retrieval_cache.clear()

    nodes = rag_chain.retrieve_context(
        "How does reciprocal fusion ranking work?",
        "retrieval-test-user",
        top_k=3,
    )

    assert len(nodes) == 1
    assert "Reciprocal fusion" in nodes[0]["content"]
