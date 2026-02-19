# Tag Quality Improvement Design

**Date:** 2026-02-19
**Complexity:** ⚠️ Medium

## Problem

YAKE keyword extraction produces tags that describe document structure (e.g., "communications plan", "executive summary", "key findings") rather than document content. At 500+ docs / 200+ tags, manual cleanup is unsustainable.

## Solution: Blocklist + Background LLM Quality Sweep

Two complementary systems:

1. **Tag blocklist** — user-controlled list of tags to suppress, with retroactive removal
2. **Background LLM sweep** — periodic task that samples documents and removes irrelevant tags, auto-adding frequently-removed tags to the blocklist

## Component 1: Tag Blocklist

### Database

New `blocked_tags` table:

| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK, default gen_random_uuid() |
| user_id | uuid | FK → auth.users, NOT NULL |
| tag | text | NOT NULL |
| created_at | timestamptz | default now() |

- Unique constraint on `(user_id, tag)`
- RLS: users only see/manage their own blocked tags

New RPC `block_tag(p_tag text)`:
- Inserts tag into `blocked_tags` (no-op if exists)
- Removes tag from all user's documents via `array_remove()`
- Returns count of documents updated

New RPC `unblock_tag(p_tag text)`:
- Deletes from `blocked_tags`
- Does NOT re-add the tag to documents (irreversible removal is fine)

### YAKE Changes

- Increase candidates: `top=5` → `top=15`
- After blocklist filtering, keep up to 8 tags
- Both values configurable in Settings:
  - `tag_candidates: int = 15`
  - `tag_max_per_document: int = 8`

### Ingestion Filter

In `_extract_topics()` (or at the callsite in ingestion), query the user's blocklist and strip matches before storing topics on the document.

### API Endpoints

- `POST /api/documents/blocked-tags` — block a tag (calls `block_tag` RPC)
  - Body: `{ "tag": "communications plan" }`
  - Response: `{ "tag": "communications plan", "documents_updated": 12 }`
- `GET /api/documents/blocked-tags` — list user's blocked tags
- `DELETE /api/documents/blocked-tags/{tag}` — unblock a tag

### UX: Edit Metadata Modal

Current tag chips have an X button to remove. Add a **ban icon** (lucide `Ban`) next to the X on each chip:

- **X** — removes tag from this document only (existing behavior)
- **Ban icon** — removes from all documents + adds to blocklist + prevents on future ingestion. Shows toast: "Blocked 'communications plan' — removed from 12 documents"

### UX: Document List Tag Pills

Tag pills in DocumentsPanel currently support left-click to filter. Add right-click context menu:

- **"Filter by tag"** — existing click behavior (also available here for discoverability)
- **"Block this tag"** — calls block endpoint, shows toast confirmation

## Component 2: Background LLM Tag Quality Sweep

### How It Works

1. Periodic background task runs every N hours (default: 12)
2. Picks one random user with documents per run
3. Samples ~10 random documents from that user
4. For each document, sends title + summary + current tags to LLM
5. LLM classifies each tag as **keep** or **remove**
6. Removed tags are deleted from documents
7. Tags removed from 3+ documents in a single sweep get auto-added to the user's blocklist

### Config

```python
tag_quality_sweep_enabled: bool = True
tag_quality_sweep_interval_hours: float = 12
tag_quality_sweep_sample_size: int = 10
tag_quality_auto_block_threshold: int = 3  # auto-block if removed from N+ docs in one sweep
```

### LLM Prompt

```
You are a document tag quality assessor.

Given a document's title, summary, and current tags, determine which tags are
relevant to the document's actual subject matter.

Remove tags that:
- Describe document structure (e.g., "executive summary", "key findings", "table of contents")
- Are template headings (e.g., "communications plan", "action items")
- Are too generic to be useful for categorization (e.g., "information", "document")

Return JSON: {"keep": ["tag1", "tag2"], "remove": ["tag3"]}
```

### Implementation

New file: `app/backend/app/services/tag_quality_sweep.py`

- `assess_tag_quality(title, summary, tags) -> dict` — single-doc LLM call
- `sweep_user(user_id) -> SweepResult` — sample + assess + update
- `sweep_random_user() -> None` — pick user, call sweep_user

### Integration

New background loop in `main.py` alongside existing consolidation and community rebuild loops. Same pattern: `asyncio.create_task(_tag_quality_sweep_loop())`.

### Relationship to Topic Consolidation

These are separate concerns:
- **Consolidation** merges duplicate tags ("ml" → "machine learning")
- **Quality sweep** removes irrelevant tags ("key findings" → deleted)

They run independently on different schedules.

## Data Flow Summary

```
Document ingested
  → YAKE extracts top 15 candidates
  → Filter against user's blocked_tags
  → Keep up to 8 tags
  → Store on document

Background (every 12h):
  → Pick random user
  → Sample 10 documents
  → LLM scores tag relevance
  → Remove bad tags
  → Auto-block tags removed 3+ times

User action (on-demand):
  → Block tag via edit modal (ban icon) or document list (right-click)
  → Immediate removal from all docs + added to blocklist
```
