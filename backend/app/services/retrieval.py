from langsmith import traceable
from app.services.supabase import get_supabase_client
from app.services.embeddings import generate_embedding


@traceable(name="retrieve_chunks")
async def retrieve_chunks(
    query: str,
    user_token: str,
    top_k: int = 5,
    similarity_threshold: float = 0.3,
    date_from: str | None = None,
    date_to: str | None = None,
    recency_weight: float = 0.0,
) -> list[dict]:
    """Embed query and search for similar chunks via pgvector."""
    query_embedding = await generate_embedding(query)
    sb = get_supabase_client(user_token)
    params = {
        "query_embedding": query_embedding,
        "match_count": top_k,
        "match_threshold": similarity_threshold,
        "filter_date_from": date_from,
        "filter_date_to": date_to,
        "recency_weight": recency_weight,
    }
    result = sb.rpc("match_chunks", params).execute()
    return result.data
