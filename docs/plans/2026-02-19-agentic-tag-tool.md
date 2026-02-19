# Agentic Tag Tool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `manage_tags` tool to the chat interface that lets users find and tag documents, delete tags, and merge/rename tags — all with a dry_run preview step before execution.

**Architecture:** A single tool file autodiscovered by the existing tool registry. The LLM passes identical parameters on both calls (dry_run=true for preview, dry_run=false for execute); the tool controls scope internally. Three write RPCs in the DB (SECURITY INVOKER, RLS-scoped) handle all mutations. No frontend changes required.

**Tech Stack:** Python/FastAPI, Supabase (PostgREST client + RPCs), existing `retrieve_chunks` retrieval pipeline, existing tool registry autodiscovery pattern.

---

## Task 1: DB Migration — Tag Management RPCs

**Files:**
- Create: `db/migrations/021_tag_management_rpcs.sql`

Apply this migration manually via Supabase Studio SQL editor (paste and run).

**Step 1: Create the migration file**

```sql
-- 021_tag_management_rpcs.sql
-- Tag management RPCs for the manage_tags tool.
-- All functions use SECURITY INVOKER so they run as the calling user
-- and inherit RLS — users can only affect their own documents.

-- Apply a tag to a list of documents (skips docs that already have it).
-- Returns the count of documents actually updated.
CREATE OR REPLACE FUNCTION apply_tag_to_docs(
    p_tag     text,
    p_doc_ids uuid[]
)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_count integer;
BEGIN
    UPDATE documents
    SET    topics = array_append(topics, p_tag)
    WHERE  id = ANY(p_doc_ids)
      AND  NOT (topics @> ARRAY[p_tag]);

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

-- Remove a tag from all of the calling user's documents that have it.
-- Returns the count of documents updated.
CREATE OR REPLACE FUNCTION delete_tag_from_docs(
    p_tag text
)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_count integer;
BEGIN
    UPDATE documents
    SET    topics = array_remove(topics, p_tag)
    WHERE  topics @> ARRAY[p_tag];

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

-- Rename a tag: remove p_from and add p_to on all docs that have p_from.
-- Skips docs that already have p_to to avoid duplicates.
-- Returns the count of documents updated.
CREATE OR REPLACE FUNCTION merge_tags(
    p_from text,
    p_to   text
)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_count integer;
BEGIN
    UPDATE documents
    SET    topics = array_append(array_remove(topics, p_from), p_to)
    WHERE  topics @> ARRAY[p_from]
      AND  NOT (topics @> ARRAY[p_to]);

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;
```

**Step 2: Apply the migration**

Open Supabase Studio → SQL Editor, paste the file contents, and run. Verify with:

```sql
SELECT routine_name FROM information_schema.routines
WHERE routine_name IN ('apply_tag_to_docs', 'delete_tag_from_docs', 'merge_tags');
-- Expected: 3 rows
```

**Step 3: Commit**

```bash
git add db/migrations/021_tag_management_rpcs.sql
git commit -m "feat: add tag management RPCs (apply_tag_to_docs, delete_tag_from_docs, merge_tags)"
```

---

## Task 2: Unit Tests for the Tool (write first, fail first)

**Files:**
- Create: `app/backend/tests/unit/tools/test_tool_manage_tags.py`

These tests mock out the Supabase client and `retrieve_chunks` — they test the tool logic only.

**Step 1: Write the failing tests**

```python
# app/backend/tests/unit/tools/test_tool_manage_tags.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.tools._registry import ToolContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(user_token="tok", user_id="uid-1", has_documents=True):
    return ToolContext(
        retrieve_fn=AsyncMock(return_value=[]),
        user_token=user_token,
        user_id=user_id,
        has_documents=has_documents,
    )


def make_chunks(doc_ids: list[str]) -> list[dict]:
    """Return minimal chunk dicts with the given document_ids."""
    return [
        {"id": f"chunk-{i}", "document_id": did, "content": "text", "rrf_score": 0.9}
        for i, did in enumerate(doc_ids)
    ]


# ---------------------------------------------------------------------------
# find_and_tag — dry_run=True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_and_tag_dry_run_shows_preview():
    from app.tools.manage_tags import plugin

    ctx = make_ctx()
    ctx.retrieve_fn = AsyncMock(return_value=make_chunks(["d1", "d2"]))

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"id": "d1", "title": "Doc One"},
        {"id": "d2", "title": "Doc Two"},
    ]

    with patch("app.tools.manage_tags.get_supabase_client", return_value=mock_sb):
        result = await plugin.handler(
            {"operation": "find_and_tag", "query": "climate", "tag_to_apply": "climate", "dry_run": True},
            ctx,
        )

    assert "Doc One" in result
    assert "Doc Two" in result
    assert "climate" in result
    assert "2" in result  # count
    # Must NOT call any RPC in dry_run
    mock_sb.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_find_and_tag_dry_run_no_results():
    from app.tools.manage_tags import plugin

    ctx = make_ctx()
    ctx.retrieve_fn = AsyncMock(return_value=[])

    with patch("app.tools.manage_tags.get_supabase_client"):
        result = await plugin.handler(
            {"operation": "find_and_tag", "query": "zzznothing", "tag_to_apply": "x", "dry_run": True},
            ctx,
        )

    assert "No documents found" in result


# ---------------------------------------------------------------------------
# find_and_tag — dry_run=False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_and_tag_execute_calls_rpc():
    from app.tools.manage_tags import plugin

    ctx = make_ctx()
    ctx.retrieve_fn = AsyncMock(return_value=make_chunks(["d1", "d2", "d3"]))

    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value.data = 3

    with patch("app.tools.manage_tags.get_supabase_client", return_value=mock_sb):
        result = await plugin.handler(
            {"operation": "find_and_tag", "query": "climate", "tag_to_apply": "climate", "dry_run": False},
            ctx,
        )

    mock_sb.rpc.assert_called_once()
    call_args = mock_sb.rpc.call_args
    assert call_args[0][0] == "apply_tag_to_docs"
    assert call_args[0][1]["p_tag"] == "climate"
    assert "Tagged" in result
    assert "climate" in result


# ---------------------------------------------------------------------------
# delete_tag — dry_run=True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_tag_dry_run_shows_preview():
    from app.tools.manage_tags import plugin

    ctx = make_ctx()
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.filter.return_value.execute.return_value.data = [
        {"id": "d1", "title": "Doc One"},
        {"id": "d2", "title": "Doc Two"},
    ]

    with patch("app.tools.manage_tags.get_supabase_client", return_value=mock_sb):
        result = await plugin.handler(
            {"operation": "delete_tag", "tag_to_delete": "enviroment", "dry_run": True},
            ctx,
        )

    assert "enviroment" in result
    assert "Doc One" in result
    mock_sb.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_delete_tag_dry_run_not_found():
    from app.tools.manage_tags import plugin

    ctx = make_ctx()
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.filter.return_value.execute.return_value.data = []

    with patch("app.tools.manage_tags.get_supabase_client", return_value=mock_sb):
        result = await plugin.handler(
            {"operation": "delete_tag", "tag_to_delete": "ghost", "dry_run": True},
            ctx,
        )

    assert "No documents" in result or "not found" in result.lower()


# ---------------------------------------------------------------------------
# delete_tag — dry_run=False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_tag_execute_calls_rpc():
    from app.tools.manage_tags import plugin

    ctx = make_ctx()
    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value.data = 2

    with patch("app.tools.manage_tags.get_supabase_client", return_value=mock_sb):
        result = await plugin.handler(
            {"operation": "delete_tag", "tag_to_delete": "oldtag", "dry_run": False},
            ctx,
        )

    mock_sb.rpc.assert_called_once()
    assert mock_sb.rpc.call_args[0][0] == "delete_tag_from_docs"
    assert "Removed" in result


# ---------------------------------------------------------------------------
# merge_tags — dry_run=True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_merge_tags_dry_run_shows_preview():
    from app.tools.manage_tags import plugin

    ctx = make_ctx()
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.filter.return_value.execute.return_value.data = [
        {"id": "d1", "title": "Doc One"},
    ]

    with patch("app.tools.manage_tags.get_supabase_client", return_value=mock_sb):
        result = await plugin.handler(
            {"operation": "merge_tags", "tag_from": "enviroment", "tag_to": "environment", "dry_run": True},
            ctx,
        )

    assert "enviroment" in result
    assert "environment" in result
    assert "Doc One" in result
    mock_sb.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_merge_tags_same_tag_error():
    from app.tools.manage_tags import plugin

    ctx = make_ctx()
    with patch("app.tools.manage_tags.get_supabase_client"):
        result = await plugin.handler(
            {"operation": "merge_tags", "tag_from": "foo", "tag_to": "foo", "dry_run": True},
            ctx,
        )

    assert "identical" in result.lower()


# ---------------------------------------------------------------------------
# merge_tags — dry_run=False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_merge_tags_execute_calls_rpc():
    from app.tools.manage_tags import plugin

    ctx = make_ctx()
    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value.data = 5

    with patch("app.tools.manage_tags.get_supabase_client", return_value=mock_sb):
        result = await plugin.handler(
            {"operation": "merge_tags", "tag_from": "enviroment", "tag_to": "environment", "dry_run": False},
            ctx,
        )

    mock_sb.rpc.assert_called_once()
    assert mock_sb.rpc.call_args[0][0] == "merge_tags"
    assert "Renamed" in result or "renamed" in result.lower()


# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------

def test_plugin_is_always_enabled():
    from app.tools.manage_tags import plugin
    assert plugin.enabled(make_ctx(has_documents=True)) is True
    assert plugin.enabled(make_ctx(has_documents=False)) is True


def test_plugin_definition_name():
    from app.tools.manage_tags import plugin
    assert plugin.definition["function"]["name"] == "manage_tags"
```

**Step 2: Run tests — verify they all FAIL**

```bash
cd /home/ralph/rag/app && source backend/venv/bin/activate && \
  pytest backend/tests/unit/tools/test_tool_manage_tags.py -v 2>&1 | head -40
```

Expected: `ImportError` or `ModuleNotFoundError` — `manage_tags` doesn't exist yet.

**Step 3: Commit the tests**

```bash
git add backend/tests/unit/tools/test_tool_manage_tags.py
git commit -m "test: add failing tests for manage_tags tool"
```

---

## Task 3: Implement the `manage_tags` Tool

**Files:**
- Create: `app/backend/app/tools/manage_tags.py`

**Step 1: Write the implementation**

```python
"""manage_tags tool — find/tag, delete, and merge tags on user documents."""
from app.tools._registry import ToolContext, ToolPlugin
from app.services.supabase import get_supabase_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PREVIEW_TOP_K = 10        # chunks to fetch for dry_run sample
_EXECUTE_TOP_K = 10_000    # effectively unlimited for execute


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dedup_docs(chunks: list[dict]) -> list[str]:
    """Return unique document_ids preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for c in chunks:
        did = str(c["document_id"])
        if did not in seen:
            seen.add(did)
            out.append(did)
    return out


def _fetch_titles(doc_ids: list[str], user_token: str) -> dict[str, str]:
    """Return {doc_id: title} for the given IDs."""
    if not doc_ids:
        return {}
    sb = get_supabase_client(user_token)
    rows = sb.table("documents").select("id, title").in_("id", doc_ids).execute().data
    return {str(r["id"]): (r.get("title") or "Untitled") for r in rows}


def _format_sample(titles: dict[str, str], max_show: int = 5) -> str:
    """Return a bulleted sample list."""
    names = list(titles.values())
    shown = names[:max_show]
    lines = "\n".join(f"  • {t}" for t in shown)
    extra = f"\n  … and {len(names) - max_show} more" if len(names) > max_show else ""
    return lines + extra


def _docs_with_tag(tag: str, user_token: str) -> list[dict]:
    """Return all user documents containing the given tag."""
    sb = get_supabase_client(user_token)
    return sb.table("documents").select("id, title").filter(
        "topics", "cs", f'{{"{tag}"}}'
    ).execute().data


# ---------------------------------------------------------------------------
# Operation handlers
# ---------------------------------------------------------------------------

async def _find_and_tag(args: dict, ctx: ToolContext) -> str:
    query = args.get("query", "").strip()
    tag = args.get("tag_to_apply", "").strip()
    dry_run = args.get("dry_run", True)

    if not query:
        return "Missing required parameter: query"
    if not tag:
        return "Missing required parameter: tag_to_apply"

    top_k = _PREVIEW_TOP_K if dry_run else _EXECUTE_TOP_K
    chunks = await ctx.retrieve_fn(query, top_k=top_k)
    doc_ids = _dedup_docs(chunks)

    if not doc_ids:
        return f"No documents found matching '{query}'. Try a broader search term."

    if dry_run:
        titles = _fetch_titles(doc_ids, ctx.user_token)
        sample = _format_sample(titles)
        return (
            f"Found {len(doc_ids)} document(s) matching '{query}':\n{sample}\n\n"
            f"Would apply tag '{tag}' to all matching documents. Shall I proceed?"
        )

    # Execute: call RPC
    sb = get_supabase_client(ctx.user_token)
    result = sb.rpc("apply_tag_to_docs", {"p_tag": tag, "p_doc_ids": doc_ids}).execute()
    affected = result.data or len(doc_ids)
    skipped = len(doc_ids) - (affected if isinstance(affected, int) else len(doc_ids))
    msg = f"Tagged {affected} document(s) with '{tag}'."
    if skipped > 0:
        msg += f" ({skipped} already had this tag.)"
    return msg


async def _delete_tag(args: dict, ctx: ToolContext) -> str:
    tag = args.get("tag_to_delete", "").strip()
    dry_run = args.get("dry_run", True)

    if not tag:
        return "Missing required parameter: tag_to_delete"

    docs = _docs_with_tag(tag, ctx.user_token)

    if not docs:
        return f"No documents have the tag '{tag}'."

    titles = {str(d["id"]): (d.get("title") or "Untitled") for d in docs}

    if dry_run:
        sample = _format_sample(titles)
        return (
            f"Tag '{tag}' appears on {len(docs)} document(s):\n{sample}\n\n"
            f"Would remove it from all. Shall I proceed?"
        )

    sb = get_supabase_client(ctx.user_token)
    result = sb.rpc("delete_tag_from_docs", {"p_tag": tag}).execute()
    affected = result.data if isinstance(result.data, int) else len(docs)
    return f"Removed tag '{tag}' from {affected} document(s)."


async def _merge_tags(args: dict, ctx: ToolContext) -> str:
    tag_from = args.get("tag_from", "").strip()
    tag_to = args.get("tag_to", "").strip()
    dry_run = args.get("dry_run", True)

    if not tag_from:
        return "Missing required parameter: tag_from"
    if not tag_to:
        return "Missing required parameter: tag_to"
    if tag_from == tag_to:
        return "Source and target tags are identical."

    docs = _docs_with_tag(tag_from, ctx.user_token)

    if not docs:
        return f"No documents have the tag '{tag_from}'."

    titles = {str(d["id"]): (d.get("title") or "Untitled") for d in docs}

    if dry_run:
        sample = _format_sample(titles)
        return (
            f"Would rename '{tag_from}' → '{tag_to}' on {len(docs)} document(s):\n{sample}\n\n"
            f"Shall I proceed?"
        )

    sb = get_supabase_client(ctx.user_token)
    result = sb.rpc("merge_tags", {"p_from": tag_from, "p_to": tag_to}).execute()
    affected = result.data if isinstance(result.data, int) else len(docs)
    return f"Renamed tag '{tag_from}' → '{tag_to}' on {affected} document(s)."


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_OPERATIONS = {
    "find_and_tag": _find_and_tag,
    "delete_tag": _delete_tag,
    "merge_tags": _merge_tags,
}


async def _handler(args: dict, ctx: ToolContext, on_status=None) -> str:
    operation = args.get("operation", "").strip()
    fn = _OPERATIONS.get(operation)
    if fn is None:
        ops = ", ".join(_OPERATIONS)
        return f"Unknown operation '{operation}'. Valid operations: {ops}"
    try:
        return await fn(args, ctx)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("manage_tags error")
        return f"Tag operation failed. No changes were made. ({exc})"


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

_DEFINITION = {
    "type": "function",
    "function": {
        "name": "manage_tags",
        "description": (
            "Find documents by semantic+keyword search and apply a tag, "
            "delete a tag from all documents that have it, or rename/merge a tag across all documents. "
            "ALWAYS call with dry_run=true first to show the user a preview of what will change, "
            "then ask for confirmation before calling with dry_run=false to execute."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["find_and_tag", "delete_tag", "merge_tags"],
                    "description": "The tag operation to perform.",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "true = preview only (no changes), false = execute. Default: true.",
                },
                "query": {
                    "type": "string",
                    "description": "[find_and_tag] Semantic+keyword search query to find documents.",
                },
                "tag_to_apply": {
                    "type": "string",
                    "description": "[find_and_tag] Tag to apply to all matching documents.",
                },
                "tag_to_delete": {
                    "type": "string",
                    "description": "[delete_tag] Tag to remove from all documents that have it.",
                },
                "tag_from": {
                    "type": "string",
                    "description": "[merge_tags] Existing tag to rename.",
                },
                "tag_to": {
                    "type": "string",
                    "description": "[merge_tags] New tag name to replace tag_from.",
                },
            },
            "required": ["operation"],
        },
    },
}

plugin = ToolPlugin(
    definition=_DEFINITION,
    handler=_handler,
    enabled=lambda ctx: True,  # available regardless of whether docs exist
)
```

**Step 2: Run the tests — all should pass**

```bash
cd /home/ralph/rag/app && source backend/venv/bin/activate && \
  pytest backend/tests/unit/tools/test_tool_manage_tags.py -v
```

Expected: all green.

**Step 3: Confirm the tool is autodiscovered**

```bash
cd /home/ralph/rag/app && source backend/venv/bin/activate && \
  python -c "from app.tools._registry import _plugins; print(list(_plugins.keys()))"
```

Expected: `manage_tags` appears in the list.

**Step 4: Commit**

```bash
git add backend/app/tools/manage_tags.py
git commit -m "feat: add manage_tags tool (find_and_tag, delete_tag, merge_tags)"
```

---

## Task 4: Wire retrieve_fn to pass top_k

**Problem:** `ctx.retrieve_fn` is a bound partial — it doesn't expose `top_k` by default. The tool calls `ctx.retrieve_fn(query, top_k=...)` but we need to confirm the retrieve_fn signature accepts `top_k`.

**Files:**
- Read: `app/backend/app/routers/chat.py` (find where ToolContext is constructed)

**Step 1: Check how retrieve_fn is set up**

```bash
cd /home/ralph/rag/app && grep -n "retrieve_fn" backend/app/routers/chat.py | head -20
```

**Step 2: Inspect the ToolContext construction in chat.py**

Look for something like:
```python
ctx = ToolContext(
    retrieve_fn=lambda q, **kw: retrieve_chunks(q, user_token, **kw),
    ...
)
```

If `top_k` is hardcoded in that lambda (e.g. `top_k=settings.top_k`), update it to pass `top_k` through:

```python
retrieve_fn=lambda q, **kw: retrieve_chunks(q, user_token, **kw),
```

This already works if `top_k` is not pinned. Check and confirm. If it IS pinned, remove the pin.

**Step 3: Run full tool tests to confirm no regression**

```bash
cd /home/ralph/rag/app && source backend/venv/bin/activate && \
  pytest backend/tests/unit/tools/ -v
```

Expected: all green.

**Step 4: Commit if a change was needed**

```bash
git add backend/app/routers/chat.py
git commit -m "fix: allow retrieve_fn to accept top_k kwarg for manage_tags"
```

---

## Task 5: Manual Integration Test

Start the backend (if not already running):

```bash
cd /home/ralph/rag/app && source backend/venv/bin/activate && \
  uvicorn backend.app.main:app --port 8000 --reload
```

Open the chat UI and run these prompts in order:

**Test 1 — find_and_tag dry_run:**
> "Find all documents about climate and tag them 'climate'"

Expected: LLM calls `manage_tags` with `dry_run=true`, shows list of matching docs and proposed tag, asks for confirmation.

**Test 2 — find_and_tag execute:**
> "Yes, go ahead"

Expected: LLM calls `manage_tags` with `dry_run=false`, reports "Tagged N documents with 'climate'."

Verify in Supabase Studio:
```sql
SELECT id, title, topics FROM documents WHERE topics @> ARRAY['climate'];
```

**Test 3 — delete_tag:**
> "Delete the tag 'climate' from all documents"

Expected: dry_run preview → confirm → tag removed. Verify in Studio.

**Test 4 — merge_tags:**
> "Rename the tag 'ai' to 'artificial-intelligence' across all documents"

Expected: preview shows affected docs → confirm → renamed. Verify in Studio.

---

## Task 6: Update PROGRESS.md

**Files:**
- Modify: `PROGRESS.md`

Change:
```
- [ ] **Agentic tag tool** AI tool calls through the chat interface to permit deleting tags, searching for docs matching key words and applying tags
```
To:
```
- [x] **Agentic tag tool** AI tool calls through the chat interface to permit deleting tags, searching for docs matching key words and applying tags
```

**Commit:**

```bash
git add PROGRESS.md
git commit -m "chore: mark agentic tag tool as complete"
```
