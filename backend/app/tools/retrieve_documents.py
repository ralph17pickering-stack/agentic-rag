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
