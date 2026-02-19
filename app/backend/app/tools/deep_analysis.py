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
