# Tag Enrichment Sweep — Design

_Date: 2026-02-23_

## Problem

The existing `tag_quality_sweep` removes bad tags from a random sample of documents every 12 hours. There is no mechanism to **add** new tags to existing documents via LLM. YAKE-only tags (set at ingestion) leave many documents under-tagged, making discovery by topic unreliable.

## Goals

1. Periodically enrich each document's `topics` with LLM-suggested tags beyond what YAKE extracted.
2. Prioritise under-tagged and least-recently-checked documents.
3. Run only when the app is idle (no user HTTP activity in the last 20 minutes).
4. Skip entirely if all documents have been checked within the last 60 days.
5. When a brand-new tag is discovered, propagate it across **all users' documents** where it is relevant (verified by LLM).

## Non-Goals

- Replacing the existing quality sweep (removal logic stays separate).
- Real-time tagging during ingestion (YAKE continues to handle that).

---

## Architecture

### New / modified files

| File | Change |
|---|---|
| `db/migrations/023_tag_enrichment.sql` | Add `last_tag_checked_at timestamptz` to `documents` |
| `app/backend/app/services/activity.py` | New — in-memory last-activity tracker |
| `app/backend/app/services/tag_enrichment_sweep.py` | New — enrichment loop |
| `app/backend/app/main.py` | Add activity middleware + new background loop |
| `app/backend/app/config.py` | New enrichment settings |

---

## Data Model

```sql
-- 023_tag_enrichment.sql
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS last_tag_checked_at timestamptz DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_last_tag_checked_at
  ON documents (last_tag_checked_at ASC NULLS FIRST);
```

`NULL` = never enriched (always highest priority). Set to `NOW()` after each enrichment run on a document.

---

## Idle Detection (`activity.py`)

```python
_last_activity: datetime = datetime.min  # never active at startup

def record_activity() -> None: ...
def is_idle(minutes: float) -> bool: ...
```

FastAPI middleware in `main.py` calls `record_activity()` on every HTTP request. Background coroutines call Python functions directly and never touch the HTTP stack, so they don't reset the idle timer.

---

## Sweep Logic (`tag_enrichment_sweep.py`)

Runs every 10 minutes. Per execution:

### Step 1 — Idle gate
```
if not is_idle(settings.tag_enrichment_idle_minutes):
    return  # user was active recently
```

### Step 2 — All-clear gate
Query for any document where:
```sql
last_tag_checked_at IS NULL
  OR last_tag_checked_at < NOW() - INTERVAL '{max_age_days} days'
```
If zero rows → entire corpus is fresh → skip run.

### Step 3 — Priority batch
```sql
SELECT id, user_id, title, summary, topics
FROM documents
WHERE last_tag_checked_at IS NULL
   OR last_tag_checked_at < NOW() - INTERVAL '{max_age_days} days'
ORDER BY array_length(topics, 1) ASC NULLS FIRST,
         last_tag_checked_at ASC NULLS FIRST
LIMIT {batch_size}
```
Default batch size: **3 documents per run**.

### Step 4 — LLM enrichment (per document)
Prompt includes: title, summary, existing tags, first ~1500 chars of content (concatenated from top chunks).

```
System: You are a document tag enricher. Given a document's metadata and
        content excerpt, suggest additional tags not already present.
        Tags must be 1–3 words, lowercase, domain/subject focused.
        Return JSON: {"new_tags": ["tag1", "tag2"]}
        Suggest 0–5 tags. Suggest 0 if already well-tagged.

User: Title: {title}
      Summary: {summary}
      Existing tags: {existing_topics}
      Content excerpt: {excerpt}
```

### Step 5 — Apply tags + update timestamp
Merge `new_tags` into `topics` (dedup). Update `last_tag_checked_at = NOW()`.

### Step 6 — Propagation (for each new tag)

1. **Novelty check** — query `documents` (service client, all users) for any row where `topics @> ARRAY[new_tag]`. If any exist → tag is already known → skip propagation for this tag.
2. **Corpus search** — use tsvector GIN index on `chunks` to find distinct `document_id`s where content matches the term (excluding the origin document).
3. **LLM verification** — for each matching document, call LLM:
   ```
   System: Is the tag "{new_tag}" relevant to this document?
           Reply JSON: {"relevant": true} or {"relevant": false}
   User: Title: {title}
         Summary: {summary}
   ```
4. **Apply** — if `relevant: true`, add `new_tag` to that document's `topics`.

---

## Config Additions

```python
tag_enrichment_sweep_enabled: bool = True
tag_enrichment_sweep_interval_minutes: float = 10
tag_enrichment_sweep_batch_size: int = 3
tag_enrichment_idle_minutes: float = 20
tag_enrichment_max_age_days: int = 60
```

---

## Volume / Cost Considerations

- 3 docs × 10 min = up to 18 LLM enrichment calls/hour (only when idle).
- Propagation LLM calls are bounded by chunk matches — could spike if a broad term is discovered. Acceptable since it only triggers for genuinely new tags and only when the app is idle.

---

## Validation Tests

1. With the server idle, manually set `last_tag_checked_at = NULL` on a document and trigger the sweep → document receives new tags and `last_tag_checked_at` is set.
2. Set all documents' `last_tag_checked_at` to within the last 60 days → sweep logs "all documents fresh, skipping" and makes no LLM calls.
3. Simulate user activity (HTTP request) within 20 minutes → sweep skips with "not idle" log message.
4. Manually inject a brand-new tag into a document's topics → confirm propagation check queries across all users and the LLM verification fires for each matching document.
