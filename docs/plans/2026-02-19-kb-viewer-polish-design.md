# KB Viewer Polish — Design

**Date:** 2026-02-19
**Status:** Approved
**Phase:** 3 (Knowledge base readability parity)

## Problem

The current `DocumentViewer` is a plain modal dialog that renders raw text in a `<pre>` block. It:
- Has no consistent layout between file docs and web docs
- Shows no metadata (title, date, topics, source URL)
- Is inaccessible from the chat view
- Has no navigation for long documents
- Blocks the chat entirely when open

## Goals

1. **Unified template** — one consistent layout for all document types (file + web)
2. **In-chat access** — view a document alongside the chat without losing context
3. **Full-screen view** — a dedicated page for deep document interaction, shareable via URL
4. **Long doc navigation** — table of contents auto-generated from headings
5. **Rich metadata display** — title, date, topics, source prominently shown

## Architecture: Two-Tier Viewer

Both tiers share a single `DocumentViewerContent` component, ensuring the unified layout is written once.

```
┌─────────────────────────────────────────────────┐
│  DocumentViewerContent  (shared, stateless)     │
│  - Unified metadata header                      │
│  - Markdown body renderer                        │
│  - Sticky ToC (generated from headings)         │
│  - "Open full view ↗" button                    │
└───────────────┬─────────────────────────────────┘
                │
     ┌──────────┴──────────┐
     ▼                     ▼
DocumentViewerPanel    /documents/:id
(Tier 1 — inline)      (Tier 2 — full-screen)
```

---

## Tier 1 — In-Chat Viewer Panel

### Behaviour

- **Desktop:** third column added to `ChatLayout`. Chat shrinks from full-width to ~60%; viewer takes ~40%. Uses the same `translate`/`transition` CSS pattern as the existing left/right panels.
- **Mobile:** slides up as a bottom drawer using scrim + `translateY` — same pattern as existing overlay panels.
- **Global state:** `useDocumentViewer` context hook allows any component to call `openDocument(doc)` / `closeDocument()` without prop drilling.

### Trigger points

| Location | Trigger |
|----------|---------|
| Documents panel | Click document title or eye icon |
| Right panel citations | Click a RAG source citation |
| Mobile results view | Click a cited document |

### Header content

```
┌────────────────────────────────────────────────────┐
│  [PDF]  Climate Report 2024              [↗] [✕]  │
│  2024-03-15  •  climate  energy  policy            │
└────────────────────────────────────────────────────┘
```

- `file_type` badge
- Document title
- "Open full view ↗" button → opens `/documents/:id` in new tab
- Close button
- `document_date` if present
- Topics as chips
- Source URL as external link (web docs)

---

## Tier 2 — Full-Screen `/documents/:id` Route

### Desktop layout

```
┌──────────────────────────────────────────────────────┐
│ ← Back  |  Title                    |  [Edit]        │
├──────────────────────────────────────────────────────┤
│  ToC    │   Document content        │  Metadata      │
│ (200px  │   (markdown rendered)     │  sidebar       │
│  fixed) │                           │  (240px fixed) │
│         │                           │  date, topics, │
│         │                           │  source, size  │
└──────────────────────────────────────────────────────┘
```

- **Back** → `history.back()` (returns to chat or documents panel)
- **ToC** — auto-generated from `#`/`##`/`###` headings; clicking jumps to section anchor
- **Metadata sidebar** — date, topics, source URL, chunk count, file size
- **Edit** shortcut — opens the edit metadata modal directly

### Mobile layout

- ToC collapses to a sticky "Jump to section" `<select>` dropdown at the top
- Metadata sidebar moves below document content
- Full-screen, no chat sidebar

### Extension points

The `/documents/:id` route is the natural home for future features:
- Chunk browser (view individual chunks with embeddings/scores)
- Annotation layer
- Version history / re-ingestion trigger
- Export options

---

## Unified Template

### Metadata header (both tiers)

```
┌────────────────────────────────────────────────┐
│  [PDF]  Climate Report 2024            [↗ link]│
│  2024-03-15  •  climate  energy  policy        │
└────────────────────────────────────────────────┘
```

### Content rendering

- Replace `<pre>` with `react-markdown` for proper heading, table, and list rendering
- Tables use a styled wrapper (`overflow-x-auto`)
- Code blocks get `rehype-highlight` if available (graceful fallback to unstyled)

### ToC generation

- Client-side only: parse headings from fetched content with `/^#{1,3} (.+)/gm`
- Assign `id` anchors to headings during render
- No backend changes required

---

## File Changes

| File | Action |
|------|--------|
| `src/components/documents/DocumentViewerContent.tsx` | **New** — shared content component (metadata header, markdown body, ToC) |
| `src/components/documents/DocumentViewerPanel.tsx` | **New** — tier 1 panel (desktop third column + mobile drawer) |
| `src/hooks/useDocumentViewer.ts` | **New** — context + hook for global `openDocument` / `closeDocument` |
| `src/pages/DocumentPage.tsx` | **New** — tier 2 full-screen route |
| `src/App.tsx` | Add `/documents/:id` route; wrap app with `DocumentViewerProvider` |
| `src/components/layout/ChatLayout.tsx` | Add third column slot; shrink chat when viewer panel open |
| `src/components/documents/DocumentsPanel.tsx` | Swap modal trigger → `openDocument()` hook call |
| `src/components/chat/RightPanel.tsx` | Citation click → `openDocument()` hook call |
| `src/components/documents/DocumentViewer.tsx` | **Delete** — replaced |

### Backend

No changes required. The existing `GET /api/documents/{id}/content` endpoint is sufficient.

---

## Constraints

- No new dependencies beyond `react-markdown` (and optionally `rehype-highlight`)
- Panel animations must use the existing `translate`/`transition` CSS pattern (no new animation libraries)
- RLS applies as-is — content endpoint already checks user ownership
- `useDocumentViewer` context must be available in both the chat view and the documents view, so it wraps at the `App` level

---

## Validation Tests

1. Open a document from the Documents panel → tier 1 panel appears; chat is still interactive behind it
2. Click "Open full view ↗" → `/documents/:id` opens in new tab with full layout
3. Click a RAG citation in the right panel → tier 1 panel opens with the correct document
4. ToC links scroll to the correct heading
5. Web document shows source URL as external link; file document shows file_type badge
6. Mobile: panel slides up as drawer; ToC is a dropdown; closing scrim dismisses panel
7. Navigating to `/documents/:id` directly (copy/paste URL) renders correctly
8. Closing the viewer panel → chat returns to full width
