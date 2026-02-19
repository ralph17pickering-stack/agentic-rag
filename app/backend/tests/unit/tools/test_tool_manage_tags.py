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
