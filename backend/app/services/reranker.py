import json
import logging

from langsmith import traceable
from pydantic import BaseModel

from app.services.llm import client
from app.config import settings

logger = logging.getLogger(__name__)


class ChunkRelevance(BaseModel):
    chunk_id: str
    relevance_score: float


class RerankResult(BaseModel):
    rankings: list[ChunkRelevance]


RERANK_PROMPT = """You are a relevance scoring system. Given a query and a list of text chunks, score each chunk's relevance to the query on a scale of 0.0 to 1.0.

Query: {query}

Chunks:
{chunks_text}

Return a JSON object with a "rankings" array. Each element must have "chunk_id" (the ID shown) and "relevance_score" (0.0 to 1.0).
Score 1.0 = perfectly relevant, 0.0 = completely irrelevant.

Return ONLY valid JSON, no other text."""


@traceable(name="rerank_chunks")
async def rerank_chunks(
    query: str,
    chunks: list[dict],
    top_n: int | None = None,
) -> list[dict]:
    """Rerank chunks using LLM-based relevance scoring.

    Returns chunks sorted by relevance_score, with rerank_score added to each.
    Falls back to original order (truncated) on failure.
    """
    top_n = top_n or settings.rerank_top_n
    if not chunks:
        return []

    # Build chunk text for prompt, truncating content to 500 chars
    chunks_text_parts = []
    for c in chunks:
        content = c.get("content", "")[:500]
        chunks_text_parts.append(f"[ID: {c['id']}]\n{content}")
    chunks_text = "\n\n".join(chunks_text_parts)

    prompt = RERANK_PROMPT.format(query=query, chunks_text=chunks_text)

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        result = RerankResult.model_validate(json.loads(raw))

        # Map scores back to chunks
        score_map = {r.chunk_id: r.relevance_score for r in result.rankings}
        for c in chunks:
            c["rerank_score"] = score_map.get(str(c["id"]), 0.0)

        chunks.sort(key=lambda c: c.get("rerank_score", 0.0), reverse=True)
        return chunks[:top_n]

    except Exception:
        logger.exception("Reranking failed, returning original order")
        return chunks[:top_n]
