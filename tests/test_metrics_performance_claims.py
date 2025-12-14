from metrics.performance_claims import PerformanceClaimsMetric

def test_performance_claims_model_index_high():
    m = PerformanceClaimsMetric()
    r = m.compute({"files": ["some/dir/model-index.json"], "readme_text": ""})
    assert r.score == 0.90

def test_performance_claims_readme_strong():
    readme = "# Results\n\n| task | accuracy |\n|---|---|\nWe report accuracy on MMLU."
    m = PerformanceClaimsMetric()
    r = m.compute({"files": [], "readme_text": readme})
    assert r.score == 0.80

def test_performance_claims_weak_hints():
    m = PerformanceClaimsMetric()
    r = m.compute({"files": [], "readme_text": "We talk about accuracy only."})
    assert 0.0 <= r.score <= 0.15
