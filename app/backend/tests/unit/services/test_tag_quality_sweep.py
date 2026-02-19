import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_assess_tags_returns_keep_and_remove():
    from app.services.tag_quality_sweep import assess_tag_quality

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"keep": ["climate change", "renewable energy"], "remove": ["key findings"]}'

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.tag_quality_sweep.client", mock_client):
        result = await assess_tag_quality(
            title="Climate Report",
            summary="A report on climate change impacts.",
            tags=["climate change", "renewable energy", "key findings"],
        )

    assert "climate change" in result["keep"]
    assert "key findings" in result["remove"]


@pytest.mark.asyncio
async def test_assess_tags_handles_llm_failure():
    from app.services.tag_quality_sweep import assess_tag_quality

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM down"))

    with patch("app.services.tag_quality_sweep.client", mock_client):
        result = await assess_tag_quality(
            title="Test", summary="Test", tags=["a", "b"]
        )

    assert result["keep"] == ["a", "b"]
    assert result["remove"] == []


@pytest.mark.asyncio
async def test_sweep_user_updates_documents():
    from app.services.tag_quality_sweep import sweep_user

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "d1", "title": "Doc 1", "summary": "S1", "topics": ["climate", "key findings", "action items"]},
        {"id": "d2", "title": "Doc 2", "summary": "S2", "topics": ["energy", "key findings", "executive summary"]},
        {"id": "d3", "title": "Doc 3", "summary": "S3", "topics": ["policy", "key findings"]},
    ]
    mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    mock_sb.table.return_value.insert.return_value.execute.return_value = None

    async def fake_assess(title, summary, tags):
        keep = [t for t in tags if t not in {"key findings", "action items", "executive summary"}]
        remove = [t for t in tags if t in {"key findings", "action items", "executive summary"}]
        return {"keep": keep, "remove": remove}

    with patch("app.services.tag_quality_sweep.get_service_supabase_client", return_value=mock_sb), \
         patch("app.services.tag_quality_sweep.assess_tag_quality", side_effect=fake_assess), \
         patch("app.services.tag_quality_sweep.settings") as mock_settings:
        mock_settings.tag_quality_sweep_sample_size = 10
        mock_settings.tag_quality_auto_block_threshold = 3

        result = await sweep_user("user-1")

    assert result["docs_updated"] == 3
    assert "key findings" in result["auto_blocked"]
    assert "action items" not in result["auto_blocked"]


@pytest.mark.asyncio
async def test_sweep_user_skips_docs_with_no_topics():
    from app.services.tag_quality_sweep import sweep_user

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "d1", "title": "Doc 1", "summary": "S1", "topics": []},
    ]

    with patch("app.services.tag_quality_sweep.get_service_supabase_client", return_value=mock_sb), \
         patch("app.services.tag_quality_sweep.settings") as mock_settings:
        mock_settings.tag_quality_sweep_sample_size = 10
        mock_settings.tag_quality_auto_block_threshold = 3

        result = await sweep_user("user-1")

    assert result["docs_updated"] == 0
