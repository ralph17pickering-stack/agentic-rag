"""
Python-only metadata extraction — no LLM required.

- title:         first markdown heading, or first non-blank line, or filename stem
- summary:       first 2–3 substantial sentences
- topics:        top keyphrases via YAKE (no model download), blocklist-filtered
- document_date: first recognisable date found via regex
"""
import re
import logging
from datetime import date
from pathlib import Path

import yake
from pydantic import BaseModel
from langsmith import traceable

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic model (unchanged contract — callers don't need to change)
# ---------------------------------------------------------------------------

class DocumentMetadata(BaseModel):
    title: str
    summary: str
    topics: list[str]
    document_date: date | None


# ---------------------------------------------------------------------------
# YAKE keyword extractor — instantiated once, reused across calls
# n=2: up to 2-word keyphrases; top=5: return 5 results
# ---------------------------------------------------------------------------

_kw_extractor = yake.KeywordExtractor(lan="en", n=2, dedupLim=0.7, top=settings.tag_candidates)


# ---------------------------------------------------------------------------
# Individual extractors
# ---------------------------------------------------------------------------

def _extract_title(text: str, filename: str = "") -> str:
    """First markdown heading > first non-blank line > filename stem."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:200]
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) > 10:
            return stripped[:200]
    if filename:
        return Path(filename).stem.replace("_", " ").replace("-", " ")[:200]
    return "Untitled"


def _extract_summary(text: str) -> str:
    """First 2–3 sentences that look like prose (≥20 chars, not a heading)."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip()[:4000])
    collected, total_chars = [], 0
    for s in sentences:
        s = s.strip()
        if len(s) < 20 or s.startswith("#"):
            continue
        collected.append(s)
        total_chars += len(s)
        if len(collected) >= 3 or total_chars >= 500:
            break
    return " ".join(collected)[:600]


def _extract_topics(text: str) -> list[str]:
    """Top keyphrases from the first 5 000 chars via YAKE."""
    try:
        keywords = _kw_extractor.extract_keywords(text[:5000])
        return [kw.lower() for kw, _score in keywords]
    except Exception as exc:
        logger.warning("Keyword extraction failed: %s", exc)
        return []


_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
    r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_DATE_RES = [
    # ISO: 2024-01-15
    re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b"),
    # "15 January 2024" or "January 15, 2024"
    re.compile(
        rf"\b(?:(\d{{1,2}})\s+)?({_MONTH})[,.]?\s+(?:(\d{{1,2}})[,.]?\s+)?((?:19|20)\d{{2}})\b",
        re.IGNORECASE,
    ),
    # DD/MM/YYYY  (European — only accept if year >= 1900)
    re.compile(r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.]((?:19|20)\d{2})\b"),
]


def _extract_date(text: str) -> date | None:
    """Return the first plausible date found in the text, or None."""
    sample = text[:8000]

    # ISO
    m = _DATE_RES[0].search(sample)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # Month-name
    m = _DATE_RES[1].search(sample)
    if m:
        day = int(m.group(1) or m.group(3) or "1")
        month = _MONTH_MAP.get(m.group(2).lower()[:3])
        year = int(m.group(4))
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    # DD/MM/YYYY
    m = _DATE_RES[2].search(sample)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            try:
                return date(y, mo, d)
            except ValueError:
                pass

    return None


# ---------------------------------------------------------------------------
# Public API — async to keep the call-site unchanged
# ---------------------------------------------------------------------------

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
