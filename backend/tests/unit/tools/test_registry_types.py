def test_tool_context_defaults():
    from app.tools._registry import ToolContext
    ctx = ToolContext()
    assert ctx.retrieve_fn is None
    assert ctx.user_token == ""
    assert ctx.user_id == ""
    assert ctx.has_documents is False

def test_tool_event_fields():
    from app.tools._registry import ToolEvent
    evt = ToolEvent(tool_name="web_search", data={"answer": "hello"})
    assert evt.tool_name == "web_search"
    assert evt.data == {"answer": "hello"}


def test_tool_plugin_default_enabled():
    from app.tools._registry import ToolPlugin, ToolContext
    plugin = ToolPlugin(definition={"name": "test"}, handler=lambda a, c, **kw: "ok")
    assert plugin.enabled(ToolContext()) is True


def test_tool_plugin_custom_enabled():
    from app.tools._registry import ToolPlugin, ToolContext
    plugin = ToolPlugin(
        definition={"name": "docs_only"},
        handler=lambda a, c, **kw: "ok",
        enabled=lambda ctx: ctx.has_documents,
    )
    assert plugin.enabled(ToolContext(has_documents=True)) is True
    assert plugin.enabled(ToolContext(has_documents=False)) is False


import sys
import types
from unittest.mock import AsyncMock


def _make_plugin(name="dummy", enabled=True):
    """Helper: build a ToolPlugin with a simple async handler."""
    from app.tools._registry import ToolPlugin, ToolContext
    return ToolPlugin(
        definition={"type": "function", "function": {"name": name, "description": "test", "parameters": {}}},
        handler=AsyncMock(return_value="result"),
        enabled=lambda ctx: enabled,
    )


def test_get_tools_returns_enabled_only(monkeypatch):
    from app.tools import _registry
    from app.tools._registry import ToolContext

    p_on = _make_plugin("tool_a", enabled=True)
    p_off = _make_plugin("tool_b", enabled=False)
    monkeypatch.setattr(_registry, "_plugins", {"tool_a": p_on, "tool_b": p_off})

    ctx = ToolContext(has_documents=True)
    tools = _registry.get_tools(ctx)
    names = [t["function"]["name"] for t in tools]
    assert "tool_a" in names
    assert "tool_b" not in names


import pytest

@pytest.mark.asyncio
async def test_execute_tool_dispatches(monkeypatch):
    from app.tools import _registry
    from app.tools._registry import ToolContext

    plugin = _make_plugin("dummy")
    monkeypatch.setattr(_registry, "_plugins", {"dummy": plugin})

    ctx = ToolContext()
    result = await _registry.execute_tool("dummy", {"x": 1}, ctx)
    assert result == "result"
    plugin.handler.assert_called_once_with({"x": 1}, ctx, on_status=None)


@pytest.mark.asyncio
async def test_execute_tool_unknown_returns_error(monkeypatch):
    from app.tools import _registry
    from app.tools._registry import ToolContext
    monkeypatch.setattr(_registry, "_plugins", {})
    ctx = ToolContext()
    result = await _registry.execute_tool("nonexistent", {}, ctx)
    assert "Unknown tool" in result
