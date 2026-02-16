import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def make_chunk(
    chunk_id="chunk-1",
    document_id="doc-1",
    doc_title="My Doc",
    chunk_index=0,
    content="Some content here",
    similarity=0.9,
    rrf_score=None,
    rerank_score=None,
):
    return {
        "id": chunk_id,
        "document_id": document_id,
        "doc_title": doc_title,
        "chunk_index": chunk_index,
        "content": content,
        "similarity": similarity,
        "rrf_score": rrf_score,
        "rerank_score": rerank_score,
    }


def build_citation_source(chunk: dict) -> dict:
    """Mirrors the logic in llm.py _execute_tool for retrieve_documents."""
    content = chunk["content"]
    return {
        "chunk_id": chunk["id"],
        "document_id": chunk["document_id"],
        "doc_title": chunk.get("doc_title") or "Untitled",
        "chunk_index": chunk.get("chunk_index", 0),
        "content_preview": content[:200] + "..." if len(content) > 200 else content,
        "score": chunk.get("rerank_score") or chunk.get("rrf_score") or chunk.get("similarity", 0.0),
    }


def test_citation_source_has_required_fields():
    chunk = make_chunk()
    source = build_citation_source(chunk)
    assert "chunk_id" in source
    assert "document_id" in source
    assert "doc_title" in source
    assert "chunk_index" in source
    assert "content_preview" in source
    assert "score" in source


def test_citation_source_uses_rerank_score_first():
    chunk = make_chunk(similarity=0.5, rrf_score=0.7, rerank_score=0.9)
    source = build_citation_source(chunk)
    assert source["score"] == 0.9


def test_citation_source_falls_back_to_rrf_score():
    chunk = make_chunk(similarity=0.5, rrf_score=0.7, rerank_score=None)
    source = build_citation_source(chunk)
    assert source["score"] == 0.7


def test_citation_source_falls_back_to_similarity():
    chunk = make_chunk(similarity=0.5, rrf_score=None, rerank_score=None)
    source = build_citation_source(chunk)
    assert source["score"] == 0.5


def test_citation_source_truncates_long_content():
    long_content = "x" * 300
    chunk = make_chunk(content=long_content)
    source = build_citation_source(chunk)
    assert len(source["content_preview"]) <= 203  # 200 + "..."
    assert source["content_preview"].endswith("...")


def test_citation_source_keeps_short_content():
    short_content = "Short text"
    chunk = make_chunk(content=short_content)
    source = build_citation_source(chunk)
    assert source["content_preview"] == short_content
    assert not source["content_preview"].endswith("...")


def test_citation_source_uses_untitled_when_no_title():
    chunk = make_chunk(doc_title=None)
    source = build_citation_source(chunk)
    assert source["doc_title"] == "Untitled"


def test_deduplication_by_chunk_id():
    """Mirrors deduplication logic in chat.py event_generator."""
    sources = [
        {"chunk_id": "a", "document_id": "doc-1", "doc_title": "D1"},
        {"chunk_id": "b", "document_id": "doc-1", "doc_title": "D1"},
        {"chunk_id": "a", "document_id": "doc-1", "doc_title": "D1"},  # duplicate
    ]
    seen = set()
    deduped = []
    for s in sources:
        if s["chunk_id"] not in seen:
            seen.add(s["chunk_id"])
            deduped.append(s)

    assert len(deduped) == 2
    assert deduped[0]["chunk_id"] == "a"
    assert deduped[1]["chunk_id"] == "b"
