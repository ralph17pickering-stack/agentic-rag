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
