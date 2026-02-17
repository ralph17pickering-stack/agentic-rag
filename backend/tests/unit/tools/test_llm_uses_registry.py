import pytest
from unittest.mock import AsyncMock, patch


def test_get_tools_delegates_to_registry(monkeypatch):
    """llm.get_tools must use registry, not its own list."""
    import app.tools._registry as reg
    from app.tools._registry import ToolContext, ToolPlugin

    fake_plugin = ToolPlugin(
        definition={"type": "function", "function": {"name": "fake", "description": "", "parameters": {}}},
        handler=AsyncMock(),
        enabled=lambda ctx: True,
    )
    monkeypatch.setattr(reg, "_plugins", {"fake": fake_plugin})

    from app.services import llm
    from app.tools._registry import ToolContext
    ctx = ToolContext(has_documents=True)
    tools = llm.get_tools(ctx)
    names = [t["function"]["name"] for t in tools]
    assert "fake" in names


@pytest.mark.asyncio
async def test_execute_tool_delegates_to_registry(monkeypatch):
    import app.tools._registry as reg
    from app.tools._registry import ToolContext, ToolPlugin

    handler = AsyncMock(return_value="dispatched!")
    fake_plugin = ToolPlugin(
        definition={"type": "function", "function": {"name": "fake", "description": "", "parameters": {}}},
        handler=handler,
        enabled=lambda ctx: True,
    )
    monkeypatch.setattr(reg, "_plugins", {"fake": fake_plugin})

    from app.services.llm import _execute_tool
    ctx = ToolContext()
    result = await _execute_tool("fake", {"x": 1}, ctx)
    assert result == "dispatched!"
