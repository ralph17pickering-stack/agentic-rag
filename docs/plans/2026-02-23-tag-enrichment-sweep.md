# Tag Enrichment Sweep Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a background sweep that uses the LLM to discover and apply new tags to existing documents every 10 minutes, running only when the app is idle, and propagating brand-new tags across all users' documents after LLM verification.

**Architecture:** A new `activity.py` module tracks last HTTP request time in-memory; a new `tag_enrichment_sweep.py` service queries the lowest-priority documents (fewest tags, oldest check), enriches them via LLM, and propagates any genuinely new tags across the corpus. Wired into `main.py` alongside the existing quality sweep loop.

**Tech Stack:** Python 3.13, FastAPI middleware, Supabase Python client (service role), OpenAI-compatible async LLM client, Pydantic, pytest + pytest-asyncio

---

## Pre-flight

All commands run from `/home/ralph/rag/app/backend` with the venv active:
```bash
source venv/bin/activate
```

---

### Task 1: Database migration — add `last_tag_checked_at`

**Files:**
- Create: `db/migrations/023_tag_enrichment.sql`

**Step 1: Write the migration**

```sql
-- 023_tag_enrichment.sql
-- Adds last_tag_checked_at to documents for enrichment sweep priority queue.

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS last_tag_checked_at timestamptz DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_last_tag_checked_at
  ON documents (last_tag_checked_at ASC NULLS FIRST);
```

Save to `/home/ralph/rag/db/migrations/023_tag_enrichment.sql`.

**Step 2: Apply the migration**

Connect to Supabase (local Docker instance) and run the SQL:
```bash
# From project root
psql "$(grep SUPABASE_DB_URL /home/ralph/rag/app/backend/.env 2>/dev/null || echo 'postgresql://postgres:postgres@localhost:5432/postgres')" \
  -f /home/ralph/rag/db/migrations/023_tag_enrichment.sql
```

If the above env var isn't set, open the Supabase Studio SQL editor at http://localhost:54323 and paste the migration SQL directly.

**Step 3: Verify column exists**

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'documents'
  AND column_name = 'last_tag_checked_at';
```

Expected: one row with `timestamp with time zone`.

**Step 4: Commit**

```bash
git add /home/ralph/rag/db/migrations/023_tag_enrichment.sql
git commit -m "feat: add last_tag_checked_at column to documents"
```

---

### Task 2: Activity tracker (`services/activity.py`)

**Files:**
- Create: `app/backend/app/services/activity.py`
- Test: `app/backend/tests/unit/services/test_activity.py`

**Step 1: Write the failing tests**

Create `app/backend/tests/unit/services/test_activity.py`:

```python
from datetime import datetime, timezone, timedelta
import pytest


def test_is_idle_returns_true_when_never_active():
    import app.services.activity as act
    act._last_activity = datetime.min.replace(tzinfo=timezone.utc)
    assert act.is_idle(20) is True


def test_is_idle_returns_false_when_recently_active():
    import app.services.activity as act
    act._last_activity = datetime.now(timezone.utc)
    assert act.is_idle(20) is False


def test_is_idle_returns_true_after_window_passes():
    import app.services.activity as act
    act._last_activity = datetime.now(timezone.utc) - timedelta(minutes=21)
    assert act.is_idle(20) is True


def test_record_activity_updates_timestamp():
    import app.services.activity as act
    before = datetime.now(timezone.utc)
    act.record_activity()
    assert act._last_activity >= before
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/services/test_activity.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — module doesn't exist yet.

**Step 3: Write the implementation**

Create `app/backend/app/services/activity.py`:

```python
"""In-memory idle detection — tracks last HTTP request timestamp."""
from datetime import datetime, timezone, timedelta

_last_activity: datetime = datetime.min.replace(tzinfo=timezone.utc)


def record_activity() -> None:
    """Call on every incoming HTTP request."""
    global _last_activity
    _last_activity = datetime.now(timezone.utc)


def is_idle(minutes: float) -> bool:
    """Return True if no activity has been recorded in the last `minutes`."""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return _last_activity < threshold
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/services/test_activity.py -v
```

Expected: 4 passed.

**Step 5: Commit**

```bash
git add app/services/activity.py tests/unit/services/test_activity.py
git commit -m "feat: add in-memory activity tracker for idle detection"
```

---

### Task 3: Config additions

**Files:**
- Modify: `app/backend/app/config.py`
- Test: `app/backend/tests/unit/services/test_config_tag_settings.py` (append)

**Step 1: Read the existing config test to understand pattern**

Read `tests/unit/services/test_config_tag_settings.py` before editing.

**Step 2: Write the failing test (append to existing test file)**

Add to `tests/unit/services/test_config_tag_settings.py`:

```python
def test_enrichment_sweep_defaults():
    from app.config import Settings
    s = Settings()
    assert s.tag_enrichment_sweep_enabled is True
    assert s.tag_enrichment_sweep_interval_minutes == 10.0
    assert s.tag_enrichment_sweep_batch_size == 3
    assert s.tag_enrichment_idle_minutes == 20.0
    assert s.tag_enrichment_max_age_days == 60
```

**Step 3: Run test to verify it fails**

```bash
pytest tests/unit/services/test_config_tag_settings.py::test_enrichment_sweep_defaults -v
```

Expected: `AttributeError` — fields don't exist yet.

**Step 4: Add config fields**

In `app/backend/app/config.py`, add after the existing `tag_quality_auto_block_threshold` line:

```python
    tag_enrichment_sweep_enabled: bool = True
    tag_enrichment_sweep_interval_minutes: float = 10
    tag_enrichment_sweep_batch_size: int = 3
    tag_enrichment_idle_minutes: float = 20
    tag_enrichment_max_age_days: int = 60
```

**Step 5: Run test to verify it passes**

```bash
pytest tests/unit/services/test_config_tag_settings.py -v
```

Expected: all pass.

**Step 6: Commit**

```bash
git add app/config.py tests/unit/services/test_config_tag_settings.py
git commit -m "feat: add tag enrichment sweep config settings"
```

---

### Task 4: Tag enrichment sweep service

**Files:**
- Create: `app/backend/app/services/tag_enrichment_sweep.py`
- Test: `app/backend/tests/unit/services/test_tag_enrichment_sweep.py`

**Step 1: Write the failing tests**

Create `app/backend/tests/unit/services/test_tag_enrichment_sweep.py`:

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ── suggest_new_tags ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_suggest_new_tags_returns_list():
    from app.services.tag_enrichment_sweep import suggest_new_tags

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"new_tags": ["biodiversity", "carbon offset"]}'

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.tag_enrichment_sweep.client", mock_client):
        result = await suggest_new_tags(
            title="Forest Policy",
            summary="A review of forest carbon policies.",
            existing_tags=["climate", "policy"],
            excerpt="Forests absorb carbon and support biodiversity...",
        )

    assert "biodiversity" in result
    assert "carbon offset" in result
    # Must not repeat existing tags
    assert "climate" not in result
    assert "policy" not in result


@pytest.mark.asyncio
async def test_suggest_new_tags_returns_empty_on_llm_failure():
    from app.services.tag_enrichment_sweep import suggest_new_tags

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM down"))

    with patch("app.services.tag_enrichment_sweep.client", mock_client):
        result = await suggest_new_tags("T", "S", ["a"], "excerpt")

    assert result == []


# ── verify_tag_relevance ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_tag_relevance_returns_true():
    from app.services.tag_enrichment_sweep import verify_tag_relevance

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"relevant": true}'

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.tag_enrichment_sweep.client", mock_client):
        result = await verify_tag_relevance(
            tag="biodiversity",
            title="Forest Policy",
            summary="A review of forest carbon policies.",
        )

    assert result is True


@pytest.mark.asyncio
async def test_verify_tag_relevance_returns_false():
    from app.services.tag_enrichment_sweep import verify_tag_relevance

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"relevant": false}'

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.tag_enrichment_sweep.client", mock_client):
        result = await verify_tag_relevance("biodiversity", "Cooking", "A recipe book.")

    assert result is False


@pytest.mark.asyncio
async def test_verify_tag_relevance_returns_false_on_failure():
    from app.services.tag_enrichment_sweep import verify_tag_relevance

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM down"))

    with patch("app.services.tag_enrichment_sweep.client", mock_client):
        result = await verify_tag_relevance("tag", "T", "S")

    assert result is False


# ── enrich_batch ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enrich_batch_applies_new_tags_and_updates_timestamp():
    from app.services.tag_enrichment_sweep import enrich_batch

    doc = {
        "id": "doc-1",
        "user_id": "user-1",
        "title": "Forest Policy",
        "summary": "Carbon policy review.",
        "topics": ["policy"],
    }

    mock_sb = MagicMock()
    # chunks fetch
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"content": "Forests absorb carbon and support biodiversity."}
    ]
    # topics novelty check — tag not found anywhere
    mock_sb.table.return_value.select.return_value.filter.return_value.limit.return_value.execute.return_value.data = []
    # chunk search for propagation
    mock_sb.table.return_value.select.return_value.filter.return_value.execute.return_value.data = []
    # update call
    mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = None

    async def fake_suggest(title, summary, existing_tags, excerpt):
        return ["biodiversity"]

    async def fake_verify(tag, title, summary):
        return True

    with patch("app.services.tag_enrichment_sweep.get_service_supabase_client", return_value=mock_sb), \
         patch("app.services.tag_enrichment_sweep.suggest_new_tags", side_effect=fake_suggest), \
         patch("app.services.tag_enrichment_sweep.verify_tag_relevance", side_effect=fake_verify), \
         patch("app.services.tag_enrichment_sweep.settings") as mock_settings:
        mock_settings.tag_enrichment_max_age_days = 60

        result = await enrich_batch([doc])

    assert result["docs_enriched"] == 1
    assert "biodiversity" in result["new_tags_applied"]


# ── run_enrichment_sweep ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_enrichment_sweep_skips_when_not_idle():
    from app.services.tag_enrichment_sweep import run_enrichment_sweep

    with patch("app.services.tag_enrichment_sweep.is_idle", return_value=False):
        result = await run_enrichment_sweep()

    assert result == {"skipped": "not_idle"}


@pytest.mark.asyncio
async def test_run_enrichment_sweep_skips_when_all_fresh():
    from app.services.tag_enrichment_sweep import run_enrichment_sweep

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.or_.return_value.limit.return_value.execute.return_value.data = []

    with patch("app.services.tag_enrichment_sweep.is_idle", return_value=True), \
         patch("app.services.tag_enrichment_sweep.get_service_supabase_client", return_value=mock_sb):
        result = await run_enrichment_sweep()

    assert result == {"skipped": "all_fresh"}
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/services/test_tag_enrichment_sweep.py -v
```

Expected: `ImportError` — module doesn't exist.

**Step 3: Write the implementation**

Create `app/backend/app/services/tag_enrichment_sweep.py`:

```python
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
        .filter("topics", "cs", f'{{"{ tag }"}}'  )
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
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/services/test_tag_enrichment_sweep.py -v
```

Expected: all pass. Fix any import or mock errors before proceeding.

**Step 5: Commit**

```bash
git add app/services/tag_enrichment_sweep.py tests/unit/services/test_tag_enrichment_sweep.py
git commit -m "feat: add tag enrichment sweep service with LLM enrichment and propagation"
```

---

### Task 5: Wire into `main.py` (middleware + loop)

**Files:**
- Modify: `app/backend/app/main.py`
- Test: `app/backend/tests/unit/test_main_sweep_loop.py` (append)

**Step 1: Write the failing tests (append to existing file)**

Add to `tests/unit/test_main_sweep_loop.py`:

```python
def test_enrichment_loop_exists():
    from app.main import _tag_enrichment_sweep_loop
    assert callable(_tag_enrichment_sweep_loop)


def test_activity_middleware_records_on_request():
    """A real HTTP request to the app should update _last_activity."""
    import app.services.activity as act
    from datetime import datetime, timezone, timedelta
    from fastapi.testclient import TestClient
    from app.main import app

    # Set activity to old timestamp
    act._last_activity = datetime.now(timezone.utc) - timedelta(hours=1)
    before = act._last_activity

    client = TestClient(app)
    client.get("/health")

    assert act._last_activity > before
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_main_sweep_loop.py -v
```

Expected: `ImportError` for `_tag_enrichment_sweep_loop` and activity assertion fails.

**Step 3: Update `main.py`**

Add these imports at the top:
```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.services.activity import record_activity
from app.services.tag_enrichment_sweep import run_enrichment_sweep
```

Add the loop function (after `_tag_quality_sweep_loop`):
```python
async def _tag_enrichment_sweep_loop():
    interval = settings.tag_enrichment_sweep_interval_minutes * 60
    while True:
        await asyncio.sleep(interval)
        logger.info("Running periodic tag enrichment sweep")
        try:
            await run_enrichment_sweep()
        except Exception:
            logger.exception("Tag enrichment sweep loop error")
```

Add the middleware class (before or after the lifespan function):
```python
class ActivityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        record_activity()
        return await call_next(request)
```

In the `lifespan` function, add the enrichment loop task alongside existing ones:
```python
    if settings.tag_enrichment_sweep_enabled:
        asyncio.create_task(_tag_enrichment_sweep_loop())
```

After `app = FastAPI(...)`, add the middleware:
```python
app.add_middleware(ActivityMiddleware)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_main_sweep_loop.py -v
```

Expected: all pass.

**Step 5: Run full test suite to confirm no regressions**

```bash
pytest tests/ -v --ignore=tests/test_documents.py --ignore=tests/test_blocked_tags_api.py
```

(The integration tests in `test_documents.py` and `test_blocked_tags_api.py` require a live Supabase instance — skip them here.)

Expected: all unit tests pass.

**Step 6: Commit**

```bash
git add app/main.py tests/unit/test_main_sweep_loop.py
git commit -m "feat: wire tag enrichment sweep loop and activity middleware into main"
```

---

### Task 6: End-to-end smoke test

**Step 1: Start the backend**

```bash
uvicorn app.main:app --reload --port 8000
```

**Step 2: Check the health endpoint records activity**

```bash
curl http://localhost:8000/health
```

Then inspect logs — should NOT see "not_idle" skip for at least 20 minutes after any request.

**Step 3: Manually trigger the enrichment sweep**

Open a Python shell with the venv active:
```python
import asyncio
from app.services.tag_enrichment_sweep import run_enrichment_sweep
import app.services.activity as act
from datetime import datetime, timezone, timedelta

# Simulate idle: no activity for 21 minutes
act._last_activity = datetime.now(timezone.utc) - timedelta(minutes=21)

result = asyncio.run(run_enrichment_sweep())
print(result)
```

Expected: `{"docs_enriched": N, "new_tags_applied": [...], "propagated_to": M}` (or `{"skipped": "all_fresh"}` if all docs are already checked).

**Step 4: Verify `last_tag_checked_at` is set**

In Supabase Studio or psql:
```sql
SELECT id, title, array_length(topics, 1) AS tag_count, last_tag_checked_at
FROM documents
ORDER BY last_tag_checked_at DESC NULLS LAST
LIMIT 10;
```

Expected: recently processed documents have a non-null `last_tag_checked_at`.

**Step 5: Final commit**

```bash
git add -p  # stage only if any test/debug files were created
git commit -m "feat: tag enrichment sweep — complete implementation"
```

---

## Summary of all files touched

| File | Action |
|---|---|
| `db/migrations/023_tag_enrichment.sql` | New |
| `app/backend/app/services/activity.py` | New |
| `app/backend/app/services/tag_enrichment_sweep.py` | New |
| `app/backend/app/main.py` | Modified |
| `app/backend/app/config.py` | Modified |
| `app/backend/tests/unit/services/test_activity.py` | New |
| `app/backend/tests/unit/services/test_tag_enrichment_sweep.py` | New |
| `app/backend/tests/unit/services/test_config_tag_settings.py` | Modified (appended) |
| `app/backend/tests/unit/test_main_sweep_loop.py` | Modified (appended) |
