# Phase 5 Plan A: Structure-Preserving Reformat + Boundary-Aware Chunking

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite HTML and DOCX extractors to emit markdown-structured text (headings, tables, lists), then make the chunker split at heading boundaries instead of arbitrary token positions.

**Architecture:** Two services are modified in sequence: `extraction.py` gains markdown-aware extractors for HTML and DOCX; `chunker.py` gains a heading-boundary split mode that falls back to existing token chunking when no headings are present. All other formats (PDF, TXT, MD, CSV) are untouched.

**Tech Stack:** Python, BeautifulSoup4 (bs4), python-docx, tiktoken, pytest

---

### Task 1: Tests + rewrite `_extract_html` to emit markdown structure

**Files:**
- Modify: `backend/app/services/extraction.py:73-75`
- Create: `tests/unit/services/test_extraction.py`

**Step 1: Create the test file**

Create `tests/unit/services/test_extraction.py` with these tests for the HTML extractor:

```python
from app.services.extraction import extract_text


# ── HTML extraction ────────────────────────────────────────────────────────────

def test_html_heading_h1_becomes_markdown():
    html = b"<h1>Hello World</h1>"
    result = extract_text(html, "html")
    assert "# Hello World" in result


def test_html_heading_h2_becomes_markdown():
    html = b"<h2>Sub Section</h2>"
    result = extract_text(html, "html")
    assert "## Sub Section" in result


def test_html_heading_h3_becomes_markdown():
    html = b"<h3>Deep</h3>"
    result = extract_text(html, "html")
    assert "### Deep" in result


def test_html_heading_h4_becomes_markdown():
    html = b"<h4>Deeper</h4>"
    result = extract_text(html, "html")
    assert "#### Deeper" in result


def test_html_list_items_become_dashes():
    html = b"<ul><li>Alpha</li><li>Beta</li></ul>"
    result = extract_text(html, "html")
    assert "- Alpha" in result
    assert "- Beta" in result


def test_html_table_becomes_markdown_table():
    html = b"""
    <table>
      <tr><th>Name</th><th>Age</th></tr>
      <tr><td>Alice</td><td>30</td></tr>
    </table>
    """
    result = extract_text(html, "html")
    assert "| Name | Age |" in result
    assert "| --- | --- |" in result
    assert "| Alice | 30 |" in result


def test_html_script_tags_stripped():
    html = b"<p>Keep this</p><script>var x = 1;</script>"
    result = extract_text(html, "html")
    assert "Keep this" in result
    assert "var x" not in result


def test_html_nav_stripped():
    html = b"<nav><a>Menu</a></nav><p>Content</p>"
    result = extract_text(html, "html")
    assert "Content" in result
    assert "Menu" not in result


def test_html_preserves_paragraph_text():
    html = b"<p>Some body text here.</p>"
    result = extract_text(html, "html")
    assert "Some body text here." in result


def test_html_no_excessive_blank_lines():
    html = b"<p>A</p><p>B</p><p>C</p>"
    result = extract_text(html, "html")
    # Should not have 3+ consecutive newlines
    assert "\n\n\n" not in result
```

**Step 2: Run tests to confirm they fail**

```bash
cd /home/ralph/dev/agentic-rag && source backend/venv/bin/activate && python -m pytest tests/unit/services/test_extraction.py -v 2>&1 | head -40
```

Expected: most HTML tests FAIL (current `_extract_html` just calls `get_text`)

**Step 3: Rewrite `_extract_html` in `backend/app/services/extraction.py`**

Replace the current `_extract_html` function (lines 73–75) with:

```python
_STRIP_TAGS = {"script", "style", "nav", "header", "footer", "aside"}
_HEADING_MAP = {"h1": "#", "h2": "##", "h3": "###", "h4": "####"}


def _extract_html(file_bytes: bytes) -> str:
    soup = BeautifulSoup(file_bytes, "html.parser")

    # Remove boilerplate elements
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    lines: list[str] = []

    def _walk(node) -> None:
        from bs4 import NavigableString, Tag
        if isinstance(node, NavigableString):
            text = node.strip()
            if text:
                lines.append(text)
            return

        tag_name = node.name
        if tag_name is None:
            return

        if tag_name in _HEADING_MAP:
            prefix = _HEADING_MAP[tag_name]
            text = node.get_text(" ", strip=True)
            if text:
                lines.append(f"\n{prefix} {text}")
            return

        if tag_name == "li":
            text = node.get_text(" ", strip=True)
            if text:
                lines.append(f"- {text}")
            return

        if tag_name == "table":
            lines.append(_table_to_markdown(node))
            return

        if tag_name in ("ul", "ol"):
            for child in node.children:
                _walk(child)
            return

        if tag_name == "p":
            text = node.get_text(" ", strip=True)
            if text:
                lines.append(text)
            return

        # Generic: recurse into children
        for child in node.children:
            _walk(child)

    _walk(soup.body or soup)

    # Collapse excessive blank lines
    import re
    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _table_to_markdown(table_node) -> str:
    """Convert a BeautifulSoup table element to GFM markdown table."""
    rows = table_node.find_all("tr")
    if not rows:
        return ""

    table_lines: list[str] = []
    header_done = False

    for row in rows:
        # th cells → header row; td cells → body row
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
        if not cells:
            continue
        table_lines.append("| " + " | ".join(cells) + " |")
        if not header_done:
            table_lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
            header_done = True

    return "\n".join(table_lines)
```

Also add `_table_to_markdown` as a module-level helper (it's called from `_walk` inside `_extract_html`).

**Step 4: Run the HTML tests**

```bash
cd /home/ralph/dev/agentic-rag && source backend/venv/bin/activate && python -m pytest tests/unit/services/test_extraction.py -v -k "html" 2>&1
```

Expected: all HTML tests PASS

**Step 5: Commit**

```bash
cd /home/ralph/dev/agentic-rag && git add backend/app/services/extraction.py tests/unit/services/test_extraction.py && git commit -m "feat: structure-preserving HTML extraction — headings, tables, lists to markdown"
```

---

### Task 2: Tests + rewrite `_extract_docx` to emit markdown structure

**Files:**
- Modify: `backend/app/services/extraction.py:44-60`
- Modify: `tests/unit/services/test_extraction.py` (add DOCX tests)

**Step 1: Add DOCX tests to `tests/unit/services/test_extraction.py`**

Add these tests at the end of the file:

```python
# ── DOCX extraction ────────────────────────────────────────────────────────────

from io import BytesIO
from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def _make_docx_bytes(**kwargs) -> bytes:
    """Create a minimal .docx in memory. kwargs: paragraphs list of (text, style)."""
    doc = DocxDocument()
    for text, style in kwargs.get("paragraphs", []):
        p = doc.add_paragraph(text, style=style)
    for table_data in kwargs.get("tables", []):
        # table_data = list of rows, each row = list of cell strings
        t = doc.add_table(rows=len(table_data), cols=len(table_data[0]))
        for r_idx, row in enumerate(table_data):
            for c_idx, cell_text in enumerate(row):
                t.cell(r_idx, c_idx).text = cell_text
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_docx_heading1_becomes_markdown():
    docx_bytes = _make_docx_bytes(paragraphs=[("Introduction", "Heading 1")])
    result = extract_text(docx_bytes, "docx")
    assert "# Introduction" in result


def test_docx_heading2_becomes_markdown():
    docx_bytes = _make_docx_bytes(paragraphs=[("Sub-topic", "Heading 2")])
    result = extract_text(docx_bytes, "docx")
    assert "## Sub-topic" in result


def test_docx_body_paragraph_has_no_prefix():
    docx_bytes = _make_docx_bytes(paragraphs=[("Just a sentence.", "Normal")])
    result = extract_text(docx_bytes, "docx")
    assert "Just a sentence." in result
    assert "# Just a sentence." not in result


def test_docx_table_becomes_markdown_table():
    docx_bytes = _make_docx_bytes(
        tables=[[["Name", "Score"], ["Alice", "95"], ["Bob", "87"]]]
    )
    result = extract_text(docx_bytes, "docx")
    assert "| Name | Score |" in result
    assert "| --- | --- |" in result
    assert "| Alice | 95 |" in result
```

**Step 2: Run DOCX tests to confirm they fail**

```bash
cd /home/ralph/dev/agentic-rag && source backend/venv/bin/activate && python -m pytest tests/unit/services/test_extraction.py -v -k "docx" 2>&1
```

Expected: FAIL — current `_extract_docx` doesn't check heading styles or emit markdown tables

**Step 3: Rewrite `_extract_docx` in `backend/app/services/extraction.py`**

Replace the current `_extract_docx` function (lines 44–60) with:

```python
_DOCX_HEADING_MAP = {
    "Heading 1": "#",
    "Heading 2": "##",
    "Heading 3": "###",
    "Heading 4": "####",
}


def _extract_docx(file_bytes: bytes) -> str:
    from docx.oxml.ns import qn as _qn

    doc = DocxDocument(BytesIO(file_bytes))
    parts: list[str] = []

    # Walk document body elements in order to preserve paragraph/table sequence
    body = doc.element.body
    for child in body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "p":
            # Find the matching python-docx Paragraph
            para_text = "".join(
                run.text for run in child.iter(_qn("w:r"))
                if "".join(t.text for t in run.iter(_qn("w:t")))
            )
            # Get full text via join of w:t elements
            para_text = "".join(
                t.text for t in child.iter(_qn("w:t"))
            ).strip()
            if not para_text:
                continue

            # Detect heading style
            style_elem = child.find(_qn("w:pPr"))
            style_name = None
            if style_elem is not None:
                style_ref = style_elem.find(_qn("w:pStyle"))
                if style_ref is not None:
                    style_id = style_ref.get(_qn("w:val"), "")
                    # Style IDs are like "Heading1" but names are "Heading 1"
                    # Match either form
                    for name in _DOCX_HEADING_MAP:
                        if style_id.replace(" ", "") == name.replace(" ", ""):
                            style_name = name
                            break

            if style_name:
                prefix = _DOCX_HEADING_MAP[style_name]
                parts.append(f"{prefix} {para_text}")
            else:
                parts.append(para_text)

        elif tag == "tbl":
            # Convert table to markdown
            rows: list[list[str]] = []
            for row_elem in child.iter(_qn("w:tr")):
                cells = []
                for cell_elem in row_elem.iter(_qn("w:tc")):
                    cell_text = "".join(
                        t.text for t in cell_elem.iter(_qn("w:t"))
                    ).strip()
                    cells.append(cell_text)
                if cells:
                    rows.append(cells)

            if rows:
                # Header row
                parts.append("| " + " | ".join(rows[0]) + " |")
                parts.append("| " + " | ".join(["---"] * len(rows[0])) + " |")
                for row in rows[1:]:
                    parts.append("| " + " | ".join(row) + " |")

    return "\n".join(parts)
```

**Step 4: Run all extraction tests**

```bash
cd /home/ralph/dev/agentic-rag && source backend/venv/bin/activate && python -m pytest tests/unit/services/test_extraction.py -v 2>&1
```

Expected: all tests PASS

**Step 5: Commit**

```bash
cd /home/ralph/dev/agentic-rag && git add backend/app/services/extraction.py tests/unit/services/test_extraction.py && git commit -m "feat: structure-preserving DOCX extraction — headings and tables to markdown"
```

---

### Task 3: Tests + implement heading-boundary chunking in `chunker.py`

**Files:**
- Modify: `backend/app/services/chunker.py`
- Create: `tests/unit/services/test_chunker.py`

**Step 1: Create `tests/unit/services/test_chunker.py`**

```python
from app.services.chunker import chunk_text


def test_no_headings_falls_back_to_token_chunking():
    """Plain text with no headings uses existing token-based chunking."""
    text = "word " * 1000  # plenty of tokens, no headings
    chunks = chunk_text(text)
    assert len(chunks) > 1
    # All chunks should be non-empty
    for c in chunks:
        assert c.content.strip()


def test_single_short_section_is_one_chunk():
    """A document with one heading and short body → single chunk."""
    text = "# Introduction\n\nThis is a short intro."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert "# Introduction" in chunks[0].content


def test_two_sections_produce_separate_chunks():
    """Two short sections stay in separate chunks."""
    text = "# Section One\n\nContent of section one.\n\n# Section Two\n\nContent of section two."
    chunks = chunk_text(text)
    # Should have at least 2 chunks
    assert len(chunks) >= 2
    # First chunk should contain heading for section one
    combined = " ".join(c.content for c in chunks)
    assert "# Section One" in combined
    assert "# Section Two" in combined


def test_heading_preserved_in_continuation_chunks():
    """When a section exceeds chunk_size, the heading is prepended to each continuation."""
    # Create a section that exceeds chunk_size (500 tokens)
    long_body = "word " * 600  # ~600 tokens
    text = f"# Big Section\n\n{long_body}"
    chunks = chunk_text(text)
    assert len(chunks) >= 2
    # Every chunk should carry the heading
    for c in chunks:
        assert "# Big Section" in c.content


def test_chunk_indices_are_sequential():
    """chunk_index values must be 0, 1, 2, ... regardless of split mode."""
    text = "# A\n\nsome content\n\n# B\n\nmore content\n\n# C\n\neven more content"
    chunks = chunk_text(text)
    for i, c in enumerate(chunks):
        assert c.chunk_index == i


def test_chunks_have_content_hash():
    """Every chunk must have a non-empty content_hash."""
    text = "# Hello\n\nSome text."
    chunks = chunk_text(text)
    for c in chunks:
        assert c.content_hash
        assert len(c.content_hash) == 64  # sha256 hex


def test_table_not_split_mid_table():
    """A markdown table within a section must not be broken in half."""
    table = (
        "| Name | Score |\n"
        "| --- | --- |\n"
        "| Alice | 95 |\n"
        "| Bob | 87 |\n"
        "| Carol | 72 |\n"
    )
    text = f"# Results\n\n{table}"
    chunks = chunk_text(text)
    # Find the chunk containing the table header
    table_chunk = next((c for c in chunks if "| Name | Score |" in c.content), None)
    assert table_chunk is not None
    # That same chunk must also contain the separator row
    assert "| --- | --- |" in table_chunk.content


def test_empty_text_returns_empty_list():
    chunks = chunk_text("")
    assert chunks == []


def test_whitespace_only_returns_empty_list():
    chunks = chunk_text("   \n  \n  ")
    assert chunks == []
```

**Step 2: Run tests to confirm they fail**

```bash
cd /home/ralph/dev/agentic-rag && source backend/venv/bin/activate && python -m pytest tests/unit/services/test_chunker.py -v 2>&1
```

Expected: most tests FAIL (current chunker has no heading detection)

**Step 3: Rewrite `chunker.py`**

Replace the entire contents of `backend/app/services/chunker.py` with:

```python
import re
import tiktoken
from pydantic import BaseModel
from app.config import settings
from app.services.hashing import sha256_text

encoding = tiktoken.get_encoding("cl100k_base")

_HEADING_RE = re.compile(r"^#{1,4} ", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\s*\|", re.MULTILINE)


class Chunk(BaseModel):
    content: str
    chunk_index: int
    token_count: int
    content_hash: str


def chunk_text(text: str) -> list[Chunk]:
    """Split text into chunks, using heading boundaries when present."""
    if not text or not text.strip():
        return []

    if _HEADING_RE.search(text):
        return _heading_chunk(text)
    return _token_chunk(text)


# ── Heading-boundary chunking ──────────────────────────────────────────────────

def _heading_chunk(text: str) -> list[Chunk]:
    """Split at markdown heading boundaries; token-split oversized sections."""
    sections = _split_into_sections(text)
    chunks: list[Chunk] = []

    for heading, body in sections:
        section_text = (f"{heading}\n\n{body}".strip() if heading else body.strip())
        tokens = encoding.encode(section_text)

        if len(tokens) <= settings.chunk_size:
            _append_chunk(chunks, section_text, tokens)
        else:
            # Token-split the section, prepending heading to each continuation
            _split_oversized_section(chunks, heading, body)

    return chunks


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    """Return list of (heading_line, body_text) pairs. Leading body before first heading has empty heading."""
    sections: list[tuple[str, str]] = []
    lines = text.splitlines(keepends=True)
    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        if _HEADING_RE.match(line):
            if current_body or current_heading:
                sections.append((current_heading, "".join(current_body).strip()))
            current_heading = line.rstrip()
            current_body = []
        else:
            current_body.append(line)

    if current_body or current_heading:
        sections.append((current_heading, "".join(current_body).strip()))

    return sections


def _split_oversized_section(
    chunks: list[Chunk], heading: str, body: str
) -> None:
    """Token-split a section that exceeds chunk_size, prepending heading to each chunk."""
    # Keep tables atomic: collect table blocks, split non-table text, stitch back
    parts = _split_preserving_tables(body)
    buffer_tokens: list[int] = []
    if heading:
        buffer_tokens = encoding.encode(heading + "\n\n")

    for part in parts:
        part_tokens = encoding.encode(part)

        if len(buffer_tokens) + len(part_tokens) <= settings.chunk_size:
            buffer_tokens.extend(part_tokens)
        else:
            # Flush buffer if non-empty
            if buffer_tokens:
                _append_chunk(chunks, encoding.decode(buffer_tokens), buffer_tokens)

            # Start new buffer with heading + this part
            if heading:
                buffer_tokens = encoding.encode(heading + "\n\n") + part_tokens
            else:
                buffer_tokens = list(part_tokens)

            # If even this one part is too large, force-split it
            while len(buffer_tokens) > settings.chunk_size:
                slice_tokens = buffer_tokens[: settings.chunk_size]
                _append_chunk(chunks, encoding.decode(slice_tokens), slice_tokens)
                if heading:
                    buffer_tokens = (
                        encoding.encode(heading + "\n\n")
                        + buffer_tokens[settings.chunk_size :]
                    )
                else:
                    buffer_tokens = buffer_tokens[settings.chunk_size :]

    if buffer_tokens:
        _append_chunk(chunks, encoding.decode(buffer_tokens), buffer_tokens)


def _split_preserving_tables(text: str) -> list[str]:
    """Split text into parts, keeping markdown table blocks intact."""
    lines = text.splitlines(keepends=True)
    parts: list[str] = []
    current: list[str] = []
    in_table = False

    for line in lines:
        is_table_row = bool(_TABLE_ROW_RE.match(line))
        if is_table_row:
            if not in_table and current:
                parts.append("".join(current))
                current = []
            current.append(line)
            in_table = True
        else:
            if in_table:
                parts.append("".join(current))
                current = []
                in_table = False
            current.append(line)

    if current:
        parts.append("".join(current))

    return [p for p in parts if p.strip()]


# ── Token-based fallback chunking (unchanged logic) ───────────────────────────

def _token_chunk(text: str) -> list[Chunk]:
    """Fixed-size token chunks with overlap (original algorithm)."""
    tokens = encoding.encode(text)
    chunks: list[Chunk] = []
    start = 0

    while start < len(tokens):
        end = start + settings.chunk_size
        chunk_tokens = tokens[start:end]
        _append_chunk(chunks, encoding.decode(chunk_tokens), chunk_tokens)
        start += settings.chunk_size - settings.chunk_overlap

    return chunks


# ── Shared ─────────────────────────────────────────────────────────────────────

def _append_chunk(chunks: list[Chunk], content: str, tokens: list[int]) -> None:
    content = content.strip()
    if not content:
        return
    chunks.append(
        Chunk(
            content=content,
            chunk_index=len(chunks),
            token_count=len(tokens),
            content_hash=sha256_text(content),
        )
    )
```

**Step 4: Run chunker tests**

```bash
cd /home/ralph/dev/agentic-rag && source backend/venv/bin/activate && python -m pytest tests/unit/services/test_chunker.py -v 2>&1
```

Expected: all tests PASS

**Step 5: Run full test suite**

```bash
cd /home/ralph/dev/agentic-rag && source backend/venv/bin/activate && python -m pytest tests/ -v 2>&1
```

Expected: all tests PASS (no regressions)

**Step 6: Commit**

```bash
cd /home/ralph/dev/agentic-rag && git add backend/app/services/chunker.py tests/unit/services/test_chunker.py && git commit -m "feat: boundary-aware chunking — heading splits, table atomicity, token fallback"
```

---

### Task 4: Update PROGRESS.md

**Files:**
- Modify: `PROGRESS.md`

Find and update:

```
- [ ] **Structure-preserving reformat:** Reformat tables/lists so they remain useful post-embedding (table→markdown, keep headers)
- [ ] **Boundary-aware chunking:** Chunking respects headings/sections; keep headings attached; keep tables whole.
```

Change to:

```
- [x] **Structure-preserving reformat:** Reformat tables/lists so they remain useful post-embedding (table→markdown, keep headers)
- [x] **Boundary-aware chunking:** Chunking respects headings/sections; keep headings attached; keep tables whole.
```

**Commit:**

```bash
cd /home/ralph/dev/agentic-rag && git add PROGRESS.md && git commit -m "docs: mark Phase 5 structure-preserving reformat and boundary-aware chunking complete"
```
