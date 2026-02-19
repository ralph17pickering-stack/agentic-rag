import json
import logging

from langsmith import traceable
from pydantic import BaseModel

from app.config import settings
from app.services.llm import client

logger = logging.getLogger(__name__)


class SubQueryList(BaseModel):
    queries: list[str]


QUERY_EXPANSION_PROMPT = """Generate {count} alternative search queries for the following question.
Each alternative should represent a different angle or phrasing of the original.
Do not repeat the original query.

Original query: {query}

Return a JSON object with a "queries" key containing an array of exactly {count} strings.
Return ONLY valid JSON, no other text."""


@traceable(name="generate_sub_queries")
async def generate_sub_queries(query: str, count: int) -> list[str]:
    """Generate `count` alternative sub-queries via LLM.

    Returns the alternatives only — caller prepends the original.
    Falls back to [] on any failure so retrieval degrades gracefully.
    """
    prompt = QUERY_EXPANSION_PROMPT.format(count=count, query=query)
    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        result = SubQueryList.model_validate(json.loads(raw))
        return result.queries[:count]
    except Exception:
        logger.exception("Sub-query generation failed, falling back to original query only")
        return []
