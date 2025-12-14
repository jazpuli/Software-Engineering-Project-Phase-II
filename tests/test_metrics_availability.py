# tests/test_metrics_availability.py
from metrics.availability import AvailabilityMetric
import metrics.availability as avail_mod

def test_availability_heuristic_path():
    ctx = {
        "files": ["config.json", "tokenizer.json", "weights.safetensors", "model-index.json"],
        "readme_text": "## Getting Started\n`pip install x`\n```python\nprint(1)\n```",
        "card_data": {"license": "mit"},
    }
    m = AvailabilityMetric()
    r = m.compute(ctx)
    assert 0.0 <= r.score <= 1.0
    assert r.extras["method"].startswith("heuristic")


def test_availability_llm_path_monkeypatched(monkeypatch):
    """
    Force the LLM path but stub the provider transport so NO real HTTP occurs.
    We patch providers.purdue_genai._post_chat_completion to return a perfect JSON,
    which yields an LLM score ~1.0; the metric should switch to heuristic+llm.
    """
    # Pretend API key exists and force the "LLM available" branch in metrics.availability
    monkeypatch.setenv("GEN_AI_STUDIO_API_KEY", "x")
    monkeypatch.setattr(avail_mod, "_has_any_env_key", lambda: True)

    # Patch the provider's HTTP transport used by score_ramp_up_with_llm
    import providers.purdue_genai as gen

    def fake_post_chat_completion(api_key, model, messages, stream=False, timeout=30):
        content = (
            '{'
            '"has_install": true,'
            '"has_quickstart": true,'
            '"has_examples": true,'
            '"has_requirements": true,'
            '"has_license": true,'
            '"clarity_0_1": 1.0'
            '}'
        )
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(gen, "_post_chat_completion", fake_post_chat_completion)

    m = AvailabilityMetric()
    r = m.compute({"files": [], "readme_text": "some readme text", "card_data": {}})

    assert r.extras["method"] == "heuristic+llm"
    assert r.score >= 0.9
    assert "llm" in r.extras and isinstance(r.extras["llm"], dict)
