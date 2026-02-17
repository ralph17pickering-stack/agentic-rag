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
