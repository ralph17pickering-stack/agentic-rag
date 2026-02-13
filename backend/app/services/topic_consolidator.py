import json
import logging

from pydantic import BaseModel
from langsmith import traceable

from app.services.llm import client
from app.services.supabase import get_service_supabase_client
from app.config import settings

logger = logging.getLogger(__name__)

CONSOLIDATION_PROMPT = """You are a topic tag normalizer.

Given a list of topic tags extracted from documents, identify groups of tags
that are semantically equivalent or nearly identical (e.g. "developer tools"
and "development tools" are the same concept; "ml" and "machine learning"
are the same concept).

For each group of equivalent tags, choose the best canonical form:
- lowercase
- clear and concise
- prefer the fuller, more descriptive form

Return JSON with a single key "mappings" whose value is an object mapping each
non-canonical tag to its canonical form. Omit tags that are already canonical
or have no near-duplicate.

Example output:
{"mappings": {"dev tools": "developer tools", "ml": "machine learning"}}

If no consolidation is needed, return: {"mappings": {}}"""


class TopicMappings(BaseModel):
    mappings: dict[str, str]


@traceable(name="get_topic_mappings")
async def get_topic_mappings(topics: list[str]) -> dict[str, str]:
    """Ask LLM to return {old_topic: canonical_topic} for near-duplicates."""
    if len(topics) < 2:
        return {}
    topic_list = json.dumps(topics)
    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": CONSOLIDATION_PROMPT},
                {"role": "user", "content": f"Topics: {topic_list}"},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        result = TopicMappings.model_validate_json(raw)
        return result.mappings
    except Exception:
        logger.warning("Topic mapping LLM call failed, skipping")
        return {}


@traceable(name="consolidate_topics_for_user")
async def consolidate_topics_for_user(user_id: str) -> int:
    """Consolidate near-duplicate topics for one user. Returns count of docs updated."""
    sb = get_service_supabase_client()

    result = sb.table("documents").select("id,topics").eq("user_id", user_id).execute()
    docs = result.data or []

    all_topics: set[str] = set()
    for doc in docs:
        for t in (doc.get("topics") or []):
            all_topics.add(t)

    if len(all_topics) < 2:
        return 0

    mappings = await get_topic_mappings(sorted(all_topics))
    if not mappings:
        return 0

    updated = 0
    for doc in docs:
        old_topics = doc.get("topics") or []
        new_topics = [mappings.get(t, t) for t in old_topics]
        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped = [t for t in new_topics if not (t in seen or seen.add(t))]
        if deduped != old_topics:
            sb.table("documents").update({"topics": deduped}).eq("id", doc["id"]).execute()
            updated += 1

    if updated:
        logger.info(
            f"Topic consolidation: updated {updated} docs for user {user_id}, mappings={mappings}"
        )
    return updated


async def consolidate_all_users() -> None:
    """Run topic consolidation for all users that have documents."""
    sb = get_service_supabase_client()
    result = sb.table("documents").select("user_id").execute()
    user_ids = list({row["user_id"] for row in (result.data or [])})
    for user_id in user_ids:
        try:
            await consolidate_topics_for_user(user_id)
        except Exception:
            logger.exception(f"Topic consolidation failed for user {user_id}")
