# tests/test_metrics_dataset_code.py
from metrics.dataset_quality import DatasetQualityMetric
from metrics.dataset_code import DatasetCodePresenceMetric

def test_no_dataset_urls_score_zero():
    m = DatasetQualityMetric()
    r = m.compute({"datasets": [], "readme_text": "size features license"})
    assert r.score == 0.0
    assert r.extras["dataset_quality_detail"]["tier"] == "none"

def test_valid_dataset_named_only():
    m = DatasetQualityMetric()
    r = m.compute({"datasets": ["https://huggingface.co/datasets/a/b"], "readme_text": ""})
    assert r.score == 0.50

def test_valid_dataset_some_detail():
    m = DatasetQualityMetric()
    r = m.compute({
        "datasets": ["https://huggingface.co/datasets/a/b"],
        "readme_text": "The dataset has size and nothing else",
    })
    assert r.score == 0.75

def test_valid_dataset_good_detail():
    m = DatasetQualityMetric()
    r = m.compute({
        "datasets": ["https://huggingface.co/datasets/a/b"],
        "readme_text": "size and features and splits are documented",
    })
    assert r.score == 0.95

def test_dataset_code_presence_both_and_none():
    m = DatasetCodePresenceMetric()
    r1 = m.compute({"datasets": ["x"], "code": ["y"]})
    assert r1.score == 1.0
    r0 = m.compute({"datasets": [], "code": []})
    assert r0.score == 0.0
