# Phase 5 Plan B Design: Chunk Metadata Schema + Enrichment Pipeline

**Date:** 2026-02-17

## Goal

Add per-chunk enrichment (summary + keywords) generated inline during ingestion. Summaries are embedded and blended into retrieval scoring; keywords are stored in a separate table for cross-chunk lookup.

## Scope

- **In:** chunk summary, chunk keywords, summary embedding, keywords table, blended retrieval scoring
- **Out:** hypothetical questions (deferred), batch/parallel enrichment, enrichment backfill for existing chunks

## Schema

### Chunks table — two new columns

| Column | Type | Default |
|--------|------|---------|
| `summary` | `TEXT` | `NULL` |
| `summary_embedding` | `vector(2048)` | `NULL` |

### New `keywords` table

```sql
CREATE TABLE keywords (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_keywords_user_keyword ON keywords(user_id, keyword);
```

RLS: users see only their own keywords (same pattern as chunks).

### `match_chunks` RPC update

Blend `summary_embedding` into scoring when present:

```sql
score := CASE WHEN c.summary_embedding IS NOT NULL
    THEN (1 - (c.embedding <=> query_embedding)) * 0.7
       + (1 - (c.summary_embedding <=> query_embedding)) * 0.3
    ELSE (1 - (c.embedding <=> query_embedding))
END
```

Chunks without enrichment fall back to content-only scoring — no regression for existing data.

## Enrichment Service

New file: `app/backapp/frontend/app/services/chunk_enricher.py`

```python
class ChunkEnrichment(BaseModel):
    summary: str
    keywords: list[str]  # 3–5 items

async def enrich_chunk(content: str) -> ChunkEnrichment | None:
    ...
```

- Single LLM call per chunk (Approach A) — mirrors `extract_metadata` pattern
- Prompt: summarise in 1–2 sentences + list 3–5 keywords, respond in JSON
- Pydantic parses structured response
- Returns `None` on any failure (LLM error, parse error, timeout) — enrichment failure does not fail ingestion

## Ingestion Pipeline

After the chunk insert loop in `ingestion.py`, add an enrichment pass:

1. Collect returned chunk `id` values from the insert (change `.execute()` to `.execute().data`)
2. For each chunk: call `enrich_chunk(content)` → if `None`, skip silently
3. Call `generate_embeddings([enrichment.summary])` → `summary_embedding`
4. `UPDATE chunks SET summary=..., summary_embedding=... WHERE id=...`
5. `INSERT INTO keywords (chunk_id, user_id, keyword) VALUES ...` for each keyword

Enrichment failures are silently skipped — document still reaches `ready` status.

## Testing

| File | What |
|------|------|
| `tests/unit/services/test_chunk_enricher.py` | Mocked LLM → correct parse; malformed JSON → None; exception → None; keywords capped at 5 |
| `tests/unit/models/test_chunk_enrichment_model.py` | Valid parse; missing summary raises error; empty keywords valid |

## Files Changed

| File | Change |
|------|--------|
| `supabase/migrations/019_chunk_enrichment.sql` | summary + summary_embedding columns; keywords table + RLS; updated match_chunks RPC |
| `app/backapp/frontend/app/services/chunk_enricher.py` | New enrichment service |
| `app/backapp/frontend/app/services/ingestion.py` | Collect chunk IDs + enrichment pass |
| `tests/unit/services/test_chunk_enricher.py` | New |
| `tests/unit/models/test_chunk_enrichment_model.py` | New |
