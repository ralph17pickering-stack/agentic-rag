from app.tools._registry import ToolContext
from app.config import settings

def test_enabled_requires_documents_and_setting(monkeypatch):
    from app.tools.deep_analysis import plugin
    monkeypatch.setattr(settings, "sub_agents_enabled", True)
    assert plugin.enabled(ToolContext(has_documents=True)) is True
    assert plugin.enabled(ToolContext(has_documents=False)) is False

def test_definition_name():
    from app.tools.deep_analysis import plugin
    assert plugin.definition["function"]["name"] == "deep_analysis"
