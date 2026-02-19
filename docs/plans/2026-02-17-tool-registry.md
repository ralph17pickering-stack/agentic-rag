# Tool Registry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the monolithic tool definitions and dispatch in `llm.py` with a file-based autodiscovery registry, and fix text-format tool call parsing to handle all three common local LLM output formats.

**Architecture:** Each tool lives in its own file under `app/backapp/frontend/app/tools/`. A `_registry.py` module globs the directory at import time, loads every `plugin: ToolPlugin` it finds, and exposes `get_tools(ctx)` and `execute_tool(name, args, ctx)`. `llm.py` delegates to the registry and gains two new text-format parsers.

**Tech Stack:** Python 3.13, FastAPI, dataclasses, importlib, glob — no new dependencies.

---

### Task 1: Types module (`_registry.py` — types only)

Extract `ToolContext` and `ToolEvent` from `llm.py` into the new registry module so tool files can import them without circular dependencies.

**Files:**
- Create: `app/backapp/frontend/app/tools/__init__.py`
- Create: `app/backapp/frontend/app/tools/_registry.py`
- Modify: `app/backapp/frontend/app/services/llm.py` (import ToolContext/ToolEvent from new location)

**Step 1: Write the failing test**

Create `tests/unit/tools/test_registry_types.py`:

```python
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
```

**Step 2: Run test to verify it fails**

```bash
cd /home/ralph/dev/agentic-rag/backend
source venv/bin/activate
pytest tests/unit/tools/test_registry_types.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.tools'`

**Step 3: Create `app/backapp/frontend/app/tools/__init__.py`** (empty)

```python
```

**Step 4: Create `app/backapp/frontend/app/tools/_registry.py`** with types only for now:

```python
"""Tool plugin registry — types, autodiscovery, and dispatch."""
from __future__ import annotations

import importlib
import logging
from collections.abc import AsyncIterator, Callable, Awaitable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared types (moved from llm.py to avoid circular imports)
# ---------------------------------------------------------------------------

RetrieveFn = Callable[..., Awaitable[list[dict]]]


@dataclass
class ToolContext:
    retrieve_fn: RetrieveFn | None = None
    user_token: str = ""
    user_id: str = ""
    has_documents: bool = False


@dataclass
class ToolEvent:
    tool_name: str
    data: Any


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------

@dataclass
class ToolPlugin:
    definition: dict
    handler: Callable  # async def handler(args: dict, ctx: ToolContext) -> str | dict
    enabled: Callable[[ToolContext], bool] = field(default=lambda _: True)
```

**Step 5: Run test to verify it passes**

```bash
pytest tests/unit/tools/test_registry_types.py -v
```

Expected: 2 PASS

**Step 6: Update `llm.py` to import from registry**

In `app/backapp/frontend/app/services/llm.py`, replace the `ToolContext` and `ToolEvent` dataclass definitions and the `RetrieveFn` alias with imports:

```python
from app.tools._registry import ToolContext, ToolEvent
```

Remove these lines from `llm.py`:
- `RetrieveFn = Callable[..., Awaitable[list[dict]]]`
- The `@dataclass class ToolContext:` block
- The `@dataclass class ToolEvent:` block

**Step 7: Verify the app still starts**

```bash
python -c "from app.services.llm import stream_chat_completion; print('OK')"
```

Expected: `OK`

**Step 8: Commit**

```bash
git add app/backapp/frontend/app/tools/__init__.py app/backapp/frontend/app/tools/_registry.py \
        app/backapp/frontend/app/services/llm.py \
        tests/unit/tools/test_registry_types.py
git commit -m "refactor: extract ToolContext/ToolEvent into tools/_registry.py"
```

---

### Task 2: Registry autodiscovery + dispatch

Add the `get_tools` and `execute_tool` functions to `_registry.py` — the autodiscovery loop and dispatch. No tool files yet; the registry simply loads nothing and that's fine.

**Files:**
- Modify: `app/backapp/frontend/app/tools/_registry.py`

**Step 1: Write the failing tests**

Add to `tests/unit/tools/test_registry_types.py`:

```python
import sys
import types
from unittest.mock import AsyncMock, MagicMock


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


async def test_execute_tool_dispatches(monkeypatch):
    from app.tools import _registry
    from app.tools._registry import ToolContext

    plugin = _make_plugin("dummy")
    monkeypatch.setattr(_registry, "_plugins", {"dummy": plugin})

    ctx = ToolContext()
    result = await _registry.execute_tool("dummy", {"x": 1}, ctx)
    assert result == "result"
    plugin.handler.assert_called_once_with({"x": 1}, ctx, on_status=None)


async def test_execute_tool_unknown_returns_error(monkeypatch):
    from app.tools import _registry
    monkeypatch.setattr(_registry, "_plugins", {})
    ctx = __import__("app.tools._registry", fromlist=["ToolContext"]).ToolContext()
    result = await _registry.execute_tool("nonexistent", {}, ctx)
    assert "Unknown tool" in result
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/tools/test_registry_types.py -v
```

Expected: FAIL — `AttributeError: module has no attribute '_plugins'`

**Step 3: Add autodiscovery + dispatch to `_registry.py`**

Append after the `ToolPlugin` dataclass:

```python
# ---------------------------------------------------------------------------
# Internal plugin store (populated at import time by _discover)
# ---------------------------------------------------------------------------

_plugins: dict[str, ToolPlugin] = {}


def _discover() -> None:
    """Glob app/tools/*.py, import each, register module.plugin if present."""
    tools_dir = Path(__file__).parent
    for path in sorted(tools_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"app.tools.{path.stem}"
        try:
            mod = importlib.import_module(module_name)
            plugin: ToolPlugin | None = getattr(mod, "plugin", None)
            if plugin is None:
                logger.warning("tools/%s.py has no 'plugin' attribute — skipped", path.stem)
                continue
            if not isinstance(plugin, ToolPlugin):
                logger.warning("tools/%s.py plugin is not a ToolPlugin — skipped", path.stem)
                continue
            name = plugin.definition["function"]["name"]
            _plugins[name] = plugin
            logger.info("Loaded tool: %s", name)
        except Exception:
            logger.exception("Failed to load tools/%s.py", path.stem)


_discover()


# ---------------------------------------------------------------------------
# Public API used by llm.py
# ---------------------------------------------------------------------------

def get_tools(ctx: ToolContext) -> list[dict]:
    """Return OpenAI tool definitions for all enabled plugins."""
    return [p.definition for p in _plugins.values() if p.enabled(ctx)]


async def execute_tool(
    name: str,
    args: dict,
    ctx: ToolContext,
    on_status: Callable[[str], Awaitable[None]] | None = None,
) -> str | Any:
    plugin = _plugins.get(name)
    if plugin is None:
        return f"Unknown tool: {name}"
    return await plugin.handler(args, ctx, on_status=on_status)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/tools/test_registry_types.py -v
```

Expected: all PASS

**Step 5: Commit**

```bash
git add app/backapp/frontend/app/tools/_registry.py tests/unit/tools/test_registry_types.py
git commit -m "feat: tool registry autodiscovery and dispatch"
```

---

### Task 3: Migrate `retrieve_documents` tool

Move the first tool out of `llm.py` into its own file.

**Files:**
- Create: `app/backapp/frontend/app/tools/retrieve_documents.py`
- Modify: `app/backapp/frontend/app/services/llm.py` (remove RETRIEVE_TOOL + its branch in `_execute_tool`)

**Step 1: Write the failing test**

Create `tests/unit/tools/test_tool_retrieve_documents.py`:

```python
import pytest
from unittest.mock import AsyncMock
from app.tools._registry import ToolContext


@pytest.mark.asyncio
async def test_handler_calls_retrieve_fn():
    from app.tools.retrieve_documents import plugin

    chunks = [{"id": "c1", "document_id": "d1", "content": "hello", "doc_title": "T"}]
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
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/tools/test_tool_retrieve_documents.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.tools.retrieve_documents'`

**Step 3: Create `app/backapp/frontend/app/tools/retrieve_documents.py`**

```python
"""retrieve_documents tool — searches the user's uploaded document chunks."""
from app.tools._registry import ToolContext, ToolPlugin
from app.services.llm import _format_chunks

_DEFINITION = {
    "type": "function",
    "function": {
        "name": "retrieve_documents",
        "description": "Search the user's uploaded documents for information relevant to their query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query to find relevant document chunks."},
                "date_from": {"type": "string", "description": "Optional start date filter (YYYY-MM-DD)."},
                "date_to": {"type": "string", "description": "Optional end date filter (YYYY-MM-DD)."},
                "recency_weight": {"type": "number", "description": "Weight 0-1 for recency bias. 0 = pure similarity."},
            },
            "required": ["query"],
        },
    },
}


async def _handler(args: dict, ctx: ToolContext, on_status=None) -> dict:
    query = args.get("query", "")
    kwargs = {}
    if "date_from" in args:
        kwargs["date_from"] = args["date_from"]
    if "date_to" in args:
        kwargs["date_to"] = args["date_to"]
    if "recency_weight" in args:
        kwargs["recency_weight"] = float(args["recency_weight"])
    chunks = await ctx.retrieve_fn(query, **kwargs)
    citation_sources = [
        {
            "chunk_id": chunk["id"],
            "document_id": chunk["document_id"],
            "doc_title": chunk.get("doc_title") or "Untitled",
            "chunk_index": chunk.get("chunk_index", 0),
            "content_preview": chunk["content"][:200] + "..." if len(chunk["content"]) > 200 else chunk["content"],
            "score": chunk.get("rerank_score") or chunk.get("rrf_score") or chunk.get("similarity", 0.0),
        }
        for chunk in chunks
    ]
    return {"formatted_text": _format_chunks(chunks), "citation_sources": citation_sources}


plugin = ToolPlugin(
    definition=_DEFINITION,
    handler=_handler,
    enabled=lambda ctx: ctx.has_documents,
)
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/tools/test_tool_retrieve_documents.py -v
```

Expected: 2 PASS

**Step 5: Commit**

```bash
git add app/backapp/frontend/app/tools/retrieve_documents.py tests/unit/tools/test_tool_retrieve_documents.py
git commit -m "feat: migrate retrieve_documents tool to registry"
```

---

### Task 4: Migrate remaining four tools

Migrate `query_documents_metadata`, `web_search`, `deep_analysis`, and `graph_search` using the same pattern. Each gets a test file and a tool file. This task covers all four together since the pattern is identical.

**Files:**
- Create: `app/backapp/frontend/app/tools/query_documents_metadata.py`
- Create: `app/backapp/frontend/app/tools/web_search.py`
- Create: `app/backapp/frontend/app/tools/deep_analysis.py`
- Create: `app/backapp/frontend/app/tools/graph_search.py`
- Create: `tests/unit/tools/test_tool_query_documents_metadata.py`
- Create: `tests/unit/tools/test_tool_web_search.py`
- Create: `tests/unit/tools/test_tool_deep_analysis.py`
- Create: `tests/unit/tools/test_tool_graph_search.py`

**Step 1: Write all four test files**

`tests/unit/tools/test_tool_query_documents_metadata.py`:
```python
from app.tools._registry import ToolContext
from app.config import settings

def test_enabled_requires_documents_and_setting():
    from app.tools.query_documents_metadata import plugin
    assert plugin.enabled(ToolContext(has_documents=True)) == settings.sql_tool_enabled
    assert plugin.enabled(ToolContext(has_documents=False)) is False

def test_definition_name():
    from app.tools.query_documents_metadata import plugin
    assert plugin.definition["function"]["name"] == "query_documents_metadata"
```

`tests/unit/tools/test_tool_web_search.py`:
```python
from app.tools._registry import ToolContext
from app.config import settings

def test_enabled_requires_api_key(monkeypatch):
    from app.tools.web_search import plugin
    monkeypatch.setattr(settings, "web_search_enabled", True)
    monkeypatch.setattr(settings, "perplexity_api_key", "key123")
    assert plugin.enabled(ToolContext()) is True

def test_disabled_without_api_key(monkeypatch):
    from app.tools.web_search import plugin
    monkeypatch.setattr(settings, "perplexity_api_key", "")
    assert plugin.enabled(ToolContext()) is False
```

`tests/unit/tools/test_tool_deep_analysis.py`:
```python
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
```

`tests/unit/tools/test_tool_graph_search.py`:
```python
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
```

**Step 2: Run all four test files to verify they fail**

```bash
pytest tests/unit/tools/test_tool_query_documents_metadata.py \
       tests/unit/tools/test_tool_web_search.py \
       tests/unit/tools/test_tool_deep_analysis.py \
       tests/unit/tools/test_tool_graph_search.py -v
```

Expected: all FAIL with `ModuleNotFoundError`

**Step 3: Create `app/backapp/frontend/app/tools/query_documents_metadata.py`**

```python
"""query_documents_metadata tool — natural language metadata queries via SQL."""
from app.tools._registry import ToolContext, ToolPlugin
from app.config import settings

_DEFINITION = {
    "type": "function",
    "function": {
        "name": "query_documents_metadata",
        "description": (
            "Query structured metadata about the user's documents using natural language. "
            "Use for questions about document counts, file types, topics, dates, sizes, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The natural language question about document metadata."},
            },
            "required": ["question"],
        },
    },
}


async def _handler(args: dict, ctx: ToolContext, on_status=None) -> str:
    from app.services.sql_tool import execute_metadata_query
    return await execute_metadata_query(args.get("question", ""), ctx.user_token)


plugin = ToolPlugin(
    definition=_DEFINITION,
    handler=_handler,
    enabled=lambda ctx: settings.sql_tool_enabled and ctx.has_documents,
)
```

**Step 4: Create `app/backapp/frontend/app/tools/web_search.py`**

```python
"""web_search tool — Perplexity-powered web search."""
from app.tools._registry import ToolContext, ToolPlugin
from app.config import settings

_DEFINITION = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information, news, or general knowledge. "
            "Use when the answer is unlikely to be in the user's documents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
            },
            "required": ["query"],
        },
    },
}


async def _handler(args: dict, ctx: ToolContext, on_status=None) -> dict:
    from app.services.web_search import search_web
    return await search_web(args.get("query", ""))


plugin = ToolPlugin(
    definition=_DEFINITION,
    handler=_handler,
    enabled=lambda ctx: settings.web_search_enabled and bool(settings.perplexity_api_key),
)
```

**Step 5: Create `app/backapp/frontend/app/tools/deep_analysis.py`**

```python
"""deep_analysis tool — multi-pass sub-agent analysis of the user's documents."""
from app.tools._registry import ToolContext, ToolPlugin
from app.config import settings

_DEFINITION = {
    "type": "function",
    "function": {
        "name": "deep_analysis",
        "description": (
            "Perform a thorough, multi-pass analysis of the user's documents. "
            "Use when the user asks for comprehensive analysis, detailed summaries, "
            "or deep investigation across their documents. This does multiple rounds "
            "of retrieval with different queries to ensure thorough coverage."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The analysis query describing what to investigate."},
                "focus_areas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of specific areas or topics to focus on.",
                },
            },
            "required": ["query"],
        },
    },
}


async def _handler(args: dict, ctx: ToolContext, on_status=None) -> str:
    from app.services.sub_agent import run_sub_agent
    return await run_sub_agent(
        query=args.get("query", ""),
        retrieve_fn=ctx.retrieve_fn,
        user_token=ctx.user_token,
        focus_areas=args.get("focus_areas"),
        on_status=on_status,
    )


plugin = ToolPlugin(
    definition=_DEFINITION,
    handler=_handler,
    enabled=lambda ctx: settings.sub_agents_enabled and ctx.has_documents,
)
```

**Step 6: Create `app/backapp/frontend/app/tools/graph_search.py`**

```python
"""graph_search tool — knowledge graph queries (global themes or entity paths)."""
from app.tools._registry import ToolContext, ToolPlugin
from app.config import settings

_DEFINITION = {
    "type": "function",
    "function": {
        "name": "graph_search",
        "description": (
            "Query the knowledge graph extracted from the user's documents. "
            "Use mode='global' for high-level themes, main topics, or an overview of all documents. "
            "Use mode='relationship' with entity_a and entity_b to find how two entities are connected."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["global", "relationship"],
                    "description": "'global' for theme/community overview; 'relationship' for entity path queries.",
                },
                "entity_a": {"type": "string", "description": "First entity name (required for mode='relationship')."},
                "entity_b": {"type": "string", "description": "Second entity name (required for mode='relationship')."},
            },
            "required": ["mode"],
        },
    },
}


async def _handler(args: dict, ctx: ToolContext, on_status=None) -> str:
    from app.services.graph_retrieval import global_graph_search, relationship_graph_search
    mode = args.get("mode", "global")
    if mode == "relationship":
        entity_a = args.get("entity_a", "")
        entity_b = args.get("entity_b", "")
        if not entity_a or not entity_b:
            return "relationship mode requires both entity_a and entity_b."
        return await relationship_graph_search(entity_a, entity_b, ctx.user_token, user_id=ctx.user_id)
    return await global_graph_search(ctx.user_token, settings.graphrag_global_communities_top_n, user_id=ctx.user_id)


plugin = ToolPlugin(
    definition=_DEFINITION,
    handler=_handler,
    enabled=lambda ctx: settings.graphrag_enabled and ctx.has_documents,
)
```

**Step 7: Run all four test files to verify they pass**

```bash
pytest tests/unit/tools/test_tool_query_documents_metadata.py \
       tests/unit/tools/test_tool_web_search.py \
       tests/unit/tools/test_tool_deep_analysis.py \
       tests/unit/tools/test_tool_graph_search.py -v
```

Expected: all PASS

**Step 8: Commit**

```bash
git add app/backapp/frontend/app/tools/query_documents_metadata.py \
        app/backapp/frontend/app/tools/web_search.py \
        app/backapp/frontend/app/tools/deep_analysis.py \
        app/backapp/frontend/app/tools/graph_search.py \
        tests/unit/tools/test_tool_query_documents_metadata.py \
        tests/unit/tools/test_tool_web_search.py \
        tests/unit/tools/test_tool_deep_analysis.py \
        tests/unit/tools/test_tool_graph_search.py
git commit -m "feat: migrate all remaining tools to registry"
```

---

### Task 5: Wire registry into `llm.py` + remove dead code

Replace `get_tools()` and `_execute_tool()` calls in `llm.py` with registry calls. Remove the now-redundant definitions.

**Files:**
- Modify: `app/backapp/frontend/app/services/llm.py`

**Step 1: Write the integration test**

Create `tests/unit/tools/test_llm_uses_registry.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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
    ctx = ToolContext(has_documents=True)
    tools = llm.get_tools(ctx.has_documents)
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
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/tools/test_llm_uses_registry.py -v
```

Expected: FAIL — `llm.get_tools` still uses the old internal list

**Step 3: Update `llm.py`**

In `app/backapp/frontend/app/services/llm.py`:

a) Add imports at the top:
```python
from app.tools._registry import get_tools as _registry_get_tools, execute_tool as _registry_execute_tool
```

b) Replace `get_tools()` function:
```python
def get_tools(has_documents: bool) -> list[dict]:
    from app.tools._registry import ToolContext
    return _registry_get_tools(ToolContext(has_documents=has_documents))
```

c) Replace `_execute_tool()` function body with a delegation to the registry:
```python
async def _execute_tool(
    tool_name: str,
    args: dict,
    ctx: ToolContext,
    on_status=None,
) -> str | dict:
    return await _registry_execute_tool(tool_name, args, ctx, on_status=on_status)
```

d) Remove the five tool definition constants (`RETRIEVE_TOOL`, `SQL_TOOL`, `WEB_SEARCH_TOOL`, `DEEP_ANALYSIS_TOOL`, `GRAPH_SEARCH_TOOL`) — they now live in their respective tool files.

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/tools/test_llm_uses_registry.py -v
```

Expected: PASS

**Step 5: Run all existing tests to confirm nothing broke**

```bash
pytest tests/ -v
```

Expected: all PASS

**Step 6: Verify the app starts cleanly and logs tool loading**

```bash
python -c "
import logging
logging.basicConfig(level=logging.INFO)
from app.services.llm import get_tools
print(get_tools(True))
"
```

Expected: INFO logs like `Loaded tool: retrieve_documents`, followed by a list of 5 tool dicts.

**Step 7: Commit**

```bash
git add app/backapp/frontend/app/services/llm.py tests/unit/tools/test_llm_uses_registry.py
git commit -m "refactor: wire llm.py to use tool registry, remove dead tool definitions"
```

---

### Task 6: Fix text-format tool call parsing (all three formats)

Extend `_parse_text_tool_calls` in `llm.py` to handle the `<tool_call>` JSON format and the bare JSON array format in addition to the existing `<function=...>` format.

**Files:**
- Modify: `app/backapp/frontend/app/services/llm.py`
- Create: `tests/unit/services/test_parse_text_tool_calls.py`

**Step 1: Write failing tests**

Create `tests/unit/services/test_parse_text_tool_calls.py`:

```python
import pytest


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


# --- No match ---

def test_returns_none_for_plain_text():
    result = parse("Here is my answer: the sky is blue.")
    assert result is None


def test_returns_none_for_empty():
    result = parse("")
    assert result is None
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/services/test_parse_text_tool_calls.py -v
```

Expected: Format 1 tests PASS (already implemented), Format 2 and 3 FAIL.

**Step 3: Update `_parse_text_tool_calls` in `llm.py`**

Replace the existing function with:

```python
def _parse_text_tool_calls(content: str) -> list[dict] | None:
    """Parse tool calls emitted as text by local LLMs.

    Handles three formats:
      1. <function=name><parameter=k>v</parameter></function>
      2. <tool_call>{"name": "...", "arguments": {...}}</tool_call>
      3. Bare JSON array: [{"name": "...", "arguments": {...}}]
    """
    if not content:
        return None

    # --- Format 1: <function=...> ---
    f1_matches = re.findall(r"<function=(\w+)>(.*?)</function>", content, re.DOTALL)
    if f1_matches:
        tool_calls = []
        for func_name, body in f1_matches:
            params = {}
            for param_name, param_value in re.findall(r"<parameter=(\w+)>(.*?)</parameter>", body, re.DOTALL):
                params[param_name] = param_value.strip()
            tool_calls.append({"name": func_name, "arguments": params})
        return tool_calls if tool_calls else None

    # --- Format 2: <tool_call>JSON</tool_call> ---
    f2_matches = re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", content, re.DOTALL)
    if f2_matches:
        tool_calls = []
        for raw_json in f2_matches:
            try:
                data = json.loads(raw_json)
                if isinstance(data, dict) and "name" in data:
                    tool_calls.append({
                        "name": data["name"],
                        "arguments": data.get("arguments", data.get("parameters", {})),
                    })
            except (json.JSONDecodeError, KeyError):
                continue
        return tool_calls if tool_calls else None

    # --- Format 3: bare JSON array (strip optional code fence) ---
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-z]*\n?", "", stripped).rstrip("`").strip()
    if stripped.startswith("["):
        try:
            data = json.loads(stripped)
            if isinstance(data, list):
                tool_calls = [
                    {"name": item["name"], "arguments": item.get("arguments", {})}
                    for item in data
                    if isinstance(item, dict) and "name" in item
                ]
                return tool_calls if tool_calls else None
        except (json.JSONDecodeError, KeyError):
            pass

    return None
```

**Step 4: Run all parsing tests**

```bash
pytest tests/unit/services/test_parse_text_tool_calls.py -v
```

Expected: all PASS

**Step 5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all PASS

**Step 6: Commit**

```bash
git add app/backapp/frontend/app/services/llm.py tests/unit/services/test_parse_text_tool_calls.py
git commit -m "fix: extend text tool call parsing to handle <tool_call> JSON and bare array formats"
```

---

### Task 7: Update PROGRESS.md

Document the new capability.

**Files:**
- Modify: `PROGRESS.md`

**Step 1: Add entries under Improvements**

Add a new section after Phase 5 in `PROGRESS.md`:

```markdown
#### Phase 5b — Tool infrastructure

- [x] **Tool registry:** File-based autodiscovery — add a tool by dropping a file into `app/backapp/frontend/app/tools/`
- [x] **Text tool call parsing:** Handle all three common local LLM text formats (`<function=...>`, `<tool_call>` JSON, bare JSON array)
- [x] **Tool migration:** All existing tools (retrieve_documents, query_documents_metadata, web_search, deep_analysis, graph_search) migrated to registry
```

**Step 2: Commit**

```bash
git add PROGRESS.md
git commit -m "docs: mark tool registry + text tool call parsing complete in PROGRESS.md"
```
