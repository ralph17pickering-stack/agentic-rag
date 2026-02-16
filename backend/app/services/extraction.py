"""Text extraction dispatcher — converts any supported file format to plain text."""

import csv
import re
from io import BytesIO, StringIO

import pypdf
from bs4 import BeautifulSoup
from docx import Document as DocxDocument


SUPPORTED_TYPES = {"txt", "md", "pdf", "docx", "csv", "html"}


def extract_text(file_bytes: bytes, file_type: str) -> str:
    """Extract plain text from file bytes based on file_type."""
    if file_type in ("txt", "md"):
        return file_bytes.decode("utf-8")

    if file_type == "pdf":
        return _extract_pdf(file_bytes)

    if file_type == "docx":
        return _extract_docx(file_bytes)

    if file_type == "csv":
        return _extract_csv(file_bytes)

    if file_type == "html":
        return _extract_html(file_bytes)

    raise ValueError(f"Unsupported file type: {file_type}")


def _extract_pdf(file_bytes: bytes) -> str:
    reader = pypdf.PdfReader(BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def _extract_docx(file_bytes: bytes) -> str:
    from docx.oxml.ns import qn

    doc = DocxDocument(BytesIO(file_bytes))
    parts: list[str] = []

    body = doc.element.body
    for child in body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "p":
            para_text = "".join(
                t.text for t in child.iter(qn("w:t"))
            ).strip()
            if not para_text:
                continue

            # Detect heading style via w:pStyle val attribute
            style_name = None
            ppr = child.find(qn("w:pPr"))
            if ppr is not None:
                pstyle = ppr.find(qn("w:pStyle"))
                if pstyle is not None:
                    style_id = pstyle.get(qn("w:val"), "")
                    # Style IDs: "Heading1", "Heading2", etc. (no spaces)
                    style_name = _DOCX_HEADING_MAP.get(style_id)

            if style_name:
                parts.append(f"{style_name} {para_text}")
            else:
                parts.append(para_text)

        elif tag == "tbl":
            rows: list[list[str]] = []
            for row_elem in child.iter(qn("w:tr")):
                cells = []
                for cell_elem in row_elem.iter(qn("w:tc")):
                    cell_text = "".join(
                        t.text for t in cell_elem.iter(qn("w:t"))
                    ).strip()
                    cells.append(cell_text)
                if cells:
                    rows.append(cells)

            if rows:
                parts.append("| " + " | ".join(rows[0]) + " |")
                parts.append("| " + " | ".join(["---"] * len(rows[0])) + " |")
                for row in rows[1:]:
                    parts.append("| " + " | ".join(row) + " |")

    return "\n".join(parts)


def _extract_csv(file_bytes: bytes) -> str:
    text = file_bytes.decode("utf-8")
    reader = csv.DictReader(StringIO(text))
    rows = []
    for i, row in enumerate(reader, start=1):
        pairs = ", ".join(f"{k}={v}" for k, v in row.items() if v)
        rows.append(f"Row {i}: {pairs}")
    return "\n".join(rows)


_STRIP_TAGS = {"script", "style", "nav", "header", "footer", "aside"}
_HEADING_MAP = {"h1": "#", "h2": "##", "h3": "###", "h4": "####"}
_DOCX_HEADING_MAP = {
    "Heading1": "#",
    "Heading2": "##",
    "Heading3": "###",
    "Heading4": "####",
}


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

        if tag_name in ("ul", "ol"):
            counter = 0
            for child in node.children:
                from bs4 import Tag as BsTag
                if isinstance(child, BsTag) and child.name == "li":
                    text = child.get_text(" ", strip=True)
                    if text:
                        if tag_name == "ol":
                            counter += 1
                            lines.append(f"{counter}. {text}")
                        else:
                            lines.append(f"- {text}")
                else:
                    _walk(child)
            return

        if tag_name == "li":
            # Fallback for bare <li> not inside ul/ol
            text = node.get_text(" ", strip=True)
            if text:
                lines.append(f"- {text}")
            return

        if tag_name == "table":
            lines.append(_table_to_markdown(node))
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
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
        if not cells:
            continue
        table_lines.append("| " + " | ".join(cells) + " |")
        if not header_done:
            table_lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
            header_done = True

    return "\n".join(table_lines)
