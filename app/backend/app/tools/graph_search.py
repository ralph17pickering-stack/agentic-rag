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
