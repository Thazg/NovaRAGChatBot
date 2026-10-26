import numpy as np
import pytest

from config.settings import settings
from rag import embeddings
from rag.rag_chain import retrieve_from_store
from rag.vector_store import HybridVectorStore
from rag.vector_store import expand_query


def test_acronym_expansion_does_not_duplicate_capitalized_query_terms():
    upper = expand_query("Explain RAG for Orion")
    lower = expand_query("explain rag for orion")
    assert upper.casefold() == lower
    assert upper.casefold().split().count("rag") == 1
    assert upper.casefold().split().count("orion") == 1
    assert "retrieval" in upper


def node(content, name):
    return {"content": content, "metadata": {"file_name": name, "storage_name": name}}


def test_selected_document_uses_its_own_ranks_and_score_normalization(monkeypatch):
    monkeypatch.setattr(settings, "RETRIEVAL_MODE", "bm25")
    documents = [node("query elsewhere", f"other-{i}.txt") for i in range(90)]
    documents.append(node("query selected evidence", "selected.txt"))
    store = HybridVectorStore(documents=documents)
    store.bm25 = type("Scores", (), {"get_scores": lambda self, query: [100.0] * 90 + [1.0]})()
    result = store.retrieve("query", top_k=1, min_score=0.9, file_name="selected.txt")
    assert len(result) == 1
    assert result[0]["metadata"]["storage_name"] == "selected.txt"
    assert result[0]["_score"] == 1.0


def test_overlap_fallback_is_not_blocked_by_an_unrelated_document(monkeypatch):
    monkeypatch.setattr(settings, "RETRIEVAL_MODE", "bm25")
    store = HybridVectorStore(documents=[node("nebula outside", "other.txt"), node("nebula inside", "selected.txt")])
    store.bm25 = type("Scores", (), {"get_scores": lambda self, query: [2.0, -0.1]})()
    assert store.retrieve("nebula", file_name="selected.txt")[0]["content"] == "nebula inside"


def test_dense_scope_does_not_lose_selected_document_to_global_candidate_cap(monkeypatch):
    monkeypatch.setattr(settings, "RETRIEVAL_MODE", "hybrid")
    monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "https://example.invalid/embeddings")
    documents = [node("unrelated", f"other-{i}.txt") for i in range(9)] + [node("selected evidence", "selected.txt")]
    vectors = np.asarray([[1.0, i / 100] for i in range(10)], dtype=np.float32)
    store = HybridVectorStore(documents=documents, embeddings=vectors)
    store._build_bm25()
    store._build_faiss()
    monkeypatch.setattr(store, "_get_query_embedding", lambda query: np.asarray([[1.0, 0.0]], dtype=np.float32))
    result = store.retrieve("no lexical match", top_k=1, file_name="selected.txt")
    assert len(result) == 1
    assert result[0]["metadata"]["storage_name"] == "selected.txt"
    assert result[0]["_score"] == 1.0


def test_enabling_hybrid_rebuilds_vectors_for_existing_lexical_documents(monkeypatch):
    monkeypatch.setattr(settings, "RETRIEVAL_MODE", "hybrid")
    monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "https://example.invalid/embeddings")
    batches = []
    def embed(texts, prefix):
        batches.append(texts)
        return np.eye(len(texts), dtype=np.float32)
    monkeypatch.setattr(embeddings, "get_embeddings_batch", embed)
    store = HybridVectorStore(documents=[node("old lexical content", "old.txt")])
    store.add_nodes([node("new semantic content", "new.txt")])
    assert batches == [["old lexical content", "new semantic content"]]
    assert len(store.embeddings) == len(store.documents) == store.faiss_index.ntotal == 2


def test_incomplete_or_invalid_dense_batch_keeps_bm25_aligned(monkeypatch):
    monkeypatch.setattr(settings, "RETRIEVAL_MODE", "hybrid")
    monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "https://example.invalid/embeddings")
    monkeypatch.setattr(embeddings, "get_embeddings_batch", lambda *args, **kwargs: np.asarray([[float("nan"), 1.0]], dtype=np.float32))
    store = HybridVectorStore(documents=[node("old lexical content", "old.txt")])
    store.add_nodes([node("new semantic content", "new.txt")])
    assert len(store.documents) == 2
    assert store.embeddings is None
    assert store.faiss_index is None
    assert store.retrieve("semantic", file_name="new.txt")


def test_punctuation_only_upload_does_not_crash_bm25():
    store = HybridVectorStore(documents=[node("--- ... !!!", "punctuation.txt")])
    store._build_bm25()
    assert store.bm25 is None
    assert store.retrieve("evidence") == []
    assert store.retrieve("evidence", top_k=0) == []


@pytest.mark.parametrize("invalid_vector", ["not-a-vector", [float("nan"), 1.0], [1.0]])
def test_malformed_or_wrong_dimension_query_vector_falls_back_to_bm25(monkeypatch, invalid_vector):
    monkeypatch.setattr(settings, "RETRIEVAL_MODE", "hybrid")
    monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "https://example.invalid/embeddings")
    monkeypatch.setattr(embeddings, "get_embedding", lambda *args, **kwargs: invalid_vector)
    store = HybridVectorStore(documents=[node("Nebula evidence", "nebula.txt")],
                              embeddings=np.asarray([[1.0, 0.0]], dtype=np.float32))
    store._build_bm25()
    store._build_faiss()
    assert store.retrieve("nebula")[0]["metadata"]["file_name"] == "nebula.txt"
def test_storage_id_scope_takes_precedence_over_another_documents_display_name(monkeypatch):
    monkeypatch.setattr(settings, "RETRIEVAL_MODE", "bm25")
    documents = [
        {"content": "nebula selected evidence", "metadata": {"storage_name": "selected.pdf", "file_name": "original.pdf", "page": 1}},
        {"content": "nebula unrelated repeated nebula", "metadata": {"storage_name": "other.pdf", "file_name": "selected.pdf", "page": 1}},
    ]
    store = HybridVectorStore(documents=documents)
    store._build_bm25()
    selected = retrieve_from_store("nebula", store, document_name="selected.pdf")
    assert selected and {item["metadata"]["storage_name"] for item in selected} == {"selected.pdf"}
    overview = retrieve_from_store("summarize", store, document_name="selected.pdf")
    assert overview and {item["metadata"]["storage_name"] for item in overview} == {"selected.pdf"}
