# tests/test_metrics_code_quality_repo.py
import os
from metrics.code_quality import CodeQualityMetric
import metrics.code_quality as cq

def test_code_quality_clone_timeout(monkeypatch):
    # Make _safe_clone return None to simulate failure
    monkeypatch.setattr(cq, "_safe_clone", lambda url, max_seconds=5: None)
    m = CodeQualityMetric()
    r = m.compute({"code": ["https://github.com/owner/repo"], "readme_text": ""})
    assert r.score == 0.0
    assert r.extras.get("clone_timeout") is True

def test_code_quality_repo_signals(monkeypatch, tmp_path):
    # Build a fake repo tree with CI, tests, typing, lint, and pyproject deps
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_something.py").write_text("def test_a(): assert True\n")

    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")

    # typing config (mypy.ini)
    (tmp_path / "mypy.ini").write_text("[mypy]\nignore_missing_imports=True\n")

    # lint config
    (tmp_path / ".flake8").write_text("[flake8]\nmax-line-length=100\n")

    # project deps in pyproject (so _pyproject_has(..., 'dependencies', ...) is true)
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["requests"]\n')

    # Force clone to return our temp dir
    monkeypatch.setattr(cq, "_safe_clone", lambda url, max_seconds=5: tmp_path.as_posix())

    # No README code blocks (keep that weight at 0.0)
    m = CodeQualityMetric()
    r = m.compute({"code": ["https://github.com/owner/repo"], "readme_text": ""})

    # Expected weighted score:
    # tests=.25, ci=.25, types=.15, lint=.15, readme_blocks=.0, pyproject_deps=.10 => 0.90
    assert abs(r.score - 0.90) < 1e-6
    ch = r.extras["checks"]
    assert ch["tests"] and ch["ci"] and ch["types"] and ch["lint"] and ch["pyproject_deps"]
