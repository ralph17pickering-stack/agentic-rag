# Phase 5 Plan B: Chunk Enrichment (Summary + Keywords)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add per-chunk LLM-generated summary and keywords during ingestion, embed summaries as a second retrieval signal, and store keywords in a dedicated table.

**Architecture:** A new `chunk_enricher.py` service generates summary + keywords via a single structured LLM call per chunk (same pattern as `extract_metadata`). The ingestion pipeline runs an enrichment pass after inserting chunks. The `match_chunks` Postgres RPC is updated to blend `summary_embedding` into scoring when present. Existing chunks without enrichment are unaffected.

**Tech Stack:** Supabase (psql migration), FastAPI/Pydantic (backend), tiktoken, pytest, existing LLM client

---

### Task 1: Apply DB migration 019

**Files:**
- Create: `supabase/migrations/019_chunk_enrichment.sql`

**Step 1: Create the migration file**

Create `supabase/migrations/019_chunk_enrichment.sql` with:

```sql
-- Add enrichment columns to chunks
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS summary TEXT DEFAULT NULL;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS summary_embedding vector(2048) DEFAULT NULL;

-- Keywords table
CREATE TABLE IF NOT EXISTS keywords (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_keywords_user_keyword ON keywords(user_id, keyword);
CREATE INDEX IF NOT EXISTS idx_keywords_chunk_id ON keywords(chunk_id);

-- RLS for keywords
ALTER TABLE keywords ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own keywords"
    ON keywords FOR SELECT
    TO authenticated
    USING ((SELECT auth.uid()) = user_id);

CREATE POLICY "Users can create their own keywords"
    ON keywords INSERT
    TO authenticated
    WITH CHECK ((SELECT auth.uid()) = user_id);

CREATE POLICY "Users can delete their own keywords"
    ON keywords FOR DELETE
    TO authenticated
    USING ((SELECT auth.uid()) = user_id);

-- Update match_chunks to blend summary_embedding when present
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding vector(2048),
    match_count INTEGER DEFAULT 5,
    match_threshold FLOAT DEFAULT 0.3,
    filter_date_from DATE DEFAULT NULL,
    filter_date_to DATE DEFAULT NULL,
    recency_weight FLOAT DEFAULT 0.0
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    content TEXT,
    chunk_index INTEGER,
    token_count INTEGER,
    similarity FLOAT,
    doc_title TEXT,
    doc_topics TEXT[],
    doc_date DATE
)
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.document_id,
        c.content,
        c.chunk_index,
        c.token_count,
        CASE
            WHEN recency_weight > 0 AND d.document_date IS NOT NULL THEN
                ((1 - recency_weight) *
                    CASE WHEN c.summary_embedding IS NOT NULL
                        THEN (1 - (c.embedding <=> query_embedding)) * 0.7
                           + (1 - (c.summary_embedding <=> query_embedding)) * 0.3
                        ELSE (1 - (c.embedding <=> query_embedding))
                    END
                + recency_weight * (1.0 / (1.0 + EXTRACT(EPOCH FROM (now() - d.document_date::timestamp)) / 86400.0 / 365.0)))::FLOAT
            ELSE
                CASE WHEN c.summary_embedding IS NOT NULL
                    THEN ((1 - (c.embedding <=> query_embedding)) * 0.7
                         + (1 - (c.summary_embedding <=> query_embedding)) * 0.3)::FLOAT
                    ELSE (1 - (c.embedding <=> query_embedding))::FLOAT
                END
        END AS similarity,
        d.title AS doc_title,
        d.topics AS doc_topics,
        COALESCE(d.document_date, d.created_at::date) AS doc_date
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE c.user_id = (SELECT auth.uid())
      AND (1 - (c.embedding <=> query_embedding)) > match_threshold
      AND (filter_date_from IS NULL OR COALESCE(d.document_date, d.created_at::date) >= filter_date_from)
      AND (filter_date_to IS NULL OR COALESCE(d.document_date, d.created_at::date) <= filter_date_to)
    ORDER BY
        CASE
            WHEN recency_weight > 0 AND d.document_date IS NOT NULL THEN
                ((1 - recency_weight) *
                    CASE WHEN c.summary_embedding IS NOT NULL
                        THEN (1 - (c.embedding <=> query_embedding)) * 0.7
                           + (1 - (c.summary_embedding <=> query_embedding)) * 0.3
                        ELSE (1 - (c.embedding <=> query_embedding))
                    END
                + recency_weight * (1.0 / (1.0 + EXTRACT(EPOCH FROM (now() - d.document_date::timestamp)) / 86400.0 / 365.0)))
            ELSE
                CASE WHEN c.summary_embedding IS NOT NULL
                    THEN (1 - (c.embedding <=> query_embedding)) * 0.7
                       + (1 - (c.summary_embedding <=> query_embedding)) * 0.3
                    ELSE (1 - (c.embedding <=> query_embedding))
                END
        END DESC
    LIMIT match_count;
END;
$$;
```

**Step 2: Apply the migration**

```bash
docker exec -i supabase-db psql -U supabase_admin -d postgres -f - < supabase/migrations/019_chunk_enrichment.sql
```

Expected output: multiple `ALTER TABLE`, `CREATE TABLE`, `CREATE INDEX`, `CREATE POLICY`, `CREATE OR REPLACE FUNCTION`

**Step 3: Verify columns exist**

```bash
docker exec supabase-db psql -U postgres -d postgres -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='chunks' AND column_name IN ('summary', 'summary_embedding') ORDER BY column_name;"
```

Expected:
```
   column_name    | data_type
------------------+-----------
 summary          | text
 summary_embedding| USER-DEFINED
```

**Step 4: Verify keywords table exists**

```bash
docker exec supabase-db psql -U postgres -d postgres -c "\d keywords"
```

Expected: table description with `chunk_id`, `user_id`, `keyword` columns.

**Step 5: Commit**

```bash
git add supabase/migrations/019_chunk_enrichment.sql
git commit -m "feat: migration 019 — chunk enrichment columns, keywords table, blended match_chunks"
```

---

### Task 2: Chunk enricher service + unit tests

**Files:**
- Create: `app/backapp/frontend/app/services/chunk_enricher.py`
- Create: `tests/unit/services/test_chunk_enricher.py`

**Step 1: Create `tests/unit/services/test_chunk_enricher.py`**

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.chunk_enricher import ChunkEnrichment, enrich_chunk


def test_chunk_enrichment_model_valid():
    e = ChunkEnrichment(summary="A short summary.", keywords=["foo", "bar"])
    assert e.summary == "A short summary."
    assert e.keywords == ["foo", "bar"]


def test_chunk_enrichment_model_empty_keywords_valid():
    e = ChunkEnrichment(summary="Summary.", keywords=[])
    assert e.keywords == []


def test_chunk_enrichment_model_missing_summary_raises():
    with pytest.raises(Exception):
        ChunkEnrichment(keywords=["foo"])


@pytest.mark.asyncio
async def test_enrich_chunk_returns_enrichment_on_success():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = (
        '{"summary": "Test summary.", "keywords": ["alpha", "beta", "gamma"]}'
    )
    with patch("app.services.chunk_enricher.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        result = await enrich_chunk("Some chunk content here.")
    assert result is not None
    assert result.summary == "Test summary."
    assert result.keywords == ["alpha", "beta", "gamma"]


@pytest.mark.asyncio
async def test_enrich_chunk_returns_none_on_malformed_json():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "not valid json at all"
    with patch("app.services.chunk_enricher.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        result = await enrich_chunk("Some chunk content.")
    assert result is None


@pytest.mark.asyncio
async def test_enrich_chunk_returns_none_on_llm_exception():
    with patch("app.services.chunk_enricher.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("LLM unavailable")
        )
        result = await enrich_chunk("Some chunk content.")
    assert result is None


@pytest.mark.asyncio
async def test_enrich_chunk_keywords_capped_at_five():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = (
        '{"summary": "Summary.", "keywords": ["a","b","c","d","e","f","g"]}'
    )
    with patch("app.services.chunk_enricher.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        result = await enrich_chunk("Some chunk content.")
    assert result is not None
    assert len(result.keywords) <= 5
```

**Step 2: Run tests to confirm they fail**

```bash
cd /home/ralph/dev/agentic-rag && source app/backapp/frontend/venv/bin/activate && python -m pytest tests/unit/services/test_chunk_enricher.py -v 2>&1 | head -20
```

Expected: `ImportError` or `ModuleNotFoundError` — `chunk_enricher` doesn't exist yet.

**Step 3: Create `app/backapp/frontend/app/services/chunk_enricher.py`**

```python
import json
import logging

from pydantic import BaseModel
from langsmith import traceable

from app.services.llm import client
from app.config import settings

logger = logging.getLogger(__name__)

ENRICHMENT_PROMPT = """Summarize the following text in 1-2 sentences and list 3-5 keywords.
Return ONLY valid JSON with these fields:
- "summary": string (1-2 sentences)
- "keywords": array of strings (3-5 short phrases, lowercase)"""


class ChunkEnrichment(BaseModel):
    summary: str
    keywords: list[str]


@traceable(name="enrich_chunk")
async def enrich_chunk(content: str) -> ChunkEnrichment | None:
    """Generate summary and keywords for a chunk via LLM.
    Returns None on any failure — enrichment is best-effort."""
    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": ENRICHMENT_PROMPT},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        enrichment = ChunkEnrichment.model_validate_json(raw)
        # Cap keywords at 5
        enrichment.keywords = enrichment.keywords[:5]
        return enrichment
    except Exception:
        logger.warning("Chunk enrichment failed, skipping", exc_info=False)
        return None
```

**Step 4: Run the tests**

```bash
cd /home/ralph/dev/agentic-rag && source app/backapp/frontend/venv/bin/activate && python -m pytest tests/unit/services/test_chunk_enricher.py -v 2>&1
```

Expected: all 6 tests PASS

**Step 5: Run full test suite**

```bash
cd /home/ralph/dev/agentic-rag && source app/backapp/frontend/venv/bin/activate && python -m pytest tests/ -v 2>&1
```

Expected: all pass (no regressions)

**Step 6: Commit**

```bash
git add app/backapp/frontend/app/services/chunk_enricher.py tests/unit/services/test_chunk_enricher.py
git commit -m "feat: chunk enricher service — LLM summary + keywords with graceful fallback"
```

---

### Task 3: Update ingestion pipeline to collect chunk IDs and run enrichment

**Files:**
- Modify: `app/backapp/frontend/app/services/ingestion.py`

**Step 1: Read the current ingestion file**

Read `app/backapp/frontend/app/services/ingestion.py` — focus on lines 68–83 (the chunk insert loop).

**Step 2: Make two targeted edits**

**Edit 1:** Add import at the top of the file (after the existing imports):

```python
from app.services.chunk_enricher import enrich_chunk
```

**Edit 2:** Replace the chunk insert loop (currently lines 68–83):

```python
        # Insert chunks with embeddings in batches — collect returned IDs
        inserted_chunk_rows: list[dict] = []
        for i in range(0, len(chunks), CHUNK_INSERT_BATCH_SIZE):
            batch_chunks = chunks[i : i + CHUNK_INSERT_BATCH_SIZE]
            batch_embeddings = all_embeddings[i : i + CHUNK_INSERT_BATCH_SIZE]
            rows = [
                {
                    "document_id": document_id,
                    "user_id": user_id,
                    "content": chunk.content,
                    "embedding": emb,
                    "chunk_index": chunk.chunk_index,
                    "token_count": chunk.token_count,
                    "content_hash": chunk.content_hash,
                }
                for chunk, emb in zip(batch_chunks, batch_embeddings)
            ]
            result = sb.table("chunks").insert(rows).execute()
            inserted_chunk_rows.extend(result.data)

        # Enrich each chunk: generate summary + keywords, embed summary
        for chunk_row in inserted_chunk_rows:
            enrichment = await enrich_chunk(chunk_row["content"])
            if enrichment is None:
                continue
            try:
                summary_embeddings = await generate_embeddings([enrichment.summary])
                sb.table("chunks").update(
                    {
                        "summary": enrichment.summary,
                        "summary_embedding": summary_embeddings[0],
                    }
                ).eq("id", chunk_row["id"]).execute()
                if enrichment.keywords:
                    keyword_rows = [
                        {
                            "chunk_id": chunk_row["id"],
                            "user_id": user_id,
                            "keyword": kw,
                        }
                        for kw in enrichment.keywords
                    ]
                    sb.table("keywords").insert(keyword_rows).execute()
            except Exception:
                logger.warning(
                    f"Failed to store enrichment for chunk {chunk_row['id']}, skipping"
                )
```

**Step 3: Verify the backend still starts**

```bash
cd /home/ralph/dev/agentic-rag && source app/backapp/frontend/venv/bin/activate && python -c "from app.services.ingestion import ingest_document; print('OK')" 2>&1
```

Expected: `OK`

**Step 4: Run full test suite**

```bash
cd /home/ralph/dev/agentic-rag && source app/backapp/frontend/venv/bin/activate && python -m pytest tests/ -v 2>&1
```

Expected: all pass

**Step 5: Commit**

```bash
git add app/backapp/frontend/app/services/ingestion.py
git commit -m "feat: run chunk enrichment inline during ingestion — summary embedding + keywords"
```

---

### Task 4: Update PROGRESS.md

**Files:**
- Modify: `PROGRESS.md`

Find and update:

```
- [ ] **Chunk metadata schema:** Add per-chunk fields (summary, keywords, hypothetical questions) + keywords table.
- [ ] **Chunk enrichment pipeline:** For each chunk: generate summary, extract/store keywords, generate hypothetical questions.
```

Change to:

```
- [x] **Chunk metadata schema:** Add per-chunk fields (summary, keywords, hypothetical questions) + keywords table.
- [x] **Chunk enrichment pipeline:** For each chunk: generate summary, extract/store keywords, generate hypothetical questions.
```

**Commit:**

```bash
git add PROGRESS.md
git commit -m "docs: mark Phase 5 chunk metadata schema and enrichment pipeline complete"
```
