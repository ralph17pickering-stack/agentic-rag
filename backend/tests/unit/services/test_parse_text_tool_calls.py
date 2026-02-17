def parse(content):
    from app.services.llm import _parse_text_tool_calls
    return _parse_text_tool_calls(content)


# --- Format 1: existing <function=...> style ---

def test_format1_single_tool():
    content = "<function=web_search>\n<parameter=query>climate change</parameter>\n</function>"
    result = parse(content)
    assert result is not None
    assert len(result) == 1
    assert result[0]["name"] == "web_search"
    assert result[0]["arguments"]["query"] == "climate change"


def test_format1_multi_param():
    content = "<function=retrieve_documents>\n<parameter=query>hello</parameter>\n<parameter=date_from>2024-01-01</parameter>\n</function>"
    result = parse(content)
    assert result[0]["arguments"]["date_from"] == "2024-01-01"


# --- Format 2: <tool_call> JSON style (Qwen3) ---

def test_format2_tool_call_json():
    content = '<tool_call>\n{"name": "deep_analysis", "arguments": {"query": "what are the types?"}}\n</tool_call>'
    result = parse(content)
    assert result is not None
    assert result[0]["name"] == "deep_analysis"
    assert result[0]["arguments"]["query"] == "what are the types?"


def test_format2_multiple_tool_calls():
    content = (
        '<tool_call>\n{"name": "web_search", "arguments": {"query": "foo"}}\n</tool_call>\n'
        '<tool_call>\n{"name": "retrieve_documents", "arguments": {"query": "bar"}}\n</tool_call>'
    )
    result = parse(content)
    assert len(result) == 2
    assert result[0]["name"] == "web_search"
    assert result[1]["name"] == "retrieve_documents"


# --- Format 3: bare JSON array ---

def test_format3_json_array():
    content = '[{"name": "graph_search", "arguments": {"mode": "global"}}]'
    result = parse(content)
    assert result is not None
    assert result[0]["name"] == "graph_search"
    assert result[0]["arguments"]["mode"] == "global"


def test_format3_wrapped_in_code_fence():
    content = '```json\n[{"name": "web_search", "arguments": {"query": "hello"}}]\n```'
    result = parse(content)
    assert result is not None
    assert result[0]["name"] == "web_search"


def test_format2_parameters_key_fallback():
    """Some models use 'parameters' instead of 'arguments'."""
    content = '<tool_call>\n{"name": "web_search", "parameters": {"query": "test"}}\n</tool_call>'
    result = parse(content)
    assert result is not None
    assert result[0]["name"] == "web_search"
    assert result[0]["arguments"]["query"] == "test"


def test_format3_uppercase_code_fence(monkeypatch):
    """Uppercase language tags like ```JSON should also be stripped."""
    import app.tools._registry as reg
    from app.tools._registry import ToolPlugin, ToolContext
    fake_plugin = ToolPlugin(
        definition={"type": "function", "function": {"name": "web_search", "description": "", "parameters": {}}},
        handler=lambda a, c, **kw: "ok",
        enabled=lambda ctx: True,
    )
    monkeypatch.setattr(reg, "_plugins", {"web_search": fake_plugin})
    content = '```JSON\n[{"name": "web_search", "arguments": {"query": "hello"}}]\n```'
    result = parse(content)
    assert result is not None
    assert result[0]["name"] == "web_search"


def test_format3_no_false_positive_on_named_objects(monkeypatch):
    """Arrays of objects with 'name' key that are not tool names must return None."""
    import app.tools._registry as reg
    monkeypatch.setattr(reg, "_plugins", {})  # no tools registered
    content = '[{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]'
    result = parse(content)
    assert result is None


# --- No match ---

def test_returns_none_for_plain_text():
    result = parse("Here is my answer: the sky is blue.")
    assert result is None


def test_returns_none_for_empty():
    result = parse("")
    assert result is None
