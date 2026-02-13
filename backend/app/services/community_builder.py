"""GraphRAG community detection using NetworkX + LLM summarization."""
import logging
from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.services.supabase import get_service_supabase_client

logger = logging.getLogger(__name__)

_client = wrap_openai(
    AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )
)


class CommunitySummary(BaseModel):
    title: str
    summary: str


_COMMUNITY_PROMPT = """\
You are summarizing a cluster of related entities found in a document collection.

Entities in this cluster: {entity_names}

Representative text excerpts mentioning these entities:
{excerpts}

Write a concise title (5-10 words) and a 2-3 sentence summary describing what this cluster of entities represents and how they relate to each other.

Output ONLY valid JSON:
{{"title": "...", "summary": "..."}}
"""


@traceable(name="load_user_graph")
def _load_user_graph(sb, user_id: str):
    """Load all entities and relationships for a user into a NetworkX graph."""
    import networkx as nx

    entities_result = sb.table("entities").select("id,name,entity_type").eq("user_id", user_id).execute()
    relationships_result = sb.table("relationships").select("source_id,target_id,weight").eq("user_id", user_id).execute()

    G = nx.Graph()
    entity_info: dict[str, dict] = {}

    for e in entities_result.data:
        G.add_node(e["id"])
        entity_info[e["id"]] = {"name": e["name"], "entity_type": e["entity_type"]}

    for r in relationships_result.data:
        G.add_edge(r["source_id"], r["target_id"], weight=r.get("weight", 1.0))

    return G, entity_info


@traceable(name="detect_communities")
def _detect_communities(G, min_size: int) -> list[frozenset]:
    """Detect communities using greedy modularity, filter by min_size."""
    import networkx.algorithms.community as nx_comm

    if len(G.nodes) == 0:
        return []

    try:
        raw = nx_comm.greedy_modularity_communities(G, weight="weight")
        return [c for c in raw if len(c) >= min_size]
    except Exception as e:
        logger.warning(f"Community detection failed: {e}")
        return []


@traceable(name="fetch_representative_chunks")
def _fetch_representative_chunks(sb, user_id: str, entity_ids: list[str], limit: int) -> list[str]:
    """Fetch representative chunk texts for a community via entity-neighbour RPC."""
    if not entity_ids:
        return []
    try:
        neighbor_result = sb.rpc("get_entity_neighbor_chunks", {
            "p_user_id": user_id,
            "p_entity_ids": entity_ids,
            "p_limit": limit,
        }).execute()

        chunk_ids = [str(r["chunk_id"]) for r in (neighbor_result.data or [])]
        if not chunk_ids:
            return []

        chunks_result = sb.table("chunks").select("content").in_("id", chunk_ids).execute()
        return [r["content"] for r in chunks_result.data]
    except Exception as e:
        logger.warning(f"Failed to fetch representative chunks: {e}")
        return []


@traceable(name="summarize_community")
async def _summarize_community(entity_names: list[str], chunk_excerpts: list[str]) -> CommunitySummary:
    """Generate a title and summary for a community via LLM."""
    excerpts_text = "\n---\n".join(chunk_excerpts[:5]) if chunk_excerpts else "(no excerpts available)"
    prompt = _COMMUNITY_PROMPT.format(
        entity_names=", ".join(entity_names[:20]),
        excerpts=excerpts_text,
    )
    try:
        response = await _client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = response.choices[0].message.content or ""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()

        import json
        data = json.loads(raw)
        return CommunitySummary.model_validate(data)
    except (ValidationError, Exception) as e:
        logger.warning(f"Community summarization failed: {e}")
        names_preview = ", ".join(entity_names[:5])
        return CommunitySummary(
            title=f"Community: {names_preview[:50]}",
            summary=f"A cluster of {len(entity_names)} related entities including {names_preview}.",
        )


@traceable(name="build_communities_for_user")
async def build_communities_for_user(user_id: str) -> int:
    """Full pipeline: load graph → detect → summarize → replace communities.

    Returns the number of communities written.
    """
    sb = get_service_supabase_client()

    G, entity_info = _load_user_graph(sb, user_id)
    if len(G.nodes) == 0:
        logger.info(f"No entities for user {user_id}, skipping community build")
        return 0

    communities = _detect_communities(G, min_size=settings.graphrag_community_min_size)
    if not communities:
        logger.info(f"No communities detected for user {user_id}")
        return 0

    community_rows = []
    for community_nodes in communities:
        entity_ids = list(community_nodes)
        entity_names = [entity_info.get(eid, {}).get("name", eid) for eid in entity_ids]

        # Collect all document_ids for this community
        doc_ids_result = sb.table("entities").select("document_ids").in_("id", entity_ids).execute()
        all_doc_ids: set[str] = set()
        for row in doc_ids_result.data:
            for did in (row.get("document_ids") or []):
                all_doc_ids.add(str(did))

        excerpts = _fetch_representative_chunks(
            sb, user_id, entity_ids, settings.graphrag_community_chunks_per_summary
        )
        summary = await _summarize_community(entity_names, excerpts)

        community_rows.append({
            "user_id": user_id,
            "title": summary.title,
            "summary": summary.summary,
            "entity_ids": entity_ids,
            "document_ids": list(all_doc_ids),
            "size": len(entity_ids),
            "level": 0,
        })

    # Replace all communities for this user (communities are derived data)
    try:
        sb.table("communities").delete().eq("user_id", user_id).execute()
    except Exception as e:
        logger.warning(f"Failed to delete old communities for user {user_id}: {e}")

    if community_rows:
        sb.table("communities").insert(community_rows).execute()

    logger.info(f"Built {len(community_rows)} communities for user {user_id}")
    return len(community_rows)


@traceable(name="build_communities_for_all_users")
async def build_communities_for_all_users() -> None:
    """Rebuild communities for all users that have entities."""
    sb = get_service_supabase_client()
    try:
        result = sb.table("entities").select("user_id").execute()
        user_ids = list({r["user_id"] for r in result.data})
    except Exception as e:
        logger.error(f"Failed to fetch users with entities: {e}")
        return

    for user_id in user_ids:
        try:
            await build_communities_for_user(user_id)
        except Exception:
            logger.exception(f"Community rebuild failed for user {user_id}")
