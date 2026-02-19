# Tag Quality Improvement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve auto-generated tag quality via a per-user tag blocklist with retroactive removal and a background LLM quality sweep.

**Architecture:** Two complementary systems: (1) `blocked_tags` table + API endpoints + frontend UX for manual blocking, (2) periodic background task that samples documents and uses the LLM to remove irrelevant tags. YAKE candidate count increases from 5→15, filtered down to max 8 after blocklist.

**Tech Stack:** Python/FastAPI backend, Supabase (Postgres + RLS), React frontend (shadcn/ui), existing LLM client.

---

### Task 1: Database Migration — `blocked_tags` Table + `block_tag` RPC

**Files:**
- Create: `db/migrations/022_blocked_tags.sql`

**Step 1: Write the migration**

```sql
-- 022_blocked_tags.sql
-- Per-user tag blocklist with retroactive removal.

CREATE TABLE IF NOT EXISTS blocked_tags (
    id         uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tag        text NOT NULL,
    created_at timestamptz DEFAULT now(),
    UNIQUE (user_id, tag)
);

-- RLS: users only see their own blocked tags
ALTER TABLE blocked_tags ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own blocked tags"
    ON blocked_tags FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own blocked tags"
    ON blocked_tags FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own blocked tags"
    ON blocked_tags FOR DELETE
    USING (auth.uid() = user_id);

-- block_tag: insert into blocklist + remove from all user's documents atomically
-- Uses SECURITY INVOKER so RLS is inherited.
CREATE OR REPLACE FUNCTION block_tag(p_tag text)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_count integer;
BEGIN
    -- Insert into blocklist (no-op on conflict)
    INSERT INTO blocked_tags (user_id, tag)
    VALUES (auth.uid(), p_tag)
    ON CONFLICT (user_id, tag) DO NOTHING;

    -- Remove tag from all user's documents
    UPDATE documents
    SET    topics = array_remove(topics, p_tag)
    WHERE  topics @> ARRAY[p_tag];

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

-- unblock_tag: remove from blocklist (does NOT re-add to documents)
CREATE OR REPLACE FUNCTION unblock_tag(p_tag text)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
BEGIN
    DELETE FROM blocked_tags
    WHERE user_id = auth.uid() AND tag = p_tag;
END;
$$;
```

**Step 2: Apply migration**

Run: `psql "$DATABASE_URL" -f db/migrations/022_blocked_tags.sql`
Expected: CREATE TABLE, ALTER TABLE, CREATE POLICY (x3), CREATE FUNCTION (x2) — no errors.

**Step 3: Commit**

```bash
git add -f db/migrations/022_blocked_tags.sql
git commit -m "feat: add blocked_tags table and block_tag/unblock_tag RPCs"
```

---

### Task 2: Backend Config — YAKE + Sweep Settings

**Files:**
- Modify: `app/backend/app/config.py:37` (add settings after topic_consolidation block)

**Step 1: Write the failing test**

Create: `app/backend/tests/unit/services/test_config_tag_settings.py`

```python
from app.config import Settings


def test_tag_settings_defaults():
    s = Settings(
        supabase_url="http://x",
        supabase_anon_key="x",
        supabase_service_role_key="x",
        supabase_jwt_secret="x",
    )
    assert s.tag_candidates == 15
    assert s.tag_max_per_document == 8
    assert s.tag_quality_sweep_enabled is True
    assert s.tag_quality_sweep_interval_hours == 12
    assert s.tag_quality_sweep_sample_size == 10
    assert s.tag_quality_auto_block_threshold == 3
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/unit/services/test_config_tag_settings.py -v`
Expected: FAIL — Settings has no `tag_candidates` attribute.

**Step 3: Add settings to config**

In `app/backend/app/config.py`, add after line 38 (`topic_consolidation_interval_hours`):

```python
    tag_candidates: int = 15                        # YAKE candidates before filtering
    tag_max_per_document: int = 8                   # max tags kept after blocklist filter
    tag_quality_sweep_enabled: bool = True
    tag_quality_sweep_interval_hours: float = 12
    tag_quality_sweep_sample_size: int = 10
    tag_quality_auto_block_threshold: int = 3       # auto-block if removed from N+ docs in one sweep
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/unit/services/test_config_tag_settings.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/backend/app/config.py app/backend/tests/unit/services/test_config_tag_settings.py
git commit -m "feat: add tag quality config settings (YAKE candidates, sweep params)"
```

---

### Task 3: Increase YAKE Candidates + Blocklist Filtering in Metadata Service

**Files:**
- Modify: `app/backend/app/services/metadata.py:37,74-81`
- Test: `app/backend/tests/unit/services/test_metadata_tag_filtering.py`

**Step 1: Write the failing tests**

Create: `app/backend/tests/unit/services/test_metadata_tag_filtering.py`

```python
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_extract_topics_uses_configured_candidates():
    """YAKE extractor should use settings.tag_candidates, not hardcoded 5."""
    with patch("app.services.metadata.settings") as mock_settings:
        mock_settings.tag_candidates = 15
        mock_settings.tag_max_per_document = 8
        # Re-import to test extractor creation
        from app.services.metadata import _extract_topics
        text = "climate change policy renewable energy solar wind power carbon emissions greenhouse gas global warming temperature rise sea level adaptation mitigation strategy"
        topics = _extract_topics(text)
        # With top=15, we should get more than 5 (up to 8 after cap)
        assert len(topics) <= 8


@pytest.mark.asyncio
async def test_extract_metadata_filters_blocked_tags():
    """Blocked tags should be removed from extracted topics."""
    from app.services.metadata import extract_metadata
    # Patch _extract_topics to return known tags
    with patch("app.services.metadata._extract_topics", return_value=[
        "climate change", "communications plan", "key findings",
        "renewable energy", "executive summary", "carbon policy",
    ]):
        result = await extract_metadata(
            "some text",
            filename="test.pdf",
            blocked_tags={"communications plan", "executive summary"},
        )
    assert "communications plan" not in result.topics
    assert "executive summary" not in result.topics
    assert "climate change" in result.topics
    assert "renewable energy" in result.topics


@pytest.mark.asyncio
async def test_extract_metadata_caps_at_max_per_document():
    """Topics should be capped at tag_max_per_document after filtering."""
    from app.services.metadata import extract_metadata
    many_tags = [f"tag{i}" for i in range(12)]
    with patch("app.services.metadata._extract_topics", return_value=many_tags), \
         patch("app.services.metadata.settings") as mock_settings:
        mock_settings.tag_max_per_document = 8
        result = await extract_metadata("some text", filename="test.pdf")
    assert len(result.topics) == 8


@pytest.mark.asyncio
async def test_extract_metadata_no_blocked_tags_default():
    """Without blocked_tags argument, all topics pass through."""
    from app.services.metadata import extract_metadata
    with patch("app.services.metadata._extract_topics", return_value=["a", "b", "c"]), \
         patch("app.services.metadata.settings") as mock_settings:
        mock_settings.tag_max_per_document = 8
        result = await extract_metadata("some text", filename="test.pdf")
    assert result.topics == ["a", "b", "c"]
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/unit/services/test_metadata_tag_filtering.py -v`
Expected: FAIL — `extract_metadata` doesn't accept `blocked_tags` parameter.

**Step 3: Modify metadata.py**

In `app/backend/app/services/metadata.py`:

1. Add import at top: `from app.config import settings`

2. Change YAKE extractor (line 37) from:
```python
_kw_extractor = yake.KeywordExtractor(lan="en", n=2, dedupLim=0.7, top=5)
```
to:
```python
_kw_extractor = yake.KeywordExtractor(lan="en", n=2, dedupLim=0.7, top=settings.tag_candidates)
```

3. Change `_extract_topics` (lines 74-81) to return more candidates (no longer caps internally — capping done at caller):
```python
def _extract_topics(text: str) -> list[str]:
    """Top keyphrases from the first 5 000 chars via YAKE."""
    try:
        keywords = _kw_extractor.extract_keywords(text[:5000])
        return [kw.lower() for kw, _score in keywords]
    except Exception as exc:
        logger.warning("Keyword extraction failed: %s", exc)
        return []
```

4. Change `extract_metadata` signature and body (lines 148-156) to accept `blocked_tags` and apply filtering + cap:
```python
@traceable(name="extract_metadata")
async def extract_metadata(
    text: str,
    filename: str = "",
    blocked_tags: set[str] | None = None,
) -> DocumentMetadata:
    """Extract document metadata using Python NLP — no LLM needed."""
    topics = _extract_topics(text)
    if blocked_tags:
        topics = [t for t in topics if t not in blocked_tags]
    topics = topics[:settings.tag_max_per_document]
    return DocumentMetadata(
        title=_extract_title(text, filename),
        summary=_extract_summary(text),
        topics=topics,
        document_date=_extract_date(text),
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/unit/services/test_metadata_tag_filtering.py -v`
Expected: PASS

**Step 5: Run existing tests to check nothing broke**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/ -v`
Expected: All pass.

**Step 6: Commit**

```bash
git add app/backend/app/services/metadata.py app/backend/tests/unit/services/test_metadata_tag_filtering.py
git commit -m "feat: increase YAKE candidates to 15, add blocklist filtering and max cap"
```

---

### Task 4: Fetch Blocked Tags During Ingestion

**Files:**
- Modify: `app/backend/app/services/ingestion.py:83`

**Step 1: Write the failing test**

Create: `app/backend/tests/unit/services/test_ingestion_blocklist.py`

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_ingest_passes_blocked_tags_to_metadata():
    """Ingestion should fetch user's blocked tags and pass them to extract_metadata."""
    mock_sb = MagicMock()
    # doc check
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "doc-1", "filename": "test.pdf"}
    ]
    # update calls
    mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    # delete stale chunks
    mock_sb.table.return_value.delete.return_value.eq.return_value.execute.return_value = None
    # storage download
    mock_sb.storage.from_.return_value.download.return_value = b"some text content"
    # storage remove + upload
    mock_sb.storage.from_.return_value.remove.return_value = None
    mock_sb.storage.from_.return_value.upload.return_value = None
    # blocked_tags query
    mock_blocked = MagicMock()
    mock_blocked.select.return_value.eq.return_value.execute.return_value.data = [
        {"tag": "communications plan"},
        {"tag": "key findings"},
    ]

    # Need to handle multiple table() calls differently
    original_table = mock_sb.table
    def table_router(name):
        if name == "blocked_tags":
            return mock_blocked
        return original_table(name)
    mock_sb.table = MagicMock(side_effect=table_router)
    # Re-setup document table calls after replacing table
    doc_table = MagicMock()
    doc_table.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "doc-1", "filename": "test.pdf"}
    ]
    doc_table.update.return_value.eq.return_value.execute.return_value = None
    doc_table.delete.return_value.eq.return_value.execute.return_value = None
    chunks_table = MagicMock()
    chunks_table.delete.return_value.eq.return_value.execute.return_value = None
    chunks_table.insert.return_value.execute.return_value = None

    call_count = {"documents": 0}
    def table_side_effect(name):
        if name == "blocked_tags":
            return mock_blocked
        if name == "chunks":
            return chunks_table
        return doc_table

    mock_sb.table = MagicMock(side_effect=table_side_effect)

    mock_extract_metadata = AsyncMock(return_value=MagicMock(
        title="Test", summary="Summary", topics=["climate"], document_date=None,
    ))

    with patch("app.services.ingestion.get_service_supabase_client", return_value=mock_sb), \
         patch("app.services.ingestion.extract_text", return_value="some text"), \
         patch("app.services.ingestion.clean_text", return_value="some text"), \
         patch("app.services.ingestion.extract_metadata", mock_extract_metadata), \
         patch("app.services.ingestion.chunk_text", return_value=[]), \
         patch("app.services.ingestion.generate_embeddings", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.ingestion.settings") as mock_settings:
        mock_settings.graphrag_enabled = False

        from app.services.ingestion import ingest_document
        await ingest_document("doc-1", "user-1", "path/file.pdf", "pdf")

    # Verify extract_metadata was called with blocked_tags
    mock_extract_metadata.assert_called_once()
    call_kwargs = mock_extract_metadata.call_args
    assert "blocked_tags" in call_kwargs.kwargs or (len(call_kwargs.args) > 2)
    blocked = call_kwargs.kwargs.get("blocked_tags", set())
    assert "communications plan" in blocked
    assert "key findings" in blocked
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/unit/services/test_ingestion_blocklist.py -v`
Expected: FAIL — ingestion doesn't query blocked_tags.

**Step 3: Modify ingestion.py**

In `app/backend/app/services/ingestion.py`, after the `clean_text` call (around line 62) and before `extract_metadata` (line 83), add blocked tags fetch:

```python
        # Fetch user's blocked tags for filtering
        blocked_rows = sb.table("blocked_tags").select("tag").eq("user_id", user_id).execute().data
        blocked_tags = {r["tag"] for r in (blocked_rows or [])}
```

Then change the `extract_metadata` call (line 83) from:
```python
        metadata = await extract_metadata(text, filename=filename)
```
to:
```python
        metadata = await extract_metadata(text, filename=filename, blocked_tags=blocked_tags)
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/unit/services/test_ingestion_blocklist.py -v`
Expected: PASS

**Step 5: Run all tests**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/ -v`
Expected: All pass.

**Step 6: Commit**

```bash
git add app/backend/app/services/ingestion.py app/backend/tests/unit/services/test_ingestion_blocklist.py
git commit -m "feat: filter blocked tags during document ingestion"
```

---

### Task 5: Backend API Endpoints for Blocked Tags

**Files:**
- Modify: `app/backend/app/routers/documents.py` (add 3 endpoints)
- Test: `app/backend/tests/test_blocked_tags_api.py`

**Step 1: Write the failing tests**

Create: `app/backend/tests/test_blocked_tags_api.py`

```python
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def _make_app():
    """Create test app with auth mocked."""
    from app.main import app
    return app


def _auth_headers():
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def client():
    app = _make_app()
    with patch("app.dependencies.jwt") as mock_jwt:
        mock_jwt.decode.return_value = {"sub": "user-1", "email": "test@test.com"}
        yield TestClient(app)


def test_list_blocked_tags(client):
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.order.return_value.execute.return_value.data = [
        {"id": "1", "tag": "communications plan", "created_at": "2026-01-01T00:00:00Z"},
        {"id": "2", "tag": "key findings", "created_at": "2026-01-01T00:00:00Z"},
    ]
    with patch("app.routers.documents.get_supabase_client", return_value=mock_sb):
        res = client.get("/api/documents/blocked-tags", headers=_auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert data[0]["tag"] == "communications plan"


def test_block_tag(client):
    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value.data = 5
    with patch("app.routers.documents.get_supabase_client", return_value=mock_sb):
        res = client.post(
            "/api/documents/blocked-tags",
            json={"tag": "communications plan"},
            headers=_auth_headers(),
        )
    assert res.status_code == 200
    data = res.json()
    assert data["tag"] == "communications plan"
    assert data["documents_updated"] == 5
    mock_sb.rpc.assert_called_once_with("block_tag", {"p_tag": "communications plan"})


def test_block_tag_empty_rejected(client):
    with patch("app.routers.documents.get_supabase_client"):
        res = client.post(
            "/api/documents/blocked-tags",
            json={"tag": "  "},
            headers=_auth_headers(),
        )
    assert res.status_code == 400


def test_unblock_tag(client):
    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value.data = None
    with patch("app.routers.documents.get_supabase_client", return_value=mock_sb):
        res = client.delete(
            "/api/documents/blocked-tags/communications%20plan",
            headers=_auth_headers(),
        )
    assert res.status_code == 204
    mock_sb.rpc.assert_called_once_with("unblock_tag", {"p_tag": "communications plan"})
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/test_blocked_tags_api.py -v`
Expected: FAIL — routes don't exist yet.

**Step 3: Add endpoints to documents router**

In `app/backend/app/routers/documents.py`, add a Pydantic model at the top (after existing imports):

```python
from pydantic import BaseModel as PydanticBaseModel

class BlockTagRequest(PydanticBaseModel):
    tag: str
```

Then add these three endpoints (before the `backfill-graph` endpoint):

```python
@router.get("/blocked-tags")
async def list_blocked_tags(user: dict = Depends(get_current_user)):
    sb = get_supabase_client(user["token"])
    result = sb.table("blocked_tags").select("*").order("created_at", desc=True).execute()
    return result.data


@router.post("/blocked-tags")
async def block_tag(body: BlockTagRequest, user: dict = Depends(get_current_user)):
    tag = body.tag.strip().lower()
    if not tag:
        raise HTTPException(status_code=400, detail="Tag cannot be empty")
    sb = get_supabase_client(user["token"])
    result = sb.rpc("block_tag", {"p_tag": tag}).execute()
    docs_updated = result.data if isinstance(result.data, int) else 0
    return {"tag": tag, "documents_updated": docs_updated}


@router.delete("/blocked-tags/{tag}", status_code=status.HTTP_204_NO_CONTENT)
async def unblock_tag(tag: str, user: dict = Depends(get_current_user)):
    sb = get_supabase_client(user["token"])
    sb.rpc("unblock_tag", {"p_tag": tag}).execute()
```

**Important:** These routes must be defined BEFORE the `/{document_id}` route, otherwise FastAPI will try to match "blocked-tags" as a document_id. Move them above line 40 (`@router.patch("/{document_id}")`).

**Step 4: Run tests to verify they pass**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/test_blocked_tags_api.py -v`
Expected: PASS

**Step 5: Run all tests**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/ -v`
Expected: All pass.

**Step 6: Commit**

```bash
git add app/backend/app/routers/documents.py app/backend/tests/test_blocked_tags_api.py
git commit -m "feat: add blocked-tags API endpoints (list, block, unblock)"
```

---

### Task 6: Frontend — `useBlockedTags` Hook

**Files:**
- Create: `app/frontend/src/hooks/useBlockedTags.ts`

**Step 1: Write the hook**

```typescript
import { useState, useEffect, useCallback } from "react"
import { apiFetch } from "@/lib/api"

export interface BlockedTag {
  id: string
  tag: string
  created_at: string
}

export function useBlockedTags() {
  const [blockedTags, setBlockedTags] = useState<BlockedTag[]>([])

  const fetchBlockedTags = useCallback(async () => {
    const res = await apiFetch("/api/documents/blocked-tags")
    if (res.ok) {
      setBlockedTags(await res.json())
    }
  }, [])

  const blockTag = useCallback(async (tag: string): Promise<number> => {
    const res = await apiFetch("/api/documents/blocked-tags", {
      method: "POST",
      body: JSON.stringify({ tag }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Block failed" }))
      throw new Error(err.detail || "Block failed")
    }
    const data = await res.json()
    setBlockedTags(prev => [
      { id: crypto.randomUUID(), tag: data.tag, created_at: new Date().toISOString() },
      ...prev,
    ])
    return data.documents_updated
  }, [])

  const unblockTag = useCallback(async (tag: string) => {
    const res = await apiFetch(`/api/documents/blocked-tags/${encodeURIComponent(tag)}`, {
      method: "DELETE",
    })
    if (res.ok) {
      setBlockedTags(prev => prev.filter(bt => bt.tag !== tag))
    }
  }, [])

  useEffect(() => {
    fetchBlockedTags()
  }, [fetchBlockedTags])

  return { blockedTags, blockTag, unblockTag, fetchBlockedTags }
}
```

**Step 2: Commit**

```bash
git add app/frontend/src/hooks/useBlockedTags.ts
git commit -m "feat: add useBlockedTags hook for blocked tags API"
```

---

### Task 7: Frontend — Block Icon in EditMetadataModal

**Files:**
- Modify: `app/frontend/src/components/documents/EditMetadataModal.tsx`

**Step 1: Add block icon to tag chips**

Changes to `EditMetadataModal.tsx`:

1. Add `Ban` to lucide import (line 2): `import { X, Ban } from "lucide-react"`

2. Add `onBlockTag` prop to the interface:
```typescript
interface EditMetadataModalProps {
  document: Document | null
  open: boolean
  onClose: () => void
  onSave: (
    id: string,
    updates: Partial<Pick<Document, "title" | "summary" | "topics" | "document_date">>
  ) => Promise<Document>
  onBlockTag?: (tag: string) => Promise<number>
}
```

3. Update component signature to accept `onBlockTag`:
```typescript
export function EditMetadataModal({ document, open, onClose, onSave, onBlockTag }: EditMetadataModalProps) {
```

4. Replace the tag chip `<span>` block (lines 130-143) with:
```tsx
                <span
                  key={topic}
                  className="inline-flex items-center gap-1 bg-primary/10 text-primary rounded-full px-2 py-0.5 text-xs"
                >
                  {topic}
                  {onBlockTag && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        onBlockTag(topic).then(() => removeTopic(topic))
                      }}
                      className="hover:text-destructive"
                      title="Block this tag from all documents"
                    >
                      <Ban className="size-3" />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); removeTopic(topic) }}
                    className="hover:text-destructive"
                  >
                    <X className="size-3" />
                  </button>
                </span>
```

**Step 2: Commit**

```bash
git add app/frontend/src/components/documents/EditMetadataModal.tsx
git commit -m "feat: add block icon to tag chips in edit metadata modal"
```

---

### Task 8: Frontend — Context Menu on Tag Pills in DocumentsPanel

**Files:**
- Modify: `app/frontend/src/components/documents/DocumentsPanel.tsx`

**Step 1: Add context menu and wire up blocked tags**

Changes to `DocumentsPanel.tsx`:

1. Add `Ban` to lucide import: `import { Eye, ExternalLink, Pencil, X, Ban } from "lucide-react"`

2. Add `useBlockedTags` import and `toast` (from sonner):
```typescript
import { useBlockedTags } from "@/hooks/useBlockedTags"
import { toast } from "sonner"
```

3. Add `onBlockTag` prop and pass it to EditMetadataModal. Update the interface:
```typescript
interface DocumentsPanelProps {
  documents: Document[]
  loading: boolean
  uploading: boolean
  onUpload: (file: File) => Promise<Document>
  onDelete: (id: string) => Promise<void>
  onUpdate: (id: string, updates: Partial<Pick<Document, "title" | "summary" | "topics" | "document_date">>) => Promise<Document>
  onBlockTag: (tag: string) => Promise<number>
}
```

4. Add state for context menu inside the component:
```typescript
  const [contextMenu, setContextMenu] = useState<{ topic: string; x: number; y: number } | null>(null)
```

5. Replace the tag pill button (lines 230-240) with:
```tsx
                        <button
                          key={topic}
                          onClick={(e) => { e.stopPropagation(); toggleTopic(topic) }}
                          onContextMenu={(e) => {
                            e.preventDefault()
                            e.stopPropagation()
                            setContextMenu({ topic, x: e.clientX, y: e.clientY })
                          }}
                          className={`text-xs rounded-full px-2 py-0.5 transition-colors ${
                            activeTopics.has(topic)
                              ? "bg-primary text-primary-foreground"
                              : "bg-primary/10 text-primary hover:bg-primary/20"
                          }`}
                        >
                          {topic}
                        </button>
```

6. Add a context menu component (just before the closing `</div>` of the main container, after the EditMetadataModal):
```tsx
      {contextMenu && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setContextMenu(null)}
          />
          <div
            className="fixed z-50 bg-popover border rounded-md shadow-md py-1 min-w-[160px]"
            style={{ left: contextMenu.x, top: contextMenu.y }}
          >
            <button
              className="flex items-center gap-2 w-full px-3 py-1.5 text-sm hover:bg-accent text-left"
              onClick={() => {
                toggleTopic(contextMenu.topic)
                setContextMenu(null)
              }}
            >
              Filter by tag
            </button>
            <button
              className="flex items-center gap-2 w-full px-3 py-1.5 text-sm hover:bg-accent text-left text-destructive"
              onClick={async () => {
                const topic = contextMenu.topic
                setContextMenu(null)
                try {
                  const count = await onBlockTag(topic)
                  toast.success(`Blocked "${topic}" — removed from ${count} document(s)`)
                } catch {
                  toast.error(`Failed to block "${topic}"`)
                }
              }}
            >
              <Ban className="size-3" /> Block this tag
            </button>
          </div>
        </>
      )}
```

7. Pass `onBlockTag` to EditMetadataModal (line 285-290):
```tsx
      <EditMetadataModal
        document={editingDoc}
        open={editingDoc !== null}
        onClose={() => setEditingDoc(null)}
        onSave={onUpdate}
        onBlockTag={onBlockTag}
      />
```

**Step 2: Wire up in parent — DocumentPage.tsx**

Check `app/frontend/src/pages/DocumentPage.tsx` to see where `DocumentsPanel` is rendered and pass the `onBlockTag` prop. The parent needs to use `useBlockedTags` and pass `blockTag` down.

In `DocumentPage.tsx`, add:
```typescript
import { useBlockedTags } from "@/hooks/useBlockedTags"
```

Inside the component:
```typescript
const { blockTag } = useBlockedTags()
```

Pass to DocumentsPanel:
```tsx
<DocumentsPanel
  ...existing props...
  onBlockTag={blockTag}
/>
```

**Step 3: Commit**

```bash
git add app/frontend/src/components/documents/DocumentsPanel.tsx app/frontend/src/pages/DocumentPage.tsx
git commit -m "feat: add right-click context menu to block tags from document list"
```

---

### Task 9: Background LLM Tag Quality Sweep Service

**Files:**
- Create: `app/backend/app/services/tag_quality_sweep.py`
- Test: `app/backend/tests/unit/services/test_tag_quality_sweep.py`

**Step 1: Write the failing tests**

Create: `app/backend/tests/unit/services/test_tag_quality_sweep.py`

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pydantic import BaseModel


class FakeTagAssessment(BaseModel):
    keep: list[str]
    remove: list[str]


@pytest.mark.asyncio
async def test_assess_tags_returns_keep_and_remove():
    """LLM should classify tags as keep or remove."""
    from app.services.tag_quality_sweep import assess_tag_quality

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"keep": ["climate change", "renewable energy"], "remove": ["key findings"]}'

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.tag_quality_sweep.client", mock_client):
        result = await assess_tag_quality(
            title="Climate Report",
            summary="A report on climate change impacts.",
            tags=["climate change", "renewable energy", "key findings"],
        )

    assert "climate change" in result["keep"]
    assert "key findings" in result["remove"]


@pytest.mark.asyncio
async def test_assess_tags_handles_llm_failure():
    """If LLM fails, return all tags as keep (safe fallback)."""
    from app.services.tag_quality_sweep import assess_tag_quality

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM down"))

    with patch("app.services.tag_quality_sweep.client", mock_client):
        result = await assess_tag_quality(
            title="Test", summary="Test", tags=["a", "b"]
        )

    assert result["keep"] == ["a", "b"]
    assert result["remove"] == []


@pytest.mark.asyncio
async def test_sweep_user_updates_documents():
    """sweep_user should remove bad tags and auto-block frequent offenders."""
    from app.services.tag_quality_sweep import sweep_user

    mock_sb = MagicMock()
    # Sample documents
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "d1", "title": "Doc 1", "summary": "S1", "topics": ["climate", "key findings", "action items"]},
        {"id": "d2", "title": "Doc 2", "summary": "S2", "topics": ["energy", "key findings", "executive summary"]},
        {"id": "d3", "title": "Doc 3", "summary": "S3", "topics": ["policy", "key findings"]},
    ]
    mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    mock_sb.rpc.return_value.execute.return_value = None

    async def fake_assess(title, summary, tags):
        # Always remove "key findings" and "action items" and "executive summary"
        keep = [t for t in tags if t not in {"key findings", "action items", "executive summary"}]
        remove = [t for t in tags if t in {"key findings", "action items", "executive summary"}]
        return {"keep": keep, "remove": remove}

    with patch("app.services.tag_quality_sweep.get_service_supabase_client", return_value=mock_sb), \
         patch("app.services.tag_quality_sweep.assess_tag_quality", side_effect=fake_assess), \
         patch("app.services.tag_quality_sweep.settings") as mock_settings:
        mock_settings.tag_quality_sweep_sample_size = 10
        mock_settings.tag_quality_auto_block_threshold = 3

        result = await sweep_user("user-1")

    # 3 documents should have been updated (all had removable tags)
    assert result["docs_updated"] == 3
    # "key findings" removed from 3 docs — should be auto-blocked (threshold=3)
    assert "key findings" in result["auto_blocked"]
    # "action items" only in 1 doc — not auto-blocked
    assert "action items" not in result["auto_blocked"]


@pytest.mark.asyncio
async def test_sweep_user_skips_docs_with_no_topics():
    """Documents with empty topics should be skipped."""
    from app.services.tag_quality_sweep import sweep_user

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "d1", "title": "Doc 1", "summary": "S1", "topics": []},
    ]

    with patch("app.services.tag_quality_sweep.get_service_supabase_client", return_value=mock_sb), \
         patch("app.services.tag_quality_sweep.settings") as mock_settings:
        mock_settings.tag_quality_sweep_sample_size = 10
        mock_settings.tag_quality_auto_block_threshold = 3

        result = await sweep_user("user-1")

    assert result["docs_updated"] == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/unit/services/test_tag_quality_sweep.py -v`
Expected: FAIL — module doesn't exist.

**Step 3: Create the sweep service**

Create: `app/backend/app/services/tag_quality_sweep.py`

```python
"""Background tag quality sweep — LLM-based assessment of tag relevance."""
import logging
import json
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

    # Fetch random sample of user's documents that have topics
    result = sb.table("documents").select(
        "id, title, summary, topics"
    ).eq("user_id", user_id).execute()

    docs = [d for d in (result.data or []) if d.get("topics")]
    if not docs:
        return {"docs_updated": 0, "auto_blocked": []}

    # Random sample
    import random
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

    # Auto-block tags removed from N+ documents
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
            pass  # Already blocked or other conflict

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

    import random
    user_id = random.choice(user_ids)
    try:
        await sweep_user(user_id)
    except Exception:
        logger.exception(f"Tag quality sweep failed for user {user_id}")
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/unit/services/test_tag_quality_sweep.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/backend/app/services/tag_quality_sweep.py app/backend/tests/unit/services/test_tag_quality_sweep.py
git commit -m "feat: add background tag quality sweep service"
```

---

### Task 10: Wire Sweep Into Background Loop

**Files:**
- Modify: `app/backend/app/main.py`

**Step 1: Write the failing test**

Create: `app/backend/tests/unit/test_main_sweep_loop.py`

```python
from unittest.mock import patch


def test_sweep_loop_imported():
    """Verify main.py imports the sweep function."""
    with patch("app.services.tag_quality_sweep.sweep_random_user"):
        from app.main import _tag_quality_sweep_loop
        assert _tag_quality_sweep_loop is not None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/unit/test_main_sweep_loop.py -v`
Expected: FAIL — `_tag_quality_sweep_loop` doesn't exist.

**Step 3: Add sweep loop to main.py**

In `app/backend/app/main.py`:

1. Add import (after line 8):
```python
from app.services.tag_quality_sweep import sweep_random_user
```

2. Add the loop function (after the `_topic_consolidation_loop` function, ~line 34):
```python
async def _tag_quality_sweep_loop():
    interval = settings.tag_quality_sweep_interval_hours * 3600
    while True:
        await asyncio.sleep(interval)
        logger.info("Running periodic tag quality sweep")
        try:
            await sweep_random_user()
        except Exception:
            logger.exception("Tag quality sweep loop error")
```

3. Add the task creation in the `lifespan` function (after the topic consolidation task, ~line 51):
```python
    if settings.tag_quality_sweep_enabled:
        asyncio.create_task(_tag_quality_sweep_loop())
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/unit/test_main_sweep_loop.py -v`
Expected: PASS

**Step 5: Run all tests**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/ -v`
Expected: All pass.

**Step 6: Commit**

```bash
git add app/backend/app/main.py app/backend/tests/unit/test_main_sweep_loop.py
git commit -m "feat: add tag quality sweep background loop to app startup"
```

---

### Task 11: Update Documents After Blocking (Refresh Frontend State)

**Files:**
- Modify: `app/frontend/src/pages/DocumentPage.tsx` (or wherever DocumentsPanel is composed)

**Step 1: Wire blockTag to also refresh documents**

When a tag is blocked, the backend removes it from all documents. The frontend's document list state becomes stale. The `blockTag` call should trigger a `fetchDocuments` refresh.

In the parent component that holds both `useDocuments` and `useBlockedTags`:

```typescript
const handleBlockTag = useCallback(async (tag: string) => {
  const count = await blockTag(tag)
  await fetchDocuments(true)  // silent refresh to pick up removed tags
  return count
}, [blockTag, fetchDocuments])
```

Pass `handleBlockTag` (not raw `blockTag`) to `DocumentsPanel`:
```tsx
<DocumentsPanel ... onBlockTag={handleBlockTag} />
```

**Step 2: Commit**

```bash
git add app/frontend/src/pages/DocumentPage.tsx
git commit -m "feat: refresh document list after blocking a tag"
```

---

### Task 12: Final Integration Test + Typecheck

**Step 1: Run all backend tests**

Run: `cd /home/ralph/rag/app/backend && python -m pytest tests/ -v`
Expected: All pass.

**Step 2: Run frontend typecheck**

Run: `cd /home/ralph/rag/app/frontend && npx tsc --noEmit`
Expected: No errors.

**Step 3: Run frontend build**

Run: `cd /home/ralph/rag/app/frontend && npm run build`
Expected: Build succeeds.

**Step 4: Commit any fixes, update PROGRESS.md**

Add a new line under the appropriate phase in PROGRESS.md:
```
- [x] Tag quality improvement — blocklist + background LLM sweep
```

```bash
git add PROGRESS.md
git commit -m "docs: mark tag quality improvement as complete"
```
