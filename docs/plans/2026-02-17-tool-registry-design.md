# Tool Registry Design

**Date:** 2026-02-17

## Goal

Replace the monolithic tool definitions and dispatch in `llm.py` with a file-based autodiscovery registry. Adding a new tool requires dropping one file into `app/backapp/frontend/app/tools/` — nothing else changes. Also fix text-format tool call parsing to handle all common local LLM output formats.

## Context

The existing code has all tool definitions (`RETRIEVE_TOOL`, etc.), availability logic (`get_tools()`), and dispatch (`_execute_tool()`) in a single file (`llm.py`). Local LLMs sometimes emit tool calls as text rather than structured `tool_calls` API fields; the current parser only handles one of the three common text formats, causing tools like `deep_analysis` to render as raw text in the chat.

## Architecture

### Plugin Interface

Each tool is a self-contained Python file in `app/backapp/frontend/app/tools/`. Files prefixed with `_` are internal. Every tool file exposes a single module-level `plugin: ToolPlugin` variable:

```python
@dataclass
class ToolPlugin:
    definition: dict                        # OpenAI tool JSON (name, description, parameters)
    handler: AsyncCallable                  # async def handler(args, ctx) -> str | dict
    enabled: Callable[[ToolContext], bool]  # whether to include this tool for a given request
```

The `enabled` callable replaces the scattered `if has_documents` / `if settings.graphrag_enabled` checks in `get_tools()`. Each tool owns its own availability logic.

### Registry (`_registry.py`)

Runs once at import time:
- Globs `app/tools/*.py`, skips `_*.py` files
- Imports each module, looks for `module.plugin: ToolPlugin`
- Logs success (`Loaded tool: deep_analysis`) or failure (`Failed to load tools/foo.py: ...`) for each

Exposes two functions that replace what `llm.py` currently does:

```python
def get_tools(ctx: ToolContext) -> list[dict]:
    """Return OpenAI tool definitions for all enabled tools."""

async def execute_tool(name, args, ctx, on_status=None) -> str | dict:
    """Dispatch to the matching plugin's handler."""
```

`ToolContext` and `ToolEvent` move from `llm.py` into `_registry.py` (or a `_types.py`) to avoid circular imports.

### Tool Files

```
app/backapp/frontend/app/tools/
  _registry.py                  ← autodiscovery + ToolPlugin/ToolContext/ToolEvent types
  retrieve_documents.py
  query_documents_metadata.py
  web_search.py
  deep_analysis.py
  graph_search.py
```

### Text-Format Tool Call Parsing

`_parse_text_tool_calls()` (stays in `llm.py`) is extended to detect three formats in order:

**Format 1** — `<function=...>` style (already supported):
```
<function=deep_analysis>
<parameter=query>what are the types?</parameter>
</function>
```

**Format 2** — `<tool_call>` JSON (new — emitted by Qwen3):
```
<tool_call>
{"name": "deep_analysis", "arguments": {"query": "..."}}
</tool_call>
```

**Format 3** — bare JSON array (new — some Llama/Mistral variants):
```json
[{"name": "deep_analysis", "arguments": {"query": "..."}}]
```

Returns `None` if no format matches — response treated as plain text. The native OpenAI `tool_calls` API path is untouched.

## Migration

| Removed from `llm.py` | Moves to |
|---|---|
| `RETRIEVE_TOOL`, `SQL_TOOL`, `WEB_SEARCH_TOOL`, `DEEP_ANALYSIS_TOOL`, `GRAPH_SEARCH_TOOL` | individual tool files |
| `get_tools()` | `_registry.py` |
| `_execute_tool()` | `_registry.py` (dispatch) + individual tool files (logic) |
| `ToolContext`, `ToolEvent` | `_registry.py` |
| `_parse_text_tool_calls()` | stays in `llm.py`, extended |

`SYSTEM_PROMPT`, `SYSTEM_PROMPT_WITH_TOOLS`, `strip_thinking()`, and the streaming loop remain in `llm.py`.

## Constraints

- No database changes
- No frontend changes
- No API contract changes
- Existing tool behaviour preserved exactly
- `SYSTEM_PROMPT_WITH_TOOLS` stays in `llm.py` for now

## Out of Scope

- Tool versioning
- Hot-reload of tools without server restart
- Tool-level rate limiting
