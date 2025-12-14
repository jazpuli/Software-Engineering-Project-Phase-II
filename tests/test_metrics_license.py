from metrics.license import LicenseMetric

def test_license_from_hf_card():
    m = LicenseMetric()
    r = m.compute({"card_data":{"license_name":"Apache-2.0"}, "readme_text": ""})
    assert r.score == 1.0
    assert r.extras["license_note"] == "apache-2.0"
    assert r.extras["license_confidence"] == 1.0

def test_license_from_readme_section():
    md = "# License\nThis project uses GPL-3.0.\n# Other"
    m = LicenseMetric()
    r = m.compute({"card_data": {}, "readme_text": md})
    assert r.score == 0.0
    assert "readme" in r.extras["license_sources"]

def test_unknown_license_low_score():
    m = LicenseMetric()
    r = m.compute({"card_data": {"license":"unknown"}, "readme_text": ""})
    assert r.score == 0.2
