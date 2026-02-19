from app.tools._registry import ToolContext
from app.config import settings

def test_enabled_requires_documents_and_setting():
    from app.tools.query_documents_metadata import plugin
    assert plugin.enabled(ToolContext(has_documents=True)) == settings.sql_tool_enabled
    assert plugin.enabled(ToolContext(has_documents=False)) is False

def test_definition_name():
    from app.tools.query_documents_metadata import plugin
    assert plugin.definition["function"]["name"] == "query_documents_metadata"
