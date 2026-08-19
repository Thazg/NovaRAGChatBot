from rag import rag_chain
from rag import embeddings
from rag.vector_store import HybridVectorStore
from config.settings import settings


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


def test_document_scope_limits_overview_to_selected_file(monkeypatch) -> None:
    store = HybridVectorStore(
        user_id="retrieval-test-user",
        documents=[
            {
                "content": "Alpha opening and Alpha conclusion.",
                "metadata": {"file_name": "alpha.pdf", "storage_name": "alpha.pdf"},
            },
            {
                "content": "Beta opening and Beta conclusion.",
                "metadata": {"file_name": "beta.pdf", "storage_name": "beta.pdf"},
            },
        ],
    )
    store._build_bm25()
    monkeypatch.setattr(rag_chain, "get_retriever", lambda _user_id: store)
    rag_chain.retrieval_cache.clear()

    nodes = rag_chain.retrieve_context(
        "Summarize this document.",
        "retrieval-test-user",
        top_k=3,
        document_name="beta.pdf",
    )

    assert nodes
    assert {node["metadata"]["file_name"] for node in nodes} == {"beta.pdf"}


def test_bm25_production_mode_skips_document_embeddings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "RETRIEVAL_MODE", "bm25")
    monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "https://embedding.example/v1")

    def unexpected_embedding_call(*_args, **_kwargs):
        raise AssertionError("BM25 mode must not call the embedding provider")

    monkeypatch.setattr(embeddings, "get_embeddings_batch", unexpected_embedding_call)
    store = HybridVectorStore(user_id="bm25-production-test")

    assert store.add_nodes([{"content": "BM25 production retrieval", "metadata": {}}]) == 1
    assert store.bm25 is not None
    assert store.embeddings is None
    assert store.faiss_index is None


def test_bm25_production_mode_ignores_loaded_dense_index(monkeypatch) -> None:
    monkeypatch.setattr(settings, "RETRIEVAL_MODE", "bm25")
    monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "https://embedding.example/v1")
    store = _store_with_chunks([
        "BM25 is the production retrieval method.",
        "Dense retrieval is an experimental method.",
    ])
    store.faiss_index = type("ExistingDenseIndex", (), {"ntotal": 2})()
    monkeypatch.setattr(
        store,
        "_get_query_embedding",
        lambda _query: (_ for _ in ()).throw(AssertionError("dense query must not run")),
    )

    nodes = store.retrieve("production BM25 retrieval", top_k=1)

    assert nodes
    assert nodes[0]["content"] == "BM25 is the production retrieval method."
