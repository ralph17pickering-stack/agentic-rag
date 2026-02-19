"""GraphRAG retrieval: entity-neighbour expansion and global/relationship graph search."""
import logging
from langsmith import traceable
from app.config import settings
from app.services.supabase import get_supabase_client

logger = logging.getLogger(__name__)


@traceable(name="expand_with_entity_neighbors")
async def expand_with_entity_neighbors(
    chunk_ids: list[str],
    user_token: str,
    exclude_ids: set[str],
    top_k: int,
    user_id: str = "",
) -> list[dict]:
    """Expand retrieval results with chunks that share entities with the given chunks.

    Returns up to top_k new chunks (not in exclude_ids), each tagged with graph_expanded=True.
    """
    if not chunk_ids or not user_id:
        return []

    sb = get_supabase_client(user_token)

    try:
        # Step 1: find entities referenced by the given chunks
        entities_result = sb.rpc("get_entities_for_chunks", {
            "p_user_id": user_id,
            "p_chunk_ids": chunk_ids,
        }).execute()

        entity_ids = [r["entity_id"] for r in (entities_result.data or [])]
        if not entity_ids:
            return []

        # Step 2: find neighbour chunks via those entities
        neighbor_result = sb.rpc("get_entity_neighbor_chunks", {
            "p_user_id": user_id,
            "p_entity_ids": entity_ids,
            "p_limit": top_k + len(exclude_ids),
        }).execute()

        neighbor_chunk_ids = [
            str(r["chunk_id"]) for r in (neighbor_result.data or [])
            if str(r["chunk_id"]) not in exclude_ids
        ][:top_k]

        if not neighbor_chunk_ids:
            return []

        # Step 3: fetch chunk content
        chunks_result = sb.table("chunks").select(
            "id,content,document_id"
        ).in_("id", neighbor_chunk_ids).execute()

        # Enrich with document metadata
        doc_ids = list({r["document_id"] for r in chunks_result.data})
        docs_result = sb.table("documents").select(
            "id,title,document_date,topics"
        ).in_("id", doc_ids).execute()
        doc_map = {r["id"]: r for r in docs_result.data}

        extra = []
        for row in chunks_result.data:
            doc = doc_map.get(row["document_id"], {})
            extra.append({
                "id": row["id"],
                "content": row["content"],
                "document_id": row["document_id"],
                "doc_title": doc.get("title"),
                "doc_date": doc.get("document_date"),
                "doc_topics": doc.get("topics"),
                "graph_expanded": True,
                "rrf_score": 0.0,
            })

        return extra

    except Exception as e:
        logger.warning(f"Graph expansion failed: {e}")
        return []


@traceable(name="global_graph_search")
async def global_graph_search(user_token: str, top_n: int, user_id: str = "") -> str:
    """Return a structured summary of top communities for global/thematic queries."""
    if not user_id:
        return "No user context available."

    sb = get_supabase_client(user_token)

    try:
        result = sb.rpc("get_user_communities", {
            "p_user_id": user_id,
            "p_min_size": settings.graphrag_community_min_size,
        }).execute()

        communities = (result.data or [])[:top_n]
        if not communities:
            return "No communities found. The knowledge graph may still be building."

        lines = ["## Knowledge Graph Communities\n"]
        for i, c in enumerate(communities, 1):
            lines.append(f"### {i}. {c['title']} ({c['size']} entities)")
            lines.append(c["summary"])
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Global graph search failed: {e}")
        return f"Graph search encountered an error: {e}"


@traceable(name="relationship_graph_search")
async def relationship_graph_search(
    entity_a: str,
    entity_b: str,
    user_token: str,
    user_id: str = "",
) -> str:
    """Find and describe the path between two entities in the knowledge graph."""
    if not user_id:
        return "No user context available."

    sb = get_supabase_client(user_token)

    try:
        path_result = sb.rpc("find_entity_path", {
            "p_user_id": user_id,
            "p_source_lower": entity_a.lower().strip(),
            "p_target_lower": entity_b.lower().strip(),
        }).execute()

        path_nodes = path_result.data or []
        if not path_nodes:
            return (
                f"No relationship path found between '{entity_a}' and '{entity_b}' "
                "in the knowledge graph (within 4 hops)."
            )

        # Build a sorted path by hop distance
        sorted_nodes = sorted(path_nodes, key=lambda n: n.get("hop", 0))
        path_names = [n["entity_name"] for n in sorted_nodes]
        path_str = " → ".join(path_names)

        # Fetch representative chunks along the path entity IDs
        entity_ids = [n["entity_id"] for n in sorted_nodes]
        neighbor_result = sb.rpc("get_entity_neighbor_chunks", {
            "p_user_id": user_id,
            "p_entity_ids": entity_ids,
            "p_limit": 5,
        }).execute()

        chunk_ids = [str(r["chunk_id"]) for r in (neighbor_result.data or [])]
        excerpts = []
        if chunk_ids:
            chunks_result = sb.table("chunks").select("content").in_("id", chunk_ids).execute()
            excerpts = [r["content"] for r in chunks_result.data]

        lines = [f"## Relationship Path: {path_str}\n"]
        if excerpts:
            lines.append("### Relevant Excerpts\n")
            for i, excerpt in enumerate(excerpts, 1):
                lines.append(f"**Excerpt {i}:**\n{excerpt[:500]}\n")

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Relationship graph search failed: {e}")
        return f"Graph relationship search encountered an error: {e}"
