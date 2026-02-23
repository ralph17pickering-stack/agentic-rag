"""Background tag enrichment sweep — LLM-based tag discovery and propagation."""
import logging
from datetime import datetime, timezone

from pydantic import BaseModel
from langsmith import traceable

from app.services.llm import client
from app.services.supabase import get_service_supabase_client
from app.services.activity import is_idle
from app.config import settings

logger = logging.getLogger(__name__)

ENRICHMENT_PROMPT = """You are a document tag enricher.

Given a document's title, summary, existing tags, and a content excerpt, suggest
additional tags that describe the document's actual topic, domain, or subject matter.

Rules:
- Do NOT repeat any tag already in the existing tags list
- Tags must be 1–3 words, lowercase
- Focus on domain/subject, not document structure (no "introduction", "summary", etc.)
- Suggest 0–5 new tags; suggest 0 if the document is already well-tagged

Return JSON: {"new_tags": ["tag1", "tag2"]}"""

VERIFICATION_PROMPT = """You are a document tag relevance checker.

Given a candidate tag and a document's title and summary, decide if the tag is
relevant to this document's subject matter.

Return JSON: {"relevant": true} or {"relevant": false}"""


class NewTags(BaseModel):
    new_tags: list[str]


class Relevance(BaseModel):
    relevant: bool


@traceable(name="suggest_new_tags")
async def suggest_new_tags(
    title: str, summary: str, existing_tags: list[str], excerpt: str
) -> list[str]:
    """Ask LLM for additional tags not already on this document."""
    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": ENRICHMENT_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Title: {title}\n"
                        f"Summary: {summary}\n"
                        f"Existing tags: {existing_tags}\n"
                        f"Content excerpt:\n{excerpt}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        result = NewTags.model_validate_json(raw)
        # Filter out any that accidentally duplicate existing tags
        existing_lower = {t.lower() for t in existing_tags}
        return [t for t in result.new_tags if t.lower() not in existing_lower]
    except Exception:
        logger.warning("Tag enrichment LLM call failed, returning empty list")
        return []


@traceable(name="verify_tag_relevance")
async def verify_tag_relevance(tag: str, title: str, summary: str) -> bool:
    """Ask LLM whether `tag` is relevant to a document described by title/summary."""
    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": VERIFICATION_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Tag to evaluate: {tag}\n"
                        f"Title: {title}\n"
                        f"Summary: {summary}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        result = Relevance.model_validate_json(raw)
        return result.relevant
    except Exception:
        logger.warning("Tag relevance verification LLM call failed, defaulting to False")
        return False


def _get_chunk_excerpt(sb, doc_id: str, max_chars: int = 1500) -> str:
    """Fetch top chunks for a document and concatenate into an excerpt."""
    rows = (
        sb.table("chunks")
        .select("content")
        .eq("document_id", doc_id)
        .limit(3)
        .execute()
        .data
    ) or []
    combined = " ".join(r["content"] for r in rows)
    return combined[:max_chars]


async def _propagate_tag(sb, tag: str, origin_doc_id: str) -> int:
    """
    If `tag` is brand new (not in any document's topics), search all chunks for
    the term, then LLM-verify and apply to matching documents across all users.

    Returns number of documents the tag was propagated to.
    """
    # 1. Novelty check — tag must not exist in any document's topics
    existing = (
        sb.table("documents")
        .select("id")
        .filter("topics", "cs", f'{{"{tag}"}}')
        .limit(1)
        .execute()
        .data
    ) or []
    if existing:
        return 0  # tag already known, no propagation needed

    # 2. Corpus search via tsvector — find distinct documents containing the term
    #    (exclude the origin document which already has the tag)
    chunk_rows = (
        sb.table("chunks")
        .select("document_id")
        .filter("tsv", "fts", tag)
        .execute()
        .data
    ) or []

    candidate_ids = {
        r["document_id"]
        for r in chunk_rows
        if r["document_id"] != origin_doc_id
    }

    if not candidate_ids:
        return 0

    # 3. Fetch metadata for candidate documents
    docs = (
        sb.table("documents")
        .select("id, title, summary, topics")
        .in_("id", list(candidate_ids))
        .execute()
        .data
    ) or []

    propagated = 0
    for doc in docs:
        # Skip if already has this tag
        if tag in (doc.get("topics") or []):
            continue

        # LLM verification
        relevant = await verify_tag_relevance(
            tag=tag,
            title=doc.get("title") or "Untitled",
            summary=doc.get("summary") or "",
        )
        if not relevant:
            continue

        # Apply
        new_topics = list(doc.get("topics") or []) + [tag]
        sb.table("documents").update({"topics": new_topics}).eq("id", doc["id"]).execute()
        propagated += 1
        logger.info(f"Propagated tag '{tag}' to document {doc['id']}")

    return propagated


@traceable(name="enrich_batch")
async def enrich_batch(docs: list[dict]) -> dict:
    """Enrich a batch of documents with LLM-suggested tags and propagate new ones."""
    sb = get_service_supabase_client()
    docs_enriched = 0
    all_new_tags: list[str] = []
    total_propagated = 0

    for doc in docs:
        doc_id = doc["id"]
        existing_tags = doc.get("topics") or []
        excerpt = _get_chunk_excerpt(sb, doc_id)

        new_tags = await suggest_new_tags(
            title=doc.get("title") or "Untitled",
            summary=doc.get("summary") or "",
            existing_tags=existing_tags,
            excerpt=excerpt,
        )

        now_iso = datetime.now(timezone.utc).isoformat()

        if new_tags:
            merged = list(dict.fromkeys(existing_tags + new_tags))  # dedup, preserve order
            sb.table("documents").update(
                {"topics": merged, "last_tag_checked_at": now_iso}
            ).eq("id", doc_id).execute()
            docs_enriched += 1
            all_new_tags.extend(new_tags)
            logger.info(f"Enriched document {doc_id} with tags: {new_tags}")

            # Propagate brand-new tags across corpus
            for tag in new_tags:
                propagated = await _propagate_tag(sb, tag, origin_doc_id=doc_id)
                total_propagated += propagated
        else:
            # Still update the timestamp so this doc isn't re-checked immediately
            sb.table("documents").update(
                {"last_tag_checked_at": now_iso}
            ).eq("id", doc_id).execute()

    return {
        "docs_enriched": docs_enriched,
        "new_tags_applied": all_new_tags,
        "propagated_to": total_propagated,
    }


async def run_enrichment_sweep() -> dict:
    """
    Main entry point for the periodic enrichment loop.

    Guards:
    - Skips if the app has not been idle for tag_enrichment_idle_minutes.
    - Skips if all documents were checked within tag_enrichment_max_age_days.
    """
    if not is_idle(settings.tag_enrichment_idle_minutes):
        logger.debug("Tag enrichment sweep: app not idle, skipping")
        return {"skipped": "not_idle"}

    sb = get_service_supabase_client()
    max_age = settings.tag_enrichment_max_age_days

    # All-clear gate: are there any documents due for a check?
    stale = (
        sb.table("documents")
        .select("id")
        .or_(f"last_tag_checked_at.is.null,last_tag_checked_at.lt.now() - interval '{max_age} days'")
        .limit(1)
        .execute()
        .data
    ) or []

    if not stale:
        logger.debug("Tag enrichment sweep: all documents fresh, skipping")
        return {"skipped": "all_fresh"}

    # Priority batch: fewest tags first, then least recently checked
    batch_size = settings.tag_enrichment_sweep_batch_size
    rows = (
        sb.table("documents")
        .select("id, user_id, title, summary, topics")
        .or_(f"last_tag_checked_at.is.null,last_tag_checked_at.lt.now() - interval '{max_age} days'")
        .order("last_tag_checked_at", desc=False, nullsfirst=True)
        .limit(batch_size * 4)  # fetch extra, sort by tag count in Python
        .execute()
        .data
    ) or []

    # Sort by tag count ascending, then by last_tag_checked_at (already ordered by DB)
    rows.sort(key=lambda d: len(d.get("topics") or []))
    batch = rows[:batch_size]

    if not batch:
        return {"skipped": "no_docs"}

    result = await enrich_batch(batch)
    logger.info(f"Tag enrichment sweep complete: {result}")
    return result
