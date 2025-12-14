from types import SimpleNamespace
import builtins

from core.hf_api import _extract_hf_license, _readme_text, fetch_hf_model_meta

def test_extract_hf_license_priority_card_tags():
    info = SimpleNamespace(
        license=None,
        tags=["something","license:apache-2.0"],
        cardData=None,
    )
    assert _extract_hf_license(info) == "apache-2.0"

def test_readme_text_missing(monkeypatch):
    def fake_download(**kwargs): raise RuntimeError("missing")
    monkeypatch.setenv("HF_HUB_DISABLE_PROGRESS_BARS","1")
    import core.hf_api as h
    monkeypatch.setattr(h, "hf_hub_download", fake_download)
    assert _readme_text("x/y") == ""

def test_fetch_hf_model_meta(monkeypatch):
    class FakeInfo:
        def __init__(self):
            self.id = "a/b"
            self.siblings = [SimpleNamespace(rfilename="README.md", size=123)]
            self.cardData = {"license":"mit"}
            self.lastModified = "2024-01-01T00:00:00Z"
            self.downloads = 1
            self.likes = 2
        def __getattr__(self, name): return None
    class FakeApi:
        def model_info(self, repo_id, files_metadata): return FakeInfo()
    monkeypatch.setattr("core.hf_api._api", FakeApi())
    monkeypatch.setattr("core.hf_api._readme_text", lambda repo_id: "readme")
    data, ms = fetch_hf_model_meta(SimpleNamespace(owner="a", name="b"))
    assert ms >= 0
    assert data["repo_id"] == "a/b"
    assert data["files"] == ["README.md"]
    assert data["hf_license"] in ("mit","MIT","Mit")
