# Web Documents Readable Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Store the original URL for web-ingested documents and display it as a clickable link in both the document viewer and the document list card.

**Architecture:** Add a `source_url TEXT` column to the `documents` table (NULL for uploaded files). The `/from-url` backend endpoint stores it at insert time. `DocumentResponse` exposes it. The frontend `Document` type, `DocumentViewer`, and `DocumentsPanel` all gain URL-awareness.

**Tech Stack:** Supabase (psql migration), FastAPI/Pydantic (backend), React/TypeScript/Tailwind (frontend)

---

### Task 1: Apply DB migration 018

**Files:**
- Create: `supabase/migrations/018_source_url_on_documents.sql`

**Step 1: Create the migration file**

```sql
-- Add source_url column to store original URL for web-ingested documents
ALTER TABLE documents ADD COLUMN source_url TEXT DEFAULT NULL;
```

**Step 2: Apply the migration**

```bash
docker exec -i supabase-db psql -U supabase_admin -d postgres -f - < supabase/migrations/018_source_url_on_documents.sql
```

Expected: `ALTER TABLE`

**Step 3: Verify column exists**

```bash
docker exec -i supabase-db psql -U postgres -d postgres -f - < <(echo "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='documents' AND column_name='source_url';")
```

Expected: `source_url | text`

**Step 4: Commit**

```bash
git add supabase/migrations/018_source_url_on_documents.sql
git commit -m "feat: add source_url column to documents table"
```

---

### Task 2: Backend — store and return `source_url`

**Files:**
- Modify: `backend/app/models/documents.py`
- Modify: `backend/app/routers/documents.py:303-318`

**Step 1: Add `source_url` to `DocumentResponse`**

In `backend/app/models/documents.py`, add one field to `DocumentResponse` after `document_date`:

```python
source_url: str | None = None
```

**Step 2: Store `source_url` in the `/from-url` insert**

In `backend/app/routers/documents.py`, find the document insert dict inside the `ingest_from_url` function (around line 307). Change:

```python
        .insert(
            {
                "user_id": user["id"],
                "filename": filename,
                "storage_path": storage_path,
                "file_type": "html",
                "file_size": len(content),
                "content_hash": content_hash,
                "status": "pending",
            }
        )
```

To:

```python
        .insert(
            {
                "user_id": user["id"],
                "filename": filename,
                "storage_path": storage_path,
                "file_type": "html",
                "file_size": len(content),
                "content_hash": content_hash,
                "status": "pending",
                "source_url": body.url,
            }
        )
```

**Step 3: Write a unit test for the source_url field**

Create `tests/unit/models/test_document_response.py`:

```python
from datetime import datetime
from app.models.documents import DocumentResponse


def make_doc(**overrides):
    base = {
        "id": "doc-1",
        "user_id": "user-1",
        "filename": "test.html",
        "storage_path": "user-1/abc.html",
        "file_type": "html",
        "file_size": 1024,
        "status": "ready",
        "chunk_count": 5,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }
    base.update(overrides)
    return base


def test_document_response_source_url_present():
    doc = DocumentResponse(**make_doc(source_url="https://example.com/article"))
    assert doc.source_url == "https://example.com/article"


def test_document_response_source_url_defaults_to_none():
    doc = DocumentResponse(**make_doc())
    assert doc.source_url is None
```

**Step 4: Run the tests**

```bash
source backend/venv/bin/activate && python -m pytest tests/unit/models/test_document_response.py -v
```

Expected: 2 PASS

**Step 5: Run full test suite**

```bash
source backend/venv/bin/activate && python -m pytest tests/ -v
```

Expected: all pass

**Step 6: Commit**

```bash
git add backend/app/models/documents.py backend/app/routers/documents.py tests/unit/models/test_document_response.py
git commit -m "feat: store and return source_url for web-ingested documents"
```

---

### Task 3: Frontend — add `source_url` to types and wire through

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add `source_url` to the `Document` interface**

In `frontend/src/types/index.ts`, inside the `Document` interface add after `document_date`:

```typescript
source_url?: string | null
```

**Step 2: Typecheck**

```bash
cd /home/ralph/dev/agentic-rag/frontend && npx tsc --noEmit 2>&1
```

Expected: no errors

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add source_url to Document type"
```

---

### Task 4: DocumentViewer — "View original" link in header

**Files:**
- Modify: `frontend/src/components/documents/DocumentViewer.tsx`

**Current header JSX (lines 57–65):**

```tsx
<DialogHeader>
  <DialogTitle className="truncate">
    {document?.title || document?.filename}
  </DialogTitle>
  {document?.title && (
    <DialogDescription className="truncate">
      {document.filename}
    </DialogDescription>
  )}
</DialogHeader>
```

**Step 1: Add `ExternalLink` import**

Change:
```typescript
import { Loader2 } from "lucide-react"
```
To:
```typescript
import { ExternalLink, Loader2 } from "lucide-react"
```

**Step 2: Replace the `DialogHeader` block**

Replace the entire `<DialogHeader>...</DialogHeader>` block with:

```tsx
<DialogHeader>
  <div className="flex items-start justify-between gap-3 pr-8">
    <DialogTitle className="truncate">
      {document?.title || document?.filename}
    </DialogTitle>
    {document?.source_url && (
      <a
        href={document.source_url}
        target="_blank"
        rel="noopener noreferrer"
        className="shrink-0 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors mt-0.5"
        title={document.source_url}
      >
        <ExternalLink className="h-3.5 w-3.5" />
        View original
      </a>
    )}
  </div>
  {document?.title && (
    <DialogDescription className="truncate">
      {document.filename}
    </DialogDescription>
  )}
</DialogHeader>
```

**Step 3: Typecheck**

```bash
cd /home/ralph/dev/agentic-rag/frontend && npx tsc --noEmit 2>&1
```

Expected: no errors

**Step 4: Commit**

```bash
git add frontend/src/components/documents/DocumentViewer.tsx
git commit -m "feat: show 'View original' link in DocumentViewer for web docs"
```

---

### Task 5: DocumentsPanel — URL on list card

**Files:**
- Modify: `frontend/src/components/documents/DocumentsPanel.tsx`

**Step 1: Add `ExternalLink` to imports**

Change:
```typescript
import { Eye, Pencil, X } from "lucide-react"
```
To:
```typescript
import { Eye, ExternalLink, Pencil, X } from "lucide-react"
```

**Step 2: Add a URL truncation helper**

Add this function after `formatDate` (around line 34):

```typescript
function truncateUrl(url: string): string {
  try {
    const u = new URL(url)
    const path = u.pathname.length > 20 ? u.pathname.slice(0, 20) + "…" : u.pathname
    return u.hostname + path
  } catch {
    return url.length > 40 ? url.slice(0, 40) + "…" : url
  }
}
```

**Step 3: Add the URL row to the document card**

In the document list card, find the block that shows `{doc.title && <p ...>{doc.filename}</p>}` (around line 184–186). After that block, add:

```tsx
{doc.source_url && (
  <a
    href={doc.source_url}
    target="_blank"
    rel="noopener noreferrer"
    onClick={(e) => e.stopPropagation()}
    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors mt-0.5 w-fit"
    title={doc.source_url}
  >
    <ExternalLink className="h-3 w-3 shrink-0" />
    <span className="truncate">{truncateUrl(doc.source_url)}</span>
  </a>
)}
```

Note: `e.stopPropagation()` prevents the link click from triggering the "view document" action on the card.

**Step 4: Typecheck**

```bash
cd /home/ralph/dev/agentic-rag/frontend && npx tsc --noEmit 2>&1
```

Expected: no errors

**Step 5: Commit**

```bash
git add frontend/src/components/documents/DocumentsPanel.tsx
git commit -m "feat: show source URL on document list card for web docs"
```

---

### Task 6: Browser validation

**Verify dev servers are running** (port 8001 and 5173).

**Test scenario 1 — Save a web result to KB and check URL appears on list card:**
1. Navigate to http://localhost:5173, log in as `test@agentic-rag.dev` / `TestPass123!`
2. Ask a question that triggers web search
3. In the Web Results panel, click "Save to KB" on one result
4. Navigate to the Documents tab
5. Verify: the saved document card shows the truncated URL with an external link icon below the title

**Test scenario 2 — View original link in DocumentViewer:**
1. In the Documents tab, wait for the saved web doc to reach status "ready"
2. Click the document title to open the viewer
3. Verify: "View original →" link appears in the viewer header
4. Click it — verify it opens the correct URL in a new tab

**Test scenario 3 — Uploaded files have no URL:**
1. Upload a regular file (PDF or TXT)
2. Verify: no URL row appears on its list card
3. Open its viewer — verify no "View original" link in header

---

### Task 7: Update PROGRESS.md

**Files:**
- Modify: `PROGRESS.md`

Find and update:

```
- [ ] **Web documents readable:** Web searches saved/imported into the RAG are readable and include the original link.
```

Change to:

```
- [x] **Web documents readable:** Web searches saved/imported into the RAG are readable and include the original link.
```

**Commit:**

```bash
git add PROGRESS.md
git commit -m "docs: mark web documents readable as complete"
```
