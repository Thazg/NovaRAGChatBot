import pytest

from evaluation import metrics


def test_production_retrieval_timing_excludes_context_packing(monkeypatch):
    clock = [0.0]
    retrieve = metrics.retrieve_from_store
    pack = metrics.build_context_and_evidence
    def timed_retrieve(*args, **kwargs):
        result = retrieve(*args, **kwargs)
        clock[0] += 0.001
        return result
    def timed_pack(*args, **kwargs):
        result = pack(*args, **kwargs)
        clock[0] += 0.25
        return result
    monkeypatch.setattr(metrics.time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(metrics, "retrieve_from_store", timed_retrieve)
    monkeypatch.setattr(metrics, "build_context_and_evidence", timed_pack)
    fixture = {"corpus": [{"id": "one", "content": "Nebula particles produce light.",
                            "metadata": {"file_name": "one.txt"}}],
               "queries": [{"id": "q1", "query": "nebula particles", "relevant_ids": ["one"],
                            "evidence": "Nebula particles produce light."}]}
    result = metrics.evaluate_dataset(fixture)
    assert result["ablations"]["production"]["latency_ms_p50"] == pytest.approx(1.0)
    assert result["context_packing"]["latency_ms_p50"] == pytest.approx(250.0)
    assert result["context_packing"]["retention"] == 1.0


@pytest.mark.parametrize("fixture,k", [({}, 5), ({"corpus": [{"id": "one", "content": "valid corpus"}]}, 0),
                                       ({"corpus": [{"id": "one", "content": "valid corpus"}]}, 16)])
def test_evaluation_rejects_invalid_inputs_before_building_an_index(fixture, k):
    with pytest.raises(ValueError):
        metrics.evaluate_dataset(fixture, k)
def test_evidence_matching_tolerates_pdf_whitespace_only():
    from evaluation.text_matching import normalize_evidence_span

    old = "Two steps: retrieve ,\n then predict ."
    new = "two steps: retrieve, then predict."
    assert normalize_evidence_span(old) == normalize_evidence_span(new)
    assert normalize_evidence_span("betweenxandz") == normalize_evidence_span("between x and z")
    assert normalize_evidence_span("Do not retrieve, then predict.") != normalize_evidence_span("Do retrieve, then predict.")
    assert normalize_evidence_span("retrieve; predict") != normalize_evidence_span("retrieve, predict")
