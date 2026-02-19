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
