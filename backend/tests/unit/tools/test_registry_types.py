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
