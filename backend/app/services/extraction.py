"""Text extraction dispatcher — converts any supported file format to plain text."""

import csv
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
    doc = DocxDocument(BytesIO(file_bytes))
    parts = []

    # Paragraphs
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)

    # Table cells
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))

    return "\n".join(parts)


def _extract_csv(file_bytes: bytes) -> str:
    text = file_bytes.decode("utf-8")
    reader = csv.DictReader(StringIO(text))
    rows = []
    for i, row in enumerate(reader, start=1):
        pairs = ", ".join(f"{k}={v}" for k, v in row.items() if v)
        rows.append(f"Row {i}: {pairs}")
    return "\n".join(rows)


def _extract_html(file_bytes: bytes) -> str:
    soup = BeautifulSoup(file_bytes, "html.parser")
    return soup.get_text(separator="\n", strip=True)
