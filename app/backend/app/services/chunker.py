import re
import tiktoken
from pydantic import BaseModel

try:
    from app.config import settings
    from app.services.hashing import sha256_text
except ModuleNotFoundError:
    from backend.app.config import settings  # type: ignore[no-redef]
    from backend.app.services.hashing import sha256_text  # type: ignore[no-redef]

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
            _split_oversized_section(chunks, heading, body)

    return chunks


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    """Return list of (heading_line, body_text) pairs.
    Leading body before first heading has empty heading string."""
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
    parts = _split_preserving_tables(body)
    buffer_tokens: list[int] = []
    if heading:
        buffer_tokens = encoding.encode(heading + "\n\n")

    for part in parts:
        part_tokens = encoding.encode(part)

        if len(buffer_tokens) + len(part_tokens) <= settings.chunk_size:
            buffer_tokens.extend(part_tokens)
        else:
            if buffer_tokens:
                _append_chunk(chunks, encoding.decode(buffer_tokens), buffer_tokens)

            if heading:
                buffer_tokens = encoding.encode(heading + "\n\n") + part_tokens
            else:
                buffer_tokens = list(part_tokens)

            # Force-split if even heading + one part exceeds chunk_size
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


# ── Token-based fallback chunking (original algorithm) ────────────────────────

def _token_chunk(text: str) -> list[Chunk]:
    """Fixed-size token chunks with overlap."""
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
