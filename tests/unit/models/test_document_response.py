from datetime import datetime
from backend.app.models.documents import DocumentResponse


def make_doc(**overrides):
    base = {
        "id": "doc-1",
        "user_id": "user-1",
        "filename": "test.html",
        "storage_path": "user-1/abc.html",
        "file_type": "html",
        "file_size": 1024,
        "status": "ready",
        "chunk_count": 5,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }
    base.update(overrides)
    return base


def test_document_response_source_url_present():
    doc = DocumentResponse(**make_doc(source_url="https://example.com/article"))
    assert doc.source_url == "https://example.com/article"


def test_document_response_source_url_defaults_to_none():
    doc = DocumentResponse(**make_doc())
    assert doc.source_url is None
