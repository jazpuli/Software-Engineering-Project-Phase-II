# tests/test_metrics_bus_factor.py
from types import SimpleNamespace
import sys
import metrics.bus_factor as bf
from metrics.bus_factor import BusFactorMetric

def test_bus_factor_no_repo_url():
    m = BusFactorMetric()
    r = m.compute({"code": []})
    assert r.score == 0.0
    assert r.extras["reason"] == "no_repo"

def test_bus_factor_clone_timeout(monkeypatch):
    # Force clone to "timeout" (return None)
    monkeypatch.setattr(bf, "_safe_clone", lambda url: None)
    m = BusFactorMetric()
    r = m.compute({"code": ["https://github.com/a/b"]})
    assert r.score == 0.0
    assert r.extras["reason"] == "clone_timeout"

def test_bus_factor_happy_path(monkeypatch, tmp_path):
    # Provide a fake repo root
    root = tmp_path.as_posix()
    monkeypatch.setattr(bf, "_safe_clone", lambda url: root)

    # Fake git.Repo.iter_commits to return commits with authors
    class FakeCommit:
        def __init__(self, name):
            self.author = SimpleNamespace(name=name)

    class FakeRepo:
        def __init__(self, r):
            pass
        def iter_commits(self, since=None):
            # 3 by Alice, 1 by Bob
            return [
                FakeCommit("Alice"),
                FakeCommit("Alice"),
                FakeCommit("Alice"),
                FakeCommit("Bob"),
            ]

    # Inject a fake 'git' module so 'import git' inside _author_stats sees this
    fake_git_module = SimpleNamespace(Repo=FakeRepo)
    monkeypatch.setitem(sys.modules, "git", fake_git_module)

    m = BusFactorMetric()
    r = m.compute({"code": ["https://github.com/a/b"]})

    assert 0.0 < r.score <= 1.0
    assert r.extras["contributors"] == 2
    assert r.extras["commits"] == 4
    assert 0.0 < r.extras["gini"] < 1.0
