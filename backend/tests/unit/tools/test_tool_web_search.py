from app.tools._registry import ToolContext
from app.config import settings

def test_enabled_requires_api_key(monkeypatch):
    from app.tools.web_search import plugin
    monkeypatch.setattr(settings, "web_search_enabled", True)
    monkeypatch.setattr(settings, "perplexity_api_key", "key123")
    assert plugin.enabled(ToolContext()) is True

def test_disabled_without_api_key(monkeypatch):
    from app.tools.web_search import plugin
    monkeypatch.setattr(settings, "perplexity_api_key", "")
    assert plugin.enabled(ToolContext()) is False
