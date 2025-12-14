# tests/test_metrics_size.py
import json
from metrics.size import SizeMetric, _logistic
import huggingface_hub as hfh  # <-- patch the real import site used inside the function


def test_size_from_files_meta_sum():
    m = SizeMetric()
    fm = [{"rfilename": "a.safetensors", "size": 1000}, {"rfilename": "b.bin", "size": 2000}]
    r = m.compute({"files_meta": fm})
    assert "size_score" in r.extras
    assert r.extras["total_bytes"] == 3000
    assert 0 <= r.score <= 1


def test_size_from_index_json(monkeypatch, tmp_path):
    idx = {"metadata": {"total_size": 12345}}
    p = tmp_path / "model.safetensors.index.json"
    p.write_text(json.dumps(idx))

    # Patch the function exactly where metrics.size imports it (inside the function)
    def fake_hf_hub_download(*args, **kwargs):
        return str(p)

    monkeypatch.setattr(hfh, "hf_hub_download", fake_hf_hub_download)

    r = SizeMetric().compute(
        {"files_meta": [], "files": ["model.safetensors.index.json"], "repo_id": "x/y"}
    )
    assert r.extras["method"] == "index_json"
    assert r.extras["total_bytes"] == 12345


def test_size_heuristic_when_unknown():
    r = SizeMetric().compute({"files_meta": [], "files": []})
    assert r.extras["method"] == "heuristic"


def test_logistic_shape():
    # more utilization -> lower score
    assert _logistic(0.5) > _logistic(1.5)
