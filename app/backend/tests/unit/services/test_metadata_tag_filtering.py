import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_extract_metadata_filters_blocked_tags():
    """Blocked tags should be removed from extracted topics."""
    from app.services.metadata import extract_metadata
    with patch("app.services.metadata._extract_topics", return_value=[
        "climate change", "communications plan", "key findings",
        "renewable energy", "executive summary", "carbon policy",
    ]):
        result = await extract_metadata(
            "some text",
            filename="test.pdf",
            blocked_tags={"communications plan", "executive summary"},
        )
    assert "communications plan" not in result.topics
    assert "executive summary" not in result.topics
    assert "climate change" in result.topics
    assert "renewable energy" in result.topics


@pytest.mark.asyncio
async def test_extract_metadata_caps_at_max_per_document():
    """Topics should be capped at tag_max_per_document after filtering."""
    from app.services.metadata import extract_metadata
    many_tags = [f"tag{i}" for i in range(12)]
    with patch("app.services.metadata._extract_topics", return_value=many_tags):
        result = await extract_metadata("some text", filename="test.pdf")
    assert len(result.topics) <= 8


@pytest.mark.asyncio
async def test_extract_metadata_no_blocked_tags_default():
    """Without blocked_tags argument, all topics pass through (up to max)."""
    from app.services.metadata import extract_metadata
    with patch("app.services.metadata._extract_topics", return_value=["a", "b", "c"]):
        result = await extract_metadata("some text", filename="test.pdf")
    assert result.topics == ["a", "b", "c"]
