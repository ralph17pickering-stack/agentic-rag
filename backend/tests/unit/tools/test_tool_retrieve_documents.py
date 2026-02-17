import pytest
from unittest.mock import AsyncMock
from app.tools._registry import ToolContext


@pytest.mark.asyncio
async def test_handler_calls_retrieve_fn():
    from app.tools.retrieve_documents import plugin

    chunks = [{"id": "c1", "document_id": "d1", "content": "hello world here", "doc_title": "T"}]
    ctx = ToolContext(retrieve_fn=AsyncMock(return_value=chunks), has_documents=True)
    result = await plugin.handler({"query": "hello"}, ctx, on_status=None)
    assert "formatted_text" in result
    assert "citation_sources" in result
    assert result["citation_sources"][0]["chunk_id"] == "c1"


def test_enabled_requires_documents():
    from app.tools.retrieve_documents import plugin
    from app.tools._registry import ToolContext

    assert plugin.enabled(ToolContext(has_documents=True)) is True
    assert plugin.enabled(ToolContext(has_documents=False)) is False
