import asyncio

from langsmith import traceable
from app.config import settings
from app.services.supabase import get_supabase_client
from app.services.embeddings import generate_embedding
from app.services.reranker import rerank_chunks


@traceable(name="semantic_search")
async def _semantic_search(
    query: str,
    user_token: str,
    match_count: int,
    similarity_threshold: float,
    date_from: str | None,
    date_to: str | None,
    recency_weight: float,
) -> list[dict]:
    """Vector similarity search via match_chunks RPC."""
    query_embedding = await generate_embedding(query)
    sb = get_supabase_client(user_token)
    result = sb.rpc("match_chunks", {
        "query_embedding": query_embedding,
        "match_count": match_count,
        "match_threshold": similarity_threshold,
        "filter_date_from": date_from,
        "filter_date_to": date_to,
        "recency_weight": recency_weight,
    }).execute()
    return result.data


@traceable(name="keyword_search")
async def _keyword_search(
    query: str,
    user_token: str,
    match_count: int,
    date_from: str | None,
    date_to: str | None,
) -> list[dict]:
    """Full-text keyword search via match_chunks_keyword RPC."""
    sb = get_supabase_client(user_token)
    result = sb.rpc("match_chunks_keyword", {
        "search_query": query,
        "match_count": match_count,
        "filter_date_from": date_from,
        "filter_date_to": date_to,
    }).execute()
    return result.data


def reciprocal_rank_fusion(
    result_lists: list[list[dict]],
    k: int = 60,
) -> list[dict]:
    """Merge multiple ranked result lists using RRF scoring.

    Each chunk gets score = sum(1 / (k + rank + 1)) across all lists it appears in.
    """
    scores: dict[str, float] = {}
    chunk_map: dict[str, dict] = {}

    for results in result_lists:
        for rank, chunk in enumerate(results):
            chunk_id = str(chunk["id"])
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
            if chunk_id not in chunk_map:
                chunk_map[chunk_id] = chunk

    # Attach RRF score and sort
    merged = []
    for chunk_id, score in scores.items():
        chunk = chunk_map[chunk_id]
        chunk["rrf_score"] = score
        merged.append(chunk)

    merged.sort(key=lambda c: c["rrf_score"], reverse=True)
    return merged


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
    """Hybrid retrieval pipeline: semantic + keyword search, RRF merge, optional rerank."""
    candidates = settings.retrieval_candidates
    mode = settings.search_mode

    if mode == "semantic":
        results = await _semantic_search(
            query, user_token, candidates, similarity_threshold,
            date_from, date_to, recency_weight,
        )
    elif mode == "keyword":
        results = await _keyword_search(
            query, user_token, candidates, date_from, date_to,
        )
    else:
        # hybrid: run both in parallel, merge with RRF
        semantic_results, keyword_results = await asyncio.gather(
            _semantic_search(
                query, user_token, candidates, similarity_threshold,
                date_from, date_to, recency_weight,
            ),
            _keyword_search(
                query, user_token, candidates, date_from, date_to,
            ),
        )
        results = reciprocal_rank_fusion(
            [semantic_results, keyword_results],
            k=settings.rrf_k,
        )

    # Optional LLM reranking
    if settings.rerank_enabled and results:
        results = await rerank_chunks(query, results, top_n=top_k)
    else:
        results = results[:top_k]

    return results
