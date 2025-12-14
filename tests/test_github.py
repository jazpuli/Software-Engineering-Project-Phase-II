from types import SimpleNamespace
from core.github import analyze_github_urls
import core.github as ghmod

def test_analyze_github_urls_happy(monkeypatch):
    # stub Github().get_repo
    class FakeRepoObj:
        stargazers_count = 123
        def get_contributors(self): return [1,2,3]
        def get_license(self): return SimpleNamespace(license=SimpleNamespace(spdx_id="Apache-2.0"))
    class FakeGithub:
        def get_repo(self, name): return FakeRepoObj()

    # prevent real git clone, and control _walk
    monkeypatch.setattr(ghmod, "Github", lambda: FakeGithub())
    monkeypatch.setattr(ghmod, "Repo", SimpleNamespace(clone_from=lambda *a, **k: None))
    monkeypatch.setattr(ghmod, "_walk",
        lambda root, exts=None: iter([
            "/tmp/.github/workflows/ci.yml",
            "/tmp/tests/test_something.py",
            "/tmp/eval_results.md",
        ])
    )

    out = analyze_github_urls(["https://github.com/owner/name"])
    assert 0.0 <= out.get("bus_factor", 0.0) <= 1.0
    assert out.get("code_quality", 0.0) > 0.0
    assert out.get("performance_claims", 0.0) == 1.0
    assert out.get("license") == "apache-2.0"

def test_analyze_github_urls_no_repo():
    out = analyze_github_urls([])
    assert out == {}
