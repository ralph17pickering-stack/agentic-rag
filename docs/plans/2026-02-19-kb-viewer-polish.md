# KB Viewer Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the plain modal document viewer with a two-tier system: an in-chat side panel (40% desktop / bottom drawer mobile) and a full-screen `/documents/:id` route, both sharing a unified metadata + markdown content component.

**Architecture:** A `DocumentViewerProvider` context at the App level exposes `openDocument` / `openDocumentById` to any component. `DocumentViewerPanel` renders as a flex column on desktop and a fixed bottom drawer on mobile, both toggled via CSS transitions. `DocumentPage` is a new React Router route that renders a standalone three-column layout reusing the same content component.

**Tech Stack:** React 19 + TypeScript, Vite, Tailwind v4, shadcn/ui, `react-router-dom` v7, `react-markdown`, FastAPI backend.

**Design doc:** `docs/plans/2026-02-19-kb-viewer-polish-design.md`

---

## Task 1: Install frontend dependencies

**Files:**
- Modify: `app/frontend/package.json`

**Step 1: Install packages**

```bash
cd app/frontend && npm install react-router-dom react-markdown remark-gfm
```

Expected: packages added to `node_modules`, `package.json` updated.

**Step 2: Verify TypeScript types resolve**

```bash
cd app/frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no new errors (react-router-dom ships its own types).

**Step 3: Commit**

```bash
git add app/frontend/package.json app/frontend/package-lock.json
git commit -m "chore: add react-router-dom, react-markdown, remark-gfm"
```

---

## Task 2: Add `GET /api/documents/{document_id}` backend endpoint

**Files:**
- Modify: `app/backend/app/routers/documents.py`

**Step 1: Write the failing test**

Add to `app/backend/tests/test_documents.py` (create if missing):

```python
def test_get_single_document(client, auth_headers, sample_document_id):
    """GET /api/documents/{id} returns the document for its owner."""
    res = client.get(f"/api/documents/{sample_document_id}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == sample_document_id

def test_get_document_not_found(client, auth_headers):
    """GET /api/documents/{id} returns 404 for non-existent id."""
    res = client.get("/api/documents/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert res.status_code == 404
```

**Step 2: Run to confirm failure**

```bash
cd app/backend && source venv/bin/activate && pytest tests/test_documents.py::test_get_single_document -v
```

Expected: FAIL — endpoint does not exist yet.

**Step 3: Add the endpoint**

In `app/backend/app/routers/documents.py`, add this route **before** the `/{document_id}/content` route (order matters in FastAPI):

```python
@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    user=Depends(get_current_user),
    sb=Depends(get_supabase_client),
):
    res = (
        sb.table("documents")
        .select("*")
        .eq("id", document_id)
        .eq("user_id", user.id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse(**res.data)
```

**Step 4: Run tests**

```bash
cd app/backend && source venv/bin/activate && pytest tests/test_documents.py -v
```

Expected: all tests pass.

**Step 5: Commit**

```bash
git add app/backend/app/routers/documents.py app/backend/tests/test_documents.py
git commit -m "feat: add GET /api/documents/{id} single document endpoint"
```

---

## Task 3: Create `useDocumentViewer` context hook

**Files:**
- Create: `app/frontend/src/hooks/useDocumentViewer.tsx`

**Step 1: Write the failing test**

Create `app/frontend/src/hooks/__tests__/useDocumentViewer.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest"
import { renderHook, act } from "@testing-library/react"
import { DocumentViewerProvider, useDocumentViewer } from "../useDocumentViewer"
import type { Document } from "@/types"

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <DocumentViewerProvider>{children}</DocumentViewerProvider>
)

const mockDoc: Document = {
  id: "doc-1",
  user_id: "user-1",
  filename: "test.md",
  storage_path: "path/test.md",
  file_type: "md",
  file_size: 1024,
  status: "ready",
  error_message: null,
  chunk_count: 5,
  content_hash: null,
  title: "Test Document",
  summary: null,
  topics: ["testing"],
  document_date: "2024-01-01",
  source_url: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
}

describe("useDocumentViewer", () => {
  it("starts closed with no document", () => {
    const { result } = renderHook(() => useDocumentViewer(), { wrapper })
    expect(result.current.isOpen).toBe(false)
    expect(result.current.viewingDoc).toBeNull()
  })

  it("openDocument sets doc and opens panel", () => {
    const { result } = renderHook(() => useDocumentViewer(), { wrapper })
    act(() => { result.current.openDocument(mockDoc) })
    expect(result.current.isOpen).toBe(true)
    expect(result.current.viewingDoc).toEqual(mockDoc)
  })

  it("closeDocument closes panel", () => {
    const { result } = renderHook(() => useDocumentViewer(), { wrapper })
    act(() => { result.current.openDocument(mockDoc) })
    act(() => { result.current.closeDocument() })
    expect(result.current.isOpen).toBe(false)
  })

  it("throws when used outside provider", () => {
    expect(() => renderHook(() => useDocumentViewer())).toThrow()
  })
})
```

**Step 2: Install test dependency and run to confirm failure**

```bash
cd app/frontend && npm install -D @testing-library/react @testing-library/jest-dom
npx vitest run src/hooks/__tests__/useDocumentViewer.test.tsx
```

Expected: FAIL — module not found.

**Step 3: Create the hook**

```typescript
// app/frontend/src/hooks/useDocumentViewer.tsx
import { createContext, useContext, useState, useCallback, type ReactNode } from "react"
import type { Document } from "@/types"
import { apiFetch } from "@/lib/api"

interface DocumentViewerContextValue {
  viewingDoc: Document | null
  isOpen: boolean
  openDocument: (doc: Document) => void
  openDocumentById: (id: string, fallbackTitle?: string) => Promise<void>
  closeDocument: () => void
}

const DocumentViewerContext = createContext<DocumentViewerContextValue | null>(null)

export function DocumentViewerProvider({ children }: { children: ReactNode }) {
  const [viewingDoc, setViewingDoc] = useState<Document | null>(null)
  const [isOpen, setIsOpen] = useState(false)

  const openDocument = useCallback((doc: Document) => {
    setViewingDoc(doc)
    setIsOpen(true)
  }, [])

  const openDocumentById = useCallback(async (id: string, fallbackTitle?: string) => {
    // Try to fetch full document metadata; fall back to a minimal object
    try {
      const res = await apiFetch(`/api/documents/${id}`)
      if (res.ok) {
        const doc: Document = await res.json()
        setViewingDoc(doc)
        setIsOpen(true)
        return
      }
    } catch {
      // ignore, use fallback
    }
    // Fallback: open with minimal info so content can still be fetched
    setViewingDoc({
      id,
      user_id: "",
      filename: fallbackTitle || "Document",
      storage_path: "",
      file_type: "unknown",
      file_size: 0,
      status: "ready",
      error_message: null,
      chunk_count: 0,
      content_hash: null,
      title: fallbackTitle || null,
      summary: null,
      topics: [],
      document_date: null,
      source_url: null,
      created_at: "",
      updated_at: "",
    } satisfies Document)
    setIsOpen(true)
  }, [])

  const closeDocument = useCallback(() => {
    setIsOpen(false)
    // Delay clearing doc so the close animation can finish
    setTimeout(() => setViewingDoc(null), 250)
  }, [])

  return (
    <DocumentViewerContext.Provider
      value={{ viewingDoc, isOpen, openDocument, openDocumentById, closeDocument }}
    >
      {children}
    </DocumentViewerContext.Provider>
  )
}

export function useDocumentViewer() {
  const ctx = useContext(DocumentViewerContext)
  if (!ctx) throw new Error("useDocumentViewer must be used within DocumentViewerProvider")
  return ctx
}
```

**Step 4: Run tests**

```bash
cd app/frontend && npx vitest run src/hooks/__tests__/useDocumentViewer.test.tsx
```

Expected: all 4 tests pass.

**Step 5: Commit**

```bash
git add app/frontend/src/hooks/useDocumentViewer.tsx app/frontend/src/hooks/__tests__/useDocumentViewer.test.tsx app/frontend/package.json app/frontend/package-lock.json
git commit -m "feat: add DocumentViewerProvider context and useDocumentViewer hook"
```

---

## Task 4: Set up React Router and wire providers in `App.tsx`

**Files:**
- Modify: `app/frontend/src/main.tsx`
- Modify: `app/frontend/src/App.tsx`
- Create: `app/frontend/src/pages/DocumentPage.tsx` (stub — fully implemented in Task 10)

**Step 1: Add BrowserRouter to `main.tsx`**

Read `app/frontend/src/main.tsx`. It will look like:

```typescript
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import "./index.css"
import App from "./App.tsx"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
```

Add the `BrowserRouter` import and wrapper. If it's already similar, just add the missing parts.

**Step 2: Update `App.tsx` — add routes, provider, and layout wrapper**

Replace the return value in `App()`. The authenticated view becomes:

```typescript
import { Routes, Route } from "react-router-dom"
import { DocumentViewerProvider } from "@/hooks/useDocumentViewer"
import { DocumentViewerPanel } from "@/components/documents/DocumentViewerPanel"
import { DocumentPage } from "@/pages/DocumentPage"

// Inside App(), replace the authenticated return:
return (
  <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
    <DocumentViewerProvider>
      <Routes>
        <Route
          path="/documents/:id"
          element={<DocumentPage />}
        />
        <Route
          path="*"
          element={
            <div className="h-screen flex flex-col overflow-hidden">
              <Header
                email={user.email || ""}
                view={view}
                onViewChange={setView}
                onSignOut={signOut}
                breakpoint={breakpoint}
              />
              <div className="flex flex-1 min-h-0 overflow-hidden">
                <div className="flex-1 min-w-0 min-h-0">
                  {view === "chat" ? (
                    <ChatLayout breakpoint={breakpoint} />
                  ) : (
                    <DocumentsLayout />
                  )}
                </div>
                <DocumentViewerPanel />
              </div>
            </div>
          }
        />
      </Routes>
    </DocumentViewerProvider>
  </ThemeProvider>
)
```

**Step 3: Create stub `DocumentPage`**

```typescript
// app/frontend/src/pages/DocumentPage.tsx
export function DocumentPage() {
  return <div className="p-8 text-muted-foreground">Document page — coming soon</div>
}
```

**Step 4: Create stub `DocumentViewerPanel`**

```typescript
// app/frontend/src/components/documents/DocumentViewerPanel.tsx
export function DocumentViewerPanel() {
  return null
}
```

**Step 5: Fix `ChatLayout` height — remove hardcoded `calc(100vh - 3.5rem)`**

In `app/frontend/src/components/layout/ChatLayout.tsx`, find the desktop layout return:

```typescript
// BEFORE:
<div className="relative flex overflow-hidden" style={{ height: `calc(100vh - ${headerHeight})` }}>

// AFTER:
<div className="relative flex overflow-hidden h-full">
```

Also remove the `const headerHeight = "3.5rem"` line.

The parent (`App.tsx`) now controls height via `flex-1 min-h-0`. `ChatLayout` just needs `h-full` or inherits from flex.

**Step 6: Verify app still loads and works**

```bash
cd app/frontend && npm run dev
```

Open `http://localhost:5173` — app should load, chat should work, panels should open/close normally.

**Step 7: Commit**

```bash
git add app/frontend/src/main.tsx app/frontend/src/App.tsx app/frontend/src/components/layout/ChatLayout.tsx app/frontend/src/pages/DocumentPage.tsx app/frontend/src/components/documents/DocumentViewerPanel.tsx
git commit -m "feat: add React Router, DocumentViewerProvider, layout wrapper for viewer panel"
```

---

## Task 5: Create `DocumentViewerContent` shared component

**Files:**
- Create: `app/frontend/src/components/documents/DocumentViewerContent.tsx`

This is the unified template used by both the inline panel and the full-screen page.

**Step 1: Create the component**

```typescript
// app/frontend/src/components/documents/DocumentViewerContent.tsx
import { useMemo } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { ExternalLink, FileText, Loader2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { Document } from "@/types"

const FILE_TYPE_LABELS: Record<string, string> = {
  pdf: "PDF", docx: "DOCX", txt: "TXT", md: "MD",
  csv: "CSV", html: "HTML", unknown: "DOC",
}

interface TocEntry {
  level: number
  text: string
  id: string
}

function buildToc(content: string): TocEntry[] {
  const lines = content.split("\n")
  const entries: TocEntry[] = []
  const seen: Record<string, number> = {}
  for (const line of lines) {
    const match = line.match(/^(#{1,3})\s+(.+)/)
    if (!match) continue
    const level = match[1].length
    const text = match[2].trim()
    const base = text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
    const id = seen[base] ? `${base}-${seen[base]++}` : base
    seen[base] = seen[base] ? seen[base] : 1
    entries.push({ level, text, id })
  }
  return entries
}

interface DocumentViewerContentProps {
  document: Document
  content: string
  loading: boolean
  error: string | null
  /** Show "Open full view ↗" button — true in the inline panel, false on the full-screen page */
  showOpenFullView?: boolean
  /** Render ToC in a separate aside column (for full-screen layout) vs sticky within scroll area */
  tocMode?: "inline" | "aside"
}

export function DocumentViewerContent({
  document,
  content,
  loading,
  error,
  showOpenFullView = true,
  tocMode = "inline",
}: DocumentViewerContentProps) {
  const toc = useMemo(() => (content ? buildToc(content) : []), [content])
  const displayTitle = document.title || document.filename

  return (
    <div className="flex flex-col h-full">
      {/* Metadata header */}
      <div className="shrink-0 border-b px-4 py-3 space-y-1.5">
        <div className="flex items-start gap-2">
          <Badge variant="secondary" className="shrink-0 mt-0.5 text-xs font-mono uppercase">
            {FILE_TYPE_LABELS[document.file_type] ?? document.file_type}
          </Badge>
          <h2 className="flex-1 text-sm font-semibold leading-tight line-clamp-2">{displayTitle}</h2>
          {showOpenFullView && (
            <a
              href={`/documents/${document.id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              title="Open full view"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Full view</span>
            </a>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {document.document_date && <span>{document.document_date}</span>}
          {document.source_url && (
            <a
              href={document.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 hover:text-foreground transition-colors truncate max-w-[200px]"
            >
              <ExternalLink className="h-3 w-3 shrink-0" />
              <span className="truncate">{new URL(document.source_url).hostname}</span>
            </a>
          )}
        </div>
        {document.topics && document.topics.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {document.topics.map((t) => (
              <Badge key={t} variant="outline" className="text-xs px-1.5 py-0">
                {t}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Body */}
      <div className={`flex flex-1 min-h-0 ${tocMode === "aside" ? "flex-row" : "flex-col"}`}>
        {/* ToC — aside mode (full-screen page) */}
        {tocMode === "aside" && toc.length > 0 && (
          <nav className="w-48 shrink-0 border-r p-4 overflow-y-auto text-xs space-y-1">
            <p className="font-semibold mb-2 text-foreground">Contents</p>
            {toc.map((entry) => (
              <a
                key={entry.id}
                href={`#${entry.id}`}
                className="block text-muted-foreground hover:text-foreground transition-colors truncate"
                style={{ paddingLeft: `${(entry.level - 1) * 12}px` }}
              >
                {entry.text}
              </a>
            ))}
          </nav>
        )}

        <ScrollArea className="flex-1">
          <div className="p-4">
            {/* ToC — inline mode (panel) */}
            {tocMode === "inline" && toc.length > 2 && (
              <nav className="mb-4 rounded-md border bg-muted/40 p-3 text-xs space-y-1">
                <p className="font-semibold mb-1.5 text-foreground">Contents</p>
                {toc.map((entry) => (
                  <a
                    key={entry.id}
                    href={`#${entry.id}`}
                    className="block text-muted-foreground hover:text-foreground transition-colors"
                    style={{ paddingLeft: `${(entry.level - 1) * 12}px` }}
                  >
                    {entry.text}
                  </a>
                ))}
              </nav>
            )}

            {/* Content states */}
            {loading && (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="size-5 animate-spin text-muted-foreground" />
              </div>
            )}
            {error && (
              <p className="text-sm text-destructive py-4">{error}</p>
            )}
            {!loading && !error && content && (
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    // Add id anchors to headings for ToC navigation
                    h1: ({ children, ...props }) => {
                      const id = String(children).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
                      return <h1 id={id} {...props}>{children}</h1>
                    },
                    h2: ({ children, ...props }) => {
                      const id = String(children).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
                      return <h2 id={id} {...props}>{children}</h2>
                    },
                    h3: ({ children, ...props }) => {
                      const id = String(children).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
                      return <h3 id={id} {...props}>{children}</h3>
                    },
                  }}
                >
                  {content}
                </ReactMarkdown>
              </div>
            )}
            {!loading && !error && !content && (
              <div className="flex flex-col items-center justify-center py-16 gap-2 text-muted-foreground">
                <FileText className="size-8 opacity-40" />
                <p className="text-sm">No content available</p>
              </div>
            )}
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}
```

**Step 2: Type-check**

```bash
cd app/frontend && npx tsc --noEmit 2>&1 | grep -i error | head -20
```

Expected: no new type errors.

**Step 3: Commit**

```bash
git add app/frontend/src/components/documents/DocumentViewerContent.tsx
git commit -m "feat: add DocumentViewerContent shared component (metadata header, markdown, ToC)"
```

---

## Task 6: Implement `DocumentViewerPanel` (tier 1 inline panel)

**Files:**
- Modify: `app/frontend/src/components/documents/DocumentViewerPanel.tsx`

**Step 1: Replace the stub**

```typescript
// app/frontend/src/components/documents/DocumentViewerPanel.tsx
import { useEffect, useState } from "react"
import { X } from "lucide-react"
import { apiFetch } from "@/lib/api"
import { useDocumentViewer } from "@/hooks/useDocumentViewer"
import { useBreakpoint } from "@/hooks/useBreakpoint"
import { DocumentViewerContent } from "./DocumentViewerContent"
import { Scrim } from "@/components/chat/Scrim"

export function DocumentViewerPanel() {
  const { viewingDoc, isOpen, closeDocument } = useDocumentViewer()
  const breakpoint = useBreakpoint()
  const isMobile = breakpoint === "mobile"

  const [content, setContent] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch content when document changes
  useEffect(() => {
    if (!viewingDoc) {
      setContent("")
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    setContent("")

    apiFetch(`/api/documents/${viewingDoc.id}/content`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.text()
      })
      .then((text) => { if (!cancelled) setContent(text) })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [viewingDoc?.id])

  if (isMobile) {
    // Bottom drawer — always in DOM for smooth animation
    return (
      <>
        <Scrim visible={isOpen} onClick={closeDocument} />
        <div
          className="fixed bottom-0 inset-x-0 z-40 flex flex-col bg-background border-t shadow-2xl rounded-t-xl"
          style={{
            height: "78vh",
            transform: isOpen ? "translateY(0)" : "translateY(100%)",
            transition: "transform 200ms ease-in-out",
          }}
        >
          <div className="flex items-center justify-between px-4 py-2 border-b shrink-0">
            <div className="mx-auto w-10 h-1 rounded-full bg-muted-foreground/30" />
            <button
              onClick={closeDocument}
              className="ml-auto p-1 rounded hover:bg-accent transition-colors"
              aria-label="Close document viewer"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          {viewingDoc && (
            <div className="flex-1 min-h-0 overflow-hidden">
              <DocumentViewerContent
                document={viewingDoc}
                content={content}
                loading={loading}
                error={error}
                showOpenFullView
                tocMode="inline"
              />
            </div>
          )}
        </div>
      </>
    )
  }

  // Desktop / tablet — flex column in the app layout row
  return (
    <div
      className="shrink-0 border-l bg-background flex flex-col overflow-hidden"
      style={{
        width: isOpen ? "40%" : "0",
        transition: "width 200ms ease-in-out",
      }}
    >
      {/* Close button */}
      <div className="flex items-center justify-between px-3 py-2 border-b shrink-0">
        <span className="text-xs text-muted-foreground font-medium uppercase tracking-wide">Document</span>
        <button
          onClick={closeDocument}
          className="p-1 rounded hover:bg-accent transition-colors"
          aria-label="Close document viewer"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      {viewingDoc && (
        <div className="flex-1 min-h-0 overflow-hidden">
          <DocumentViewerContent
            document={viewingDoc}
            content={content}
            loading={loading}
            error={error}
            showOpenFullView
            tocMode="inline"
          />
        </div>
      )}
    </div>
  )
}
```

**Step 2: Type-check**

```bash
cd app/frontend && npx tsc --noEmit 2>&1 | grep -i error | head -20
```

Expected: no errors.

**Step 3: Smoke test in browser**

Start dev server, open the app. The panel shouldn't appear yet (nothing triggers it). No visual regressions.

**Step 4: Commit**

```bash
git add app/frontend/src/components/documents/DocumentViewerPanel.tsx
git commit -m "feat: implement DocumentViewerPanel (desktop column + mobile bottom drawer)"
```

---

## Task 7: Update `DocumentsPanel` — remove old modal, use context hook

**Files:**
- Modify: `app/frontend/src/components/documents/DocumentsPanel.tsx`
- Delete: `app/frontend/src/components/documents/DocumentViewer.tsx`

**Step 1: Update `DocumentsPanel.tsx`**

1. Remove `import { DocumentViewer } from "@/components/documents/DocumentViewer"`
2. Add `import { useDocumentViewer } from "@/hooks/useDocumentViewer"`
3. Remove `const [viewingDoc, setViewingDoc] = useState<Document | null>(null)`
4. In the component body, add: `const { openDocument } = useDocumentViewer()`
5. Replace every `setViewingDoc(doc)` call with `openDocument(doc)`
6. Remove the `<DocumentViewer document={viewingDoc} open={viewingDoc !== null} onClose={() => setViewingDoc(null)} />` JSX at the bottom of the return

The trigger points to update are:
- Eye icon button: `onClick={() => openDocument(doc)}`
- Document title click: `onClick={() => doc.status === "ready" && openDocument(doc)}`

**Step 2: Delete old viewer**

```bash
rm app/frontend/src/components/documents/DocumentViewer.tsx
```

**Step 3: Type-check**

```bash
cd app/frontend && npx tsc --noEmit 2>&1 | grep -i error | head -20
```

Expected: no errors.

**Step 4: Manual test**

In the browser, go to Documents view. Click the eye icon on a ready document. The new panel should slide in on desktop (right column) / slide up on mobile (bottom drawer). Verify metadata header shows title, badge, topics.

**Step 5: Commit**

```bash
git add app/frontend/src/components/documents/DocumentsPanel.tsx
git rm app/frontend/src/components/documents/DocumentViewer.tsx
git commit -m "feat: migrate DocumentsPanel to use DocumentViewerPanel, remove old modal viewer"
```

---

## Task 8: Wire document viewer to chat citations in `RightPanel`

**Files:**
- Modify: `app/frontend/src/components/chat/RightPanel.tsx`

**Step 1: Read the full `RightPanel.tsx`**

Read the file to find the citations rendering code — specifically where `usedSources` are rendered as a list.

**Step 2: Update citations to open viewer**

1. Add: `import { useDocumentViewer } from "@/hooks/useDocumentViewer"`
2. Inside the component: `const { openDocumentById } = useDocumentViewer()`
3. Find the citation item rendering. Each `CitationSource` has `document_id` and `doc_title`. Make the citation item clickable:

```typescript
// Find the section rendering each source/citation
// Wrap it with onClick (or add a button):
<button
  key={source.chunk_id}
  onClick={() => openDocumentById(source.document_id, source.doc_title)}
  className="w-full text-left rounded-md border p-3 text-xs hover:bg-accent transition-colors space-y-1"
>
  <div className="font-medium truncate">{source.doc_title}</div>
  <div className="text-muted-foreground line-clamp-2">{source.content_preview}</div>
  <div className="text-muted-foreground">Score: {source.score.toFixed(3)}</div>
</button>
```

Adapt the exact markup to match the existing citation card style.

**Step 3: Type-check**

```bash
cd app/frontend && npx tsc --noEmit 2>&1 | grep -i error | head -20
```

**Step 4: Manual test**

Send a message that retrieves RAG sources. Open the right panel (Sources tab). Click a citation — the document viewer panel should slide open on the right with the document content.

**Step 5: Commit**

```bash
git add app/frontend/src/components/chat/RightPanel.tsx
git commit -m "feat: citation click in RightPanel opens DocumentViewerPanel"
```

---

## Task 9: Implement `DocumentPage` (tier 2 full-screen route)

**Files:**
- Modify: `app/frontend/src/pages/DocumentPage.tsx`

**Step 1: Replace the stub with the full implementation**

```typescript
// app/frontend/src/pages/DocumentPage.tsx
import { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { ArrowLeft, Pencil } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ThemeProvider } from "next-themes"
import { useAuth } from "@/hooks/useAuth"
import { LoginForm } from "@/components/auth/LoginForm"
import { SignUpForm } from "@/components/auth/SignUpForm"
import { EditMetadataModal } from "@/components/documents/EditMetadataModal"
import { DocumentViewerContent } from "@/components/documents/DocumentViewerContent"
import { apiFetch } from "@/lib/api"
import type { Document } from "@/types"

export function DocumentPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user, loading: authLoading, signIn, signUp } = useAuth()
  const [isSignUp, setIsSignUp] = useState(false)

  const [doc, setDoc] = useState<Document | null>(null)
  const [content, setContent] = useState("")
  const [docLoading, setDocLoading] = useState(true)
  const [contentLoading, setContentLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingDoc, setEditingDoc] = useState<Document | null>(null)

  useEffect(() => {
    if (!id || !user) return
    let cancelled = false

    // Fetch document metadata
    apiFetch(`/api/documents/${id}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Document not found (HTTP ${res.status})`)
        return res.json() as Promise<Document>
      })
      .then((d) => { if (!cancelled) { setDoc(d); setDocLoading(false) } })
      .catch((err) => { if (!cancelled) { setError(err.message); setDocLoading(false) } })

    // Fetch content
    apiFetch(`/api/documents/${id}/content`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.text()
      })
      .then((text) => { if (!cancelled) { setContent(text); setContentLoading(false) } })
      .catch(() => { if (!cancelled) setContentLoading(false) })

    return () => { cancelled = true }
  }, [id, user])

  const handleUpdate = async (docId: string, updates: Partial<Pick<Document, "title" | "summary" | "topics" | "document_date">>) => {
    const res = await apiFetch(`/api/documents/${docId}`, {
      method: "PATCH",
      body: JSON.stringify(updates),
    })
    if (!res.ok) throw new Error("Update failed")
    const updated: Document = await res.json()
    setDoc(updated)
    return updated
  }

  // Auth loading
  if (authLoading) {
    return (
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <div className="flex h-screen items-center justify-center">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </ThemeProvider>
    )
  }

  // Not authenticated — show login
  if (!user) {
    return (
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <div className="flex h-screen items-center justify-center">
          {isSignUp ? (
            <SignUpForm onSignUp={signUp} onToggle={() => setIsSignUp(false)} />
          ) : (
            <LoginForm onSignIn={signIn} onToggle={() => setIsSignUp(true)} />
          )}
        </div>
      </ThemeProvider>
    )
  }

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <div className="h-screen flex flex-col bg-background text-foreground">
        {/* Page header */}
        <header className="shrink-0 flex items-center gap-3 border-b px-4 py-3">
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="gap-1">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <h1 className="flex-1 text-sm font-semibold truncate">
            {doc ? (doc.title || doc.filename) : "Loading…"}
          </h1>
          {doc && (
            <Button variant="ghost" size="sm" onClick={() => setEditingDoc(doc)} className="gap-1">
              <Pencil className="h-3.5 w-3.5" />
              Edit metadata
            </Button>
          )}
        </header>

        {/* Three-column body (desktop) / stacked (mobile) */}
        <div className="flex flex-1 min-h-0">
          {error ? (
            <div className="flex flex-1 items-center justify-center p-8">
              <p className="text-sm text-destructive">{error}</p>
            </div>
          ) : doc ? (
            <>
              {/* Metadata sidebar (desktop only) */}
              <aside className="hidden lg:flex w-56 shrink-0 border-r flex-col p-4 gap-3 text-xs text-muted-foreground overflow-y-auto">
                <div>
                  <p className="font-semibold text-foreground mb-1">File</p>
                  <p className="break-all">{doc.filename}</p>
                </div>
                {doc.document_date && (
                  <div>
                    <p className="font-semibold text-foreground mb-1">Date</p>
                    <p>{doc.document_date}</p>
                  </div>
                )}
                {doc.topics && doc.topics.length > 0 && (
                  <div>
                    <p className="font-semibold text-foreground mb-1">Topics</p>
                    <div className="flex flex-wrap gap-1">
                      {doc.topics.map((t) => (
                        <span key={t} className="rounded bg-muted px-1.5 py-0.5">{t}</span>
                      ))}
                    </div>
                  </div>
                )}
                {doc.chunk_count > 0 && (
                  <div>
                    <p className="font-semibold text-foreground mb-1">Chunks</p>
                    <p>{doc.chunk_count}</p>
                  </div>
                )}
                {doc.file_size > 0 && (
                  <div>
                    <p className="font-semibold text-foreground mb-1">Size</p>
                    <p>{doc.file_size < 1024 * 1024
                      ? `${(doc.file_size / 1024).toFixed(1)} KB`
                      : `${(doc.file_size / (1024 * 1024)).toFixed(1)} MB`}
                    </p>
                  </div>
                )}
                {doc.summary && (
                  <div>
                    <p className="font-semibold text-foreground mb-1">Summary</p>
                    <p className="leading-relaxed">{doc.summary}</p>
                  </div>
                )}
              </aside>

              {/* Main content — DocumentViewerContent with aside ToC */}
              <div className="flex-1 min-w-0 min-h-0 overflow-hidden">
                <DocumentViewerContent
                  document={doc}
                  content={content}
                  loading={contentLoading}
                  error={null}
                  showOpenFullView={false}
                  tocMode="aside"
                />
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center">
              <p className="text-muted-foreground text-sm">Loading document…</p>
            </div>
          )}
        </div>

        {/* Edit metadata modal */}
        {editingDoc && (
          <EditMetadataModal
            document={editingDoc}
            open
            onClose={() => setEditingDoc(null)}
            onSave={(updates) => handleUpdate(editingDoc.id, updates)}
          />
        )}
      </div>
    </ThemeProvider>
  )
}
```

**Step 2: Type-check**

```bash
cd app/frontend && npx tsc --noEmit 2>&1 | grep -i error | head -20
```

Expected: no errors.

**Step 3: Manual test — full-screen page**

1. Open a document in the inline panel (Documents view, click eye icon)
2. Click "Full view ↗" button → new tab opens at `http://localhost:5173/documents/<id>`
3. Verify: Back button works, three-column layout (desktop), metadata sidebar shows date/topics/chunks, markdown rendered, ToC on left
4. Verify: navigating directly to the URL (copy/paste) works — auth check shows login if not signed in

**Step 4: Commit**

```bash
git add app/frontend/src/pages/DocumentPage.tsx
git commit -m "feat: implement full-screen DocumentPage at /documents/:id"
```

---

## Task 10: Final validation

**Step 1: Run type-check across the whole frontend**

```bash
cd app/frontend && npx tsc --noEmit
```

Expected: zero errors.

**Step 2: Run all frontend tests**

```bash
cd app/frontend && npx vitest run
```

Expected: all tests pass.

**Step 3: Run backend tests**

```bash
cd app/backend && source venv/bin/activate && pytest -v
```

Expected: all tests pass, including the new `test_get_single_document` test.

**Step 4: End-to-end walkthrough checklist**

- [ ] Open Documents view → click eye icon → inline panel slides in (desktop) or draws up (mobile)
- [ ] Inline panel shows: file type badge, title, date, topics, source URL (for web docs)
- [ ] Markdown is rendered (headings, tables, lists — not raw text)
- [ ] ToC appears for documents with 3+ headings; clicking a ToC link scrolls to that heading
- [ ] Click "Full view ↗" → `/documents/:id` opens in new tab
- [ ] Full-screen page: Back button returns to previous page
- [ ] Full-screen page: three-column layout (ToC | content | metadata sidebar) on desktop
- [ ] Full-screen page: "Edit metadata" button opens modal; save updates doc title/topics
- [ ] Open chat, send message with RAG sources → right panel shows Sources tab → click a citation → inline panel opens with that document
- [ ] Close inline panel → chat returns to full width with transition
- [ ] Paste `/documents/:id` URL in new tab without auth → login form appears

**Step 5: Update PROGRESS.md**

Mark the KB viewer polish item as done:

```markdown
- [x] **KB viewer polish:** Unified viewer experience for file docs + web docs (title, source link, extracted text, metadata).
```

**Step 6: Final commit**

```bash
git add PROGRESS.md
git commit -m "docs: mark KB viewer polish complete in PROGRESS.md"
```

---

## Summary of all changed files

| File | Action |
|------|--------|
| `app/frontend/src/main.tsx` | Add `BrowserRouter` wrapper |
| `app/frontend/src/App.tsx` | Add routes, `DocumentViewerProvider`, layout wrapper |
| `app/frontend/src/components/layout/ChatLayout.tsx` | Remove hardcoded height, use `h-full` |
| `app/frontend/src/components/documents/DocumentViewerContent.tsx` | **New** — shared content component |
| `app/frontend/src/components/documents/DocumentViewerPanel.tsx` | **New** — tier 1 inline panel |
| `app/frontend/src/components/documents/DocumentsPanel.tsx` | Use `openDocument` hook, remove modal state |
| `app/frontend/src/components/chat/RightPanel.tsx` | Citation click → `openDocumentById` |
| `app/frontend/src/pages/DocumentPage.tsx` | **New** — tier 2 full-screen route |
| `app/frontend/src/hooks/useDocumentViewer.tsx` | **New** — context + hook |
| `app/frontend/src/components/documents/DocumentViewer.tsx` | **Deleted** |
| `app/backend/app/routers/documents.py` | Add `GET /{document_id}` endpoint |
| `app/frontend/package.json` | Add `react-router-dom`, `react-markdown`, `remark-gfm`, `@testing-library/react` |
