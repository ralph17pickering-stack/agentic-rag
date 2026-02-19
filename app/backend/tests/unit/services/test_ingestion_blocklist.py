import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_ingest_passes_blocked_tags_to_metadata():
    """Ingestion should fetch user's blocked tags and pass them to extract_metadata."""
    # Mock supabase client
    doc_table = MagicMock()
    doc_table.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "doc-1", "filename": "test.pdf"}
    ]
    doc_table.update.return_value.eq.return_value.execute.return_value = None

    chunks_table = MagicMock()
    chunks_table.delete.return_value.eq.return_value.execute.return_value = None
    chunks_table.insert.return_value.execute.return_value = None

    blocked_table = MagicMock()
    blocked_table.select.return_value.eq.return_value.execute.return_value.data = [
        {"tag": "communications plan"},
        {"tag": "key findings"},
    ]

    mock_sb = MagicMock()
    def table_router(name):
        if name == "blocked_tags":
            return blocked_table
        if name == "chunks":
            return chunks_table
        return doc_table
    mock_sb.table = MagicMock(side_effect=table_router)
    mock_sb.storage.from_.return_value.download.return_value = b"some text"
    mock_sb.storage.from_.return_value.remove.return_value = None
    mock_sb.storage.from_.return_value.upload.return_value = None

    mock_metadata = MagicMock(
        title="Test", summary="Summary", topics=["climate"],
        document_date=None,
    )
    mock_extract_metadata = AsyncMock(return_value=mock_metadata)

    with patch("app.services.ingestion.get_service_supabase_client", return_value=mock_sb), \
         patch("app.services.ingestion.extract_text", return_value="some text"), \
         patch("app.services.ingestion.clean_text", return_value="some text"), \
         patch("app.services.ingestion.extract_metadata", mock_extract_metadata), \
         patch("app.services.ingestion.chunk_text", return_value=[]), \
         patch("app.services.ingestion.generate_embeddings", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.ingestion.settings") as mock_settings:
        mock_settings.graphrag_enabled = False
        mock_metadata.document_date = None

        from app.services.ingestion import ingest_document
        await ingest_document("doc-1", "user-1", "path/file.pdf", "pdf")

    mock_extract_metadata.assert_called_once()
    kwargs = mock_extract_metadata.call_args.kwargs
    assert "blocked_tags" in kwargs
    assert kwargs["blocked_tags"] == {"communications plan", "key findings"}
