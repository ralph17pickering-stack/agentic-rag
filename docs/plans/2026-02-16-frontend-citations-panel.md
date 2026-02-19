# Frontend Citations Panel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Display document citations (retrieved RAG chunks) in the RightPanel, alongside the existing web results panel, using separate edge handles to open each.

**Architecture:** Single `RightPanel` component gains a `mode` state (`"citations" | "web-results"`). Two edge handles (book icon for citations, globe for web results) each open the panel in their mode. `useChat` is extended to track `usedSources` from SSE events and message history. `ChatLayout` wires the new state into the panel and auto-opens on new citations.

**Tech Stack:** React + TypeScript, Tailwind CSS, lucide-react icons, existing shadcn/ui components

---

### Task 1: Add `CitationSource` type and update `Message` type

**Files:**
- Modify: `app/frontend/src/types/index.ts`

**Step 1: Add the type**

Open `app/frontend/src/types/index.ts` and make these two changes:

1. Add `CitationSource` interface after `WebResult`:

```typescript
export interface CitationSource {
  chunk_id: string
  document_id: string
  doc_title: string
  chunk_index: number
  content_preview: string
  score: number
}
```

2. Add `used_sources` to the `Message` interface (after `web_results`):

```typescript
used_sources?: CitationSource[] | null
```

**Step 2: Verify TypeScript is happy**

```bash
cd /home/ralph/dev/agentic-rag/frontend && npx tsc --noEmit 2>&1
```

Expected: no errors (no code is using the new type yet)

**Step 3: Commit**

```bash
git add app/frontend/src/types/index.ts
git commit -m "feat: add CitationSource type and used_sources to Message"
```

---

### Task 2: Update `useChat` to track `used_sources`

**Files:**
- Modify: `app/frontend/src/hooks/useChat.ts`

**Step 1: Add `usedSources` state**

At the top of the `useChat` function body (after `usedDeepAnalysis`), add:

```typescript
const [usedSources, setUsedSources] = useState<CitationSource[]>([])
```

Also add the import at the top of the file:

```typescript
import type { Message, WebResult, CitationSource } from "@/types"
```

**Step 2: Reset `usedSources` when sending a message**

In `sendMessage`, alongside `setWebResults([])` and `setDeepAnalysisPhase(null)`, add:

```typescript
setUsedSources([])
```

**Step 3: Handle `used_sources` SSE events**

In the SSE parsing loop (inside the `for (const line of lines)` block), after the `web_results` handler:

```typescript
if (data.used_sources) {
  setUsedSources(prev => [...prev, ...data.used_sources])
}
```

Note: deduplication happens on the backend before the `done` event; streaming events may have per-call sources. We accumulate and let the `done` message replace with the authoritative deduplicated list.

**Step 4: On `done`, replace with authoritative `used_sources`**

Inside the `if (data.done)` block, after `setMessages(prev => [...prev, data.message])`, add:

```typescript
if (data.message?.used_sources) {
  setUsedSources(data.message.used_sources)
} else {
  setUsedSources([])
}
```

**Step 5: Restore `usedSources` on thread load**

In `fetchMessages`, after the `setWebResults(lastWithResults?.web_results ?? [])` line, add:

```typescript
const lastWithSources = [...data].reverse().find(
  m => m.role === "assistant" && m.used_sources && m.used_sources.length > 0
)
setUsedSources(lastWithSources?.used_sources ?? [])
```

**Step 6: Expose `usedSources` from the hook**

Add `usedSources` to the return object:

```typescript
return {
  messages,
  isStreaming,
  streamingContent,
  loading,
  webResults,
  usedSources,
  deepAnalysisPhase,
  usedDeepAnalysis,
  fetchMessages,
  sendMessage,
  setMessages,
  clearMessages,
}
```

**Step 7: Typecheck**

```bash
cd /home/ralph/dev/agentic-rag/frontend && npx tsc --noEmit 2>&1
```

Expected: no errors

**Step 8: Commit**

```bash
git add app/frontend/src/hooks/useChat.ts
git commit -m "feat: track used_sources in useChat — SSE + history restore"
```

---

### Task 3: Extend `RightPanel` with mode, two handles, and citations content

**Files:**
- Modify: `app/frontend/src/components/chat/RightPanel.tsx`

**Step 1: Update imports**

Replace the current imports with:

```typescript
import { useState } from "react"
import { X, Globe, BookOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { apiFetch } from "@/lib/api"
import type { WebResult, CitationSource } from "@/types"
import type { RightPanelState } from "@/hooks/usePanelState"
```

**Step 2: Update props interface**

Replace `RightPanelProps` with:

```typescript
type PanelMode = "citations" | "web-results"

interface RightPanelProps {
  results: WebResult[]
  usedSources: CitationSource[]
  state: RightPanelState
  onClose: () => void
  onOpen: (mode: PanelMode) => void
}
```

**Step 3: Add `mode` state and update function signature**

Replace the function signature and add state:

```typescript
export function RightPanel({ results, usedSources, state, onClose, onOpen }: RightPanelProps) {
  const [saving, setSaving] = useState<Record<string, "loading" | "saved" | "error">>({})
  const [mode, setMode] = useState<PanelMode>("citations")
```

**Step 4: Update `isOpen` and `hasResults` logic**

Replace the two const declarations at the bottom of the existing logic:

```typescript
const isOpen = state === "open-overlay"
const hasWebResults = results.length > 0
const hasCitations = usedSources.length > 0
```

**Step 5: Update `handleSave` — no changes needed** (still works the same)

**Step 6: Replace the JSX entirely**

Replace everything from `return (` to the closing `</>` with:

```tsx
return (
  <>
    {/* Citations edge handle — visible when closed with citations */}
    {!isOpen && hasCitations && (
      <button
        onClick={() => { setMode("citations"); onOpen("citations") }}
        className="fixed right-0 z-20 rounded-l-md border border-r-0 bg-background px-2 py-3 text-xs font-medium shadow-md hover:bg-accent transition-colors"
        style={{ top: "calc(50% - 3.5rem)" }}
        title="Show citations"
      >
        <BookOpen className="mx-auto mb-1 h-4 w-4" />
        <span className="[writing-mode:vertical-lr] text-[10px]">Sources ({usedSources.length})</span>
      </button>
    )}

    {/* Web results edge handle — visible when closed with results */}
    {!isOpen && hasWebResults && (
      <button
        onClick={() => { setMode("web-results"); onOpen("web-results") }}
        className="fixed right-0 z-20 rounded-l-md border border-r-0 bg-background px-2 py-3 text-xs font-medium shadow-md hover:bg-accent transition-colors"
        style={{ top: hasCitations ? "calc(50% + 1rem)" : "50%", transform: "translateY(-50%)" }}
        title="Show web results"
      >
        <Globe className="mx-auto mb-1 h-4 w-4" />
        <span className="[writing-mode:vertical-lr] text-[10px]">Results ({results.length})</span>
      </button>
    )}

    {/* Sliding panel */}
    <div
      className={`absolute right-0 top-0 z-30 flex h-full w-80 shrink-0 flex-col overflow-hidden border-l bg-background shadow-lg transition-transform duration-200 ${
        isOpen ? "translate-x-0" : "translate-x-full"
      }`}
      style={{ transitionTimingFunction: isOpen ? "ease-out" : "ease-in" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-2">
        <div className="flex items-center gap-2">
          {hasCitations && hasWebResults ? (
            <>
              <button
                onClick={() => setMode("citations")}
                className={`text-sm font-medium transition-colors ${mode === "citations" ? "text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              >
                Sources
              </button>
              <span className="text-muted-foreground text-xs">/</span>
              <button
                onClick={() => setMode("web-results")}
                className={`text-sm font-medium transition-colors ${mode === "web-results" ? "text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              >
                Web
              </button>
            </>
          ) : (
            <h3 className="text-sm font-medium">{mode === "citations" ? "Sources" : "Web Results"}</h3>
          )}
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {mode === "citations" && (
          <div className="p-3 space-y-3">
            {usedSources.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center py-4">No sources for this response</p>
            ) : (
              usedSources.map((source, i) => (
                <div key={source.chunk_id ?? i} className="overflow-hidden rounded-md border bg-card p-3 space-y-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium line-clamp-2 leading-snug">{source.doc_title}</p>
                    <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {Math.round(source.score * 100)}%
                    </span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">Chunk {source.chunk_index + 1}</p>
                  <p className="text-xs text-muted-foreground line-clamp-4 break-words">{source.content_preview}</p>
                </div>
              ))
            )}
          </div>
        )}

        {mode === "web-results" && (
          <div className="p-3 space-y-3">
            {results.map((r, i) => (
              <div key={i} className="overflow-hidden rounded-md border bg-card p-3 space-y-2">
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-sm font-medium text-primary hover:underline line-clamp-2 break-all"
                >
                  {r.title || r.url}
                </a>
                {r.snippet && (
                  <p className="text-xs text-muted-foreground line-clamp-3 break-words">{r.snippet}</p>
                )}
                <p className="text-xs text-muted-foreground truncate">{r.url}</p>
                <Button
                  size="sm"
                  variant="outline"
                  className="w-full h-7 text-xs"
                  disabled={saving[r.url] === "loading" || saving[r.url] === "saved"}
                  onClick={() => handleSave(r)}
                >
                  {saving[r.url] === "loading"
                    ? "Saving..."
                    : saving[r.url] === "saved"
                      ? "Saved"
                      : saving[r.url] === "error"
                        ? "Retry Save"
                        : "Save to KB"}
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  </>
)
```

**Step 7: Typecheck**

```bash
cd /home/ralph/dev/agentic-rag/frontend && npx tsc --noEmit 2>&1
```

Expected: errors about `onOpen` call signature mismatch in `ChatLayout.tsx` (that's fine — we fix it next)

**Step 8: Commit**

```bash
git add app/frontend/src/components/chat/RightPanel.tsx
git commit -m "feat: citations panel — mode state, dual edge handles, citations content"
```

---

### Task 4: Wire `usedSources` into `ChatLayout` and fix `onOpen` call site

**Files:**
- Modify: `app/frontend/src/components/chat/ChatLayout.tsx`

**Step 1: Destructure `usedSources` from `useChat`**

In the `useChat(...)` destructuring, add `usedSources`:

```typescript
const {
  messages,
  isStreaming,
  streamingContent,
  fetchMessages,
  sendMessage,
  setMessages,
  clearMessages,
  webResults,
  usedSources,
  deepAnalysisPhase,
  usedDeepAnalysis,
} = useChat(activeThreadId, updateThreadTitle)
```

**Step 2: Update `openRightPanel` call to pass mode**

The `onOpen` prop now takes a `PanelMode` argument. `usePanelState`'s `openRightPanel` doesn't need a mode argument (mode is internal to `RightPanel`). Just update the `RightPanel` JSX prop:

Change:
```typescript
onOpen={openRightPanel}
```
To:
```typescript
onOpen={() => openRightPanel()}
```

**Step 3: Pass `usedSources` to `RightPanel`**

In the desktop/tablet `<RightPanel ...>` call, add:

```tsx
<RightPanel
  results={webResults}
  usedSources={usedSources}
  state={rightPanel}
  onClose={closeRightPanel}
  onOpen={() => openRightPanel()}
/>
```

**Step 4: Auto-open panel when citations arrive (like web results)**

The existing `useEffect` auto-opens for web results. Add a parallel effect for citations. Add after the existing web results effect:

```typescript
const prevSourcesLen = useRef(0)

useEffect(() => {
  if (usedSources.length > 0 && usedSources.length !== prevSourcesLen.current) {
    if (breakpoint !== "mobile") {
      openRightPanel()
    }
  }
  prevSourcesLen.current = usedSources.length
}, [usedSources, breakpoint, openRightPanel])
```

**Step 5: Typecheck**

```bash
cd /home/ralph/dev/agentic-rag/frontend && npx tsc --noEmit 2>&1
```

Expected: no errors

**Step 6: Commit**

```bash
git add app/frontend/src/components/chat/ChatLayout.tsx
git commit -m "feat: wire usedSources into ChatLayout — auto-open citations panel"
```

---

### Task 5: Browser validation

**Start the dev servers if not running:**

```bash
# Terminal 1: backend
cd /home/ralph/dev/agentic-rag && source app/backapp/frontend/venv/bin/activate && uvicorn app.main:app --reload --port 8001 --app-dir backend

# Terminal 2: frontend
cd /home/ralph/dev/agentic-rag/frontend && npm run dev
```

**Navigate to:** http://localhost:5173

**Login with test credentials:** `test@agentic-rag.dev` / `TestPass123!`

**Test scenario 1 — Citations panel appears after RAG response:**
1. Start a chat that triggers document retrieval (ask something about an uploaded doc)
2. Verify: a `BookOpen` edge handle appears on the right side after the response
3. Click it — panel slides in showing "Sources" with document title, chunk number, preview, and score %
4. Verify each citation card shows: title, "Chunk N", content preview, score badge

**Test scenario 2 — Web results + citations coexist:**
1. Ask a question that triggers both web search and doc retrieval
2. Verify: both edge handles appear (stacked)
3. Click citations handle → shows Sources view
4. Click web results handle → panel switches to Web Results view
5. When panel is open with both: "Sources / Web" switcher appears in the header

**Test scenario 3 — Thread load restores citations:**
1. Refresh the page
2. Navigate back to the thread with citations
3. Verify: the edge handle reappears with the correct source count

**Test scenario 4 — Panel closes/opens correctly:**
1. Click the X button → panel closes, edge handles reappear
2. Press Escape → panel closes

---

### Task 6: Update PROGRESS.md

**Files:**
- Modify: `PROGRESS.md`

Find and update the right-panel citations (docs) line:

```
- [ ] **Right panel citations (docs):** When chat uses RAG file info, show linked sources in the right-hand panel (doc → chunk anchors).
```

Change to:

```
- [x] **Right panel citations (docs):** When chat uses RAG file info, show linked sources in the right-hand panel (doc → chunk anchors).
```

**Commit:**

```bash
git add PROGRESS.md
git commit -m "docs: mark right panel citations (docs) as complete"
```
