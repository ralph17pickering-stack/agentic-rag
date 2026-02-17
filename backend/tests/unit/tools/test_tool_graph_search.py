from app.tools._registry import ToolContext
from app.config import settings

def test_enabled_requires_documents_and_setting(monkeypatch):
    from app.tools.graph_search import plugin
    monkeypatch.setattr(settings, "graphrag_enabled", True)
    assert plugin.enabled(ToolContext(has_documents=True)) is True
    assert plugin.enabled(ToolContext(has_documents=False)) is False

def test_definition_name():
    from app.tools.graph_search import plugin
    assert plugin.definition["function"]["name"] == "graph_search"
