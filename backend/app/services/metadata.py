import json
import logging
from datetime import date

from pydantic import BaseModel
from langsmith import traceable

from app.services.llm import client, strip_thinking
from app.services.chunker import encoding
from app.config import settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """/no_think
Extract metadata from this document. Return JSON with these fields:
- "title": a concise descriptive title for the document
- "summary": a 1-2 sentence summary of the document's content
- "topics": a list of 1-5 topic tags (lowercase, short phrases)
- "document_date": the most relevant date mentioned in the document in YYYY-MM-DD format, or null if no date is found

Return ONLY valid JSON, no other text."""


class DocumentMetadata(BaseModel):
    title: str
    summary: str
    topics: list[str]
    document_date: date | None


@traceable(name="extract_metadata")
async def extract_metadata(text: str) -> DocumentMetadata:
    """Extract title, summary, topics, and date from document text via LLM."""
    # Truncate to first ~2000 tokens
    tokens = encoding.encode(text)
    truncated = encoding.decode(tokens[:2000])

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": truncated},
            ],
            response_format={"type": "json_object"},
        )
        raw = strip_thinking(response.choices[0].message.content or "")
        return DocumentMetadata.model_validate_json(raw)
    except Exception:
        # Try parsing JSON from free-form response as fallback
        try:
            raw = strip_thinking(response.choices[0].message.content or "")
            # Try to find JSON in the response
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return DocumentMetadata.model_validate(json.loads(raw[start:end]))
        except Exception:
            pass

        # Final fallback: derive from text
        logger.warning("Metadata extraction failed, using fallback")
        first_line = text.strip().split("\n")[0][:200]
        return DocumentMetadata(
            title=first_line,
            summary="",
            topics=[],
            document_date=None,
        )
