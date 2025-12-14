# tests/test_metrics_code_quality.py
from metrics.code_quality import CodeQualityMetric, _pyproject_has

def test_code_quality_no_repo_fallback_readme():
    m = CodeQualityMetric()
    r = m.compute({"code": [], "readme_text": "```python\nprint('hi')\n```"})
    assert r.score == 0.2
    assert r.extras["checks"]["readme_code_blocks"] is True

def test_pyproject_has_tiny_toml(tmp_path):
    # Use a QUOTED table header so the top-level key is literally "tool.mypy"
    py = tmp_path / "pyproject.toml"
    py.write_text('["tool.mypy"]\nplugins = ["pydantic.mypy"]\n')
    assert _pyproject_has("tool.mypy", "plugins", tmp_path.as_posix()) is True
