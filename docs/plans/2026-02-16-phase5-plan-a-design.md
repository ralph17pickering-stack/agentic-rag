# Phase 5 Plan A Design: Structure-Preserving Reformat + Boundary-Aware Chunking

**Date:** 2026-02-16

## Problem

The current ingestion pipeline loses document structure on the way to chunks:

- `_extract_html` calls `soup.get_text()` — strips all headings, tables, lists into a flat string
- `_extract_docx` iterates paragraphs without checking heading styles; tables become " | "-joined rows, not markdown tables
- `chunk_text` splits on fixed token boundaries, potentially mid-sentence, mid-table, mid-section

The result: chunks land mid-paragraph with no context about what section they belong to, tables are shredded, and retrieval returns fragments that can't stand alone.

## Solution

Two changes, tightly coupled:

### 1. Structure-preserving extraction (`extraction.py`)

HTML and DOCX extractors emit **markdown-structured text** instead of plain text, so structural information (headings, tables, lists) survives into the chunker.

**HTML** (`_extract_html`):
- Walk the DOM via BeautifulSoup
- Strip boilerplate tags: `<script>`, `<style>`, `<nav>`, `<header>`, `<footer>`, `<aside>`
- Map heading tags to markdown: `<h1>` → `# `, `<h2>` → `## `, `<h3>` → `### `, `<h4>` → `#### `
- Map list items `<li>` → `- ` prefix
- Map `<table>` → GFM markdown table (header row + separator `|---|` + body rows)
- Collapse excessive blank lines (max 2 consecutive)
- Fall back to `.get_text()` for any element not explicitly handled

**DOCX** (`_extract_docx`):
- For each paragraph, inspect `.style.name`: `Heading 1` → `# `, `Heading 2` → `## `, `Heading 3` → `### `, `Heading 4` → `#### `
- Body paragraphs: emit as plain text (no prefix)
- Tables: emit as GFM markdown table (same format as HTML tables)
- Preserve document order (paragraphs and tables interleaved)

**PDF, TXT, MD, CSV**: no changes.

### 2. Boundary-aware chunking (`chunker.py`)

After extraction produces markdown-structured text, the chunker detects heading boundaries and splits there instead of at token boundaries.

**Algorithm:**
1. Detect whether text has headings: scan for lines matching `^#{1,4} `
2. **With headings** — heading-boundary split:
   - Split text into sections at every heading line
   - Each section = heading line + body text until next heading
   - Tokenise each section
   - If section tokens ≤ `chunk_size` → one chunk (section as-is)
   - If section tokens > `chunk_size` → token-split the section with heading prepended to each continuation chunk
   - Tables are kept atomic: never split mid-table (`| ... |` block)
3. **Without headings** — fall back to existing fixed-size token chunking with overlap (unchanged)

**Settings used:** `chunk_size` (500), `chunk_overlap` (50) — no new settings needed.

## Files Changed

| File | Change |
|------|--------|
| `app/backapp/frontend/app/services/extraction.py` | Rewrite `_extract_html` and `_extract_docx` |
| `app/backapp/frontend/app/services/chunker.py` | Add heading-boundary logic; keep token fallback |
| `tests/unit/services/test_extraction.py` | New — unit tests for HTML/DOCX extraction |
| `tests/unit/services/test_chunker.py` | New — unit tests for boundary-aware chunking |

## Out of Scope

- PDF structure (pypdf doesn't give heading metadata)
- CSV structure (already row-based, no headings needed)
- Table-of-contents generation
- Chunk enrichment (Plan B)
