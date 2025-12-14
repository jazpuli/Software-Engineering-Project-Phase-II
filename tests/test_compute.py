from types import SimpleNamespace
from metrics.base import MetricResult
import core.compute as C

class FakeMetric:
    def __init__(self, name, val): self.name, self.val = name, val
    def compute(self, ctx): return MetricResult(score=self.val, latency_ms=1, extras={"k":"v"})

def test_collate_groups_and_clears(monkeypatch):
    calls = []
    def fake_compute_one(u, ds, code):
        calls.append((u, tuple(ds), tuple(code)))
        return {"name": u, "category":"MODEL", "net_score":0, "net_score_latency":0,
                "ramp_up_time":0, "ramp_up_time_latency":0, "bus_factor":0, "bus_factor_latency":0,
                "performance_claims":0, "performance_claims_latency":0, "license":0, "license_latency":0,
                "size_score":{}, "size_score_latency":0, "dataset_and_code_score":0, "dataset_and_code_score_latency":0,
                "dataset_quality":0, "dataset_quality_latency":0, "code_quality":0, "code_quality_latency":0}
    monkeypatch.setattr(C, "compute_one", fake_compute_one)
    seq = [
        "https://huggingface.co/datasets/aa/bb",
        "https://github.com/o/r",
        "https://huggingface.co/owner/model1",
        "https://huggingface.co/datasets/cc/dd",
        "https://huggingface.co/owner/model2",
    ]
    rows = list(C.collate(seq))
    assert len(rows) == 2
    assert calls[0][1] == ("https://huggingface.co/datasets/aa/bb",)
    assert calls[0][2] == ("https://github.com/o/r",)
    # stacks cleared before second model
    assert calls[1][1] == ("https://huggingface.co/datasets/cc/dd",)
    assert calls[1][2] == ()

def test_compute_one_with_mocks(monkeypatch):
    # make parse_url return hf_model always
    monkeypatch.setattr(C, "parse_url",
        lambda u: SimpleNamespace(kind="hf_model", owner="o", name="m"))
    # stub HF meta
    meta = {
        "files": ["model-index.json"],
        "files_meta": [{"rfilename":"a.safetensors","size":1024}],
        "card_data": {"license":"mit"},
        "hf_license": "mit",
        "last_modified": "2024-01-01T00:00:00Z",
        "downloads": 10, "likes": 2,
        "readme_text": "## Getting Started\n```python\npass\n```",
        "repo_id": "o/m",
        "name": "m",
    }
    monkeypatch.setattr(C, "fetch_hf_model_meta", lambda p: (meta, 7))
    # stub GH signals (will be merged)
    monkeypatch.setattr(C, "analyze_github_urls", lambda urls, max_commits=200: {
        "code_quality": 0.8, "performance_claims": 0.9, "license": "apache-2.0",
        "bus_factor": 0.6, "code_quality_latency": 3, "bus_factor_latency": 4
    })
    # provide a full metric registry with 8 metrics matching weights
    metrics = [
        FakeMetric("size_score", 0.5),
        FakeMetric("license", 1.0),
        FakeMetric("ramp_up_time", 1.0),
        FakeMetric("bus_factor", 0.1),
        FakeMetric("dataset_and_code_score", 1.0),
        FakeMetric("dataset_quality", 0.5),
        FakeMetric("code_quality", 0.1),
        FakeMetric("performance_claims", 0.1),
    ]
    monkeypatch.setattr(C, "metric_registry", lambda: metrics)
    # run
    row = C.compute_one("https://huggingface.co/o/m", ["ds1"], ["https://github.com/o/r"])
    # allowed keys only
    assert set(row.keys()) == {
        "name","category","net_score","net_score_latency",
        "ramp_up_time","ramp_up_time_latency","bus_factor","bus_factor_latency",
        "performance_claims","performance_claims_latency","license","license_latency",
        "size_score","size_score_latency","dataset_and_code_score","dataset_and_code_score_latency",
        "dataset_quality","dataset_quality_latency","code_quality","code_quality_latency"
    }
    # GH merge should raise some scores over base (code_quality, perf_claims, bus_factor)
    assert row["code_quality"] >= 0.8
    assert row["performance_claims"] >= 0.9
    assert row["bus_factor"] >= 0.6
    # size latency includes fetch_ms
    assert row["size_score_latency"] >= 7
