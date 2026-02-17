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
