from types import SimpleNamespace

import numpy as np
import pytest

from rag import embeddings


def provider(monkeypatch, payload):
    monkeypatch.setattr(embeddings.settings, "EMBEDDING_BASE_URL", "https://embedding.example/v1")
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr(embeddings, "_get_client", lambda: SimpleNamespace(post=lambda *args, **kwargs: response))


def test_batch_response_is_ordered_by_exact_input_indices(monkeypatch):
    provider(monkeypatch, {"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]})
    assert np.array_equal(embeddings.get_embeddings_batch(["first", "second"]), [[1, 0], [0, 1]])


@pytest.mark.parametrize("data", [
    [{"index": 0, "embedding": [1, 0]}, {"index": 0, "embedding": [0, 1]}],
    [{"index": 1, "embedding": [1, 0]}, {"index": 2, "embedding": [0, 1]}],
    [{"index": 0, "embedding": [1, 0]}],
    [{"index": 0, "embedding": [1, 0]}, {"index": 1, "embedding": [1]}],
    [{"index": 0, "embedding": [float("nan")]}, {"index": 1, "embedding": [0]}],
    [{"index": 0, "embedding": [1e100]}, {"index": 1, "embedding": [0]}],
    [{"index": 0, "embedding": ["1"]}, {"index": 1, "embedding": ["0"]}],
    [{"index": False, "embedding": [1]}, {"index": 1, "embedding": [0]}],
])
def test_bad_embedding_batch_fails_closed_for_lexical_fallback(monkeypatch, data):
    provider(monkeypatch, {"data": data})
    assert embeddings.get_embeddings_batch(["first", "second"]) is None


def test_single_query_embedding_cannot_contain_non_finite_values(monkeypatch):
    provider(monkeypatch, {"data": [{"index": 0, "embedding": [float("inf")]}]})
    assert embeddings.get_embedding("question", "search_query:") is None


def test_empty_or_unconfigured_batch_does_not_contact_a_provider(monkeypatch):
    monkeypatch.setattr(embeddings.settings, "EMBEDDING_BASE_URL", "")
    monkeypatch.setattr(embeddings, "_get_client", lambda: pytest.fail("unexpected provider request"))
    assert embeddings.get_embeddings_batch(["text"]) is None
    assert embeddings.get_embeddings_batch([]) is None
