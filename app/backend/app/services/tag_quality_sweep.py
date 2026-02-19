"""Background tag quality sweep — LLM-based assessment of tag relevance."""
import logging
import json
import random
from collections import Counter

from pydantic import BaseModel
from langsmith import traceable

from app.services.llm import client
from app.services.supabase import get_service_supabase_client
from app.config import settings

logger = logging.getLogger(__name__)

QUALITY_PROMPT = """You are a document tag quality assessor.

Given a document's title, summary, and current tags, determine which tags are
relevant to the document's actual subject matter.

Remove tags that:
- Describe document structure (e.g., "executive summary", "key findings", "table of contents")
- Are template headings (e.g., "communications plan", "action items")
- Are too generic to be useful for categorization (e.g., "information", "document")

Keep tags that describe the document's actual topic, domain, or subject.

Return JSON: {"keep": ["tag1", "tag2"], "remove": ["tag3"]}"""


class TagAssessment(BaseModel):
    keep: list[str]
    remove: list[str]


@traceable(name="assess_tag_quality")
async def assess_tag_quality(
    title: str, summary: str, tags: list[str]
) -> dict[str, list[str]]:
    """Ask LLM to classify tags as keep or remove for a single document."""
    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": QUALITY_PROMPT},
                {
                    "role": "user",
                    "content": f"Title: {title}\nSummary: {summary}\nTags: {json.dumps(tags)}",
                },
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        result = TagAssessment.model_validate_json(raw)
        return {"keep": result.keep, "remove": result.remove}
    except Exception:
        logger.warning("Tag quality assessment LLM call failed, keeping all tags")
        return {"keep": tags, "remove": []}


@traceable(name="sweep_user")
async def sweep_user(user_id: str) -> dict:
    """Sample documents for a user, assess tag quality, remove bad tags."""
    sb = get_service_supabase_client()
    sample_size = settings.tag_quality_sweep_sample_size
    threshold = settings.tag_quality_auto_block_threshold

    result = sb.table("documents").select(
        "id, title, summary, topics"
    ).eq("user_id", user_id).execute()

    docs = [d for d in (result.data or []) if d.get("topics")]
    if not docs:
        return {"docs_updated": 0, "auto_blocked": []}

    sample = random.sample(docs, min(sample_size, len(docs)))

    removed_counter: Counter = Counter()
    docs_updated = 0

    for doc in sample:
        topics = doc["topics"]
        if not topics:
            continue

        assessment = await assess_tag_quality(
            title=doc.get("title") or "Untitled",
            summary=doc.get("summary") or "",
            tags=topics,
        )

        to_remove = assessment["remove"]
        if not to_remove:
            continue

        new_topics = [t for t in topics if t not in set(to_remove)]
        if new_topics != topics:
            sb.table("documents").update(
                {"topics": new_topics}
            ).eq("id", doc["id"]).execute()
            docs_updated += 1

        for tag in to_remove:
            removed_counter[tag] += 1

    auto_blocked = [
        tag for tag, count in removed_counter.items()
        if count >= threshold
    ]
    for tag in auto_blocked:
        try:
            sb.table("blocked_tags").insert(
                {"user_id": user_id, "tag": tag}
            ).execute()
        except Exception:
            pass

    if docs_updated or auto_blocked:
        logger.info(
            f"Tag quality sweep for user {user_id}: "
            f"updated {docs_updated} docs, auto-blocked {auto_blocked}"
        )

    return {"docs_updated": docs_updated, "auto_blocked": auto_blocked}


async def sweep_random_user() -> None:
    """Pick a random user with documents and run the tag quality sweep."""
    sb = get_service_supabase_client()
    result = sb.table("documents").select("user_id").execute()
    user_ids = list({row["user_id"] for row in (result.data or [])})
    if not user_ids:
        return

    user_id = random.choice(user_ids)
    try:
        await sweep_user(user_id)
    except Exception:
        logger.exception(f"Tag quality sweep failed for user {user_id}")
