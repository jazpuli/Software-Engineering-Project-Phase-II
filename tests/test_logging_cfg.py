import logging, os
from core.logging_cfg import setup_logging

def test_setup_logging_silent_stdout(monkeypatch):
    monkeypatch.delenv("LOG_FILE", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "2")
    setup_logging()
    root = logging.getLogger()
    # No default StreamHandler attached by setup (keeps stdout clean)
    assert not any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert root.level == logging.DEBUG
