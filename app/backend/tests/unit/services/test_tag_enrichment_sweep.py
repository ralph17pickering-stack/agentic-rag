import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ── suggest_new_tags ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_suggest_new_tags_returns_list():
    from app.services.tag_enrichment_sweep import suggest_new_tags

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"new_tags": ["biodiversity", "carbon offset"]}'

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.tag_enrichment_sweep.client", mock_client):
        result = await suggest_new_tags(
            title="Forest Policy",
            summary="A review of forest carbon policies.",
            existing_tags=["climate", "policy"],
            excerpt="Forests absorb carbon and support biodiversity...",
        )

    assert "biodiversity" in result
    assert "carbon offset" in result
    # Must not repeat existing tags
    assert "climate" not in result
    assert "policy" not in result


@pytest.mark.asyncio
async def test_suggest_new_tags_returns_empty_on_llm_failure():
    from app.services.tag_enrichment_sweep import suggest_new_tags

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM down"))

    with patch("app.services.tag_enrichment_sweep.client", mock_client):
        result = await suggest_new_tags("T", "S", ["a"], "excerpt")

    assert result == []


# ── verify_tag_relevance ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_tag_relevance_returns_true():
    from app.services.tag_enrichment_sweep import verify_tag_relevance

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"relevant": true}'

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.tag_enrichment_sweep.client", mock_client):
        result = await verify_tag_relevance(
            tag="biodiversity",
            title="Forest Policy",
            summary="A review of forest carbon policies.",
        )

    assert result is True


@pytest.mark.asyncio
async def test_verify_tag_relevance_returns_false():
    from app.services.tag_enrichment_sweep import verify_tag_relevance

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"relevant": false}'

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.tag_enrichment_sweep.client", mock_client):
        result = await verify_tag_relevance("biodiversity", "Cooking", "A recipe book.")

    assert result is False


@pytest.mark.asyncio
async def test_verify_tag_relevance_returns_false_on_failure():
    from app.services.tag_enrichment_sweep import verify_tag_relevance

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM down"))

    with patch("app.services.tag_enrichment_sweep.client", mock_client):
        result = await verify_tag_relevance("tag", "T", "S")

    assert result is False


# ── enrich_batch ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enrich_batch_applies_new_tags_and_updates_timestamp():
    from app.services.tag_enrichment_sweep import enrich_batch

    doc = {
        "id": "doc-1",
        "user_id": "user-1",
        "title": "Forest Policy",
        "summary": "Carbon policy review.",
        "topics": ["policy"],
    }

    mock_sb = MagicMock()
    # chunks fetch
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"content": "Forests absorb carbon and support biodiversity."}
    ]
    # topics novelty check — tag not found anywhere
    mock_sb.table.return_value.select.return_value.filter.return_value.limit.return_value.execute.return_value.data = []
    # chunk search for propagation
    mock_sb.table.return_value.select.return_value.filter.return_value.execute.return_value.data = []
    # update call
    mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = None

    async def fake_suggest(title, summary, existing_tags, excerpt):
        return ["biodiversity"]

    async def fake_verify(tag, title, summary):
        return True

    with patch("app.services.tag_enrichment_sweep.get_service_supabase_client", return_value=mock_sb), \
         patch("app.services.tag_enrichment_sweep.suggest_new_tags", side_effect=fake_suggest), \
         patch("app.services.tag_enrichment_sweep.verify_tag_relevance", side_effect=fake_verify), \
         patch("app.services.tag_enrichment_sweep.settings") as mock_settings:
        mock_settings.tag_enrichment_max_age_days = 60

        result = await enrich_batch([doc])

    assert result["docs_enriched"] == 1
    assert "biodiversity" in result["new_tags_applied"]


# ── run_enrichment_sweep ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_enrichment_sweep_skips_when_not_idle():
    from app.services.tag_enrichment_sweep import run_enrichment_sweep

    with patch("app.services.tag_enrichment_sweep.is_idle", return_value=False):
        result = await run_enrichment_sweep()

    assert result == {"skipped": "not_idle"}


@pytest.mark.asyncio
async def test_run_enrichment_sweep_skips_when_all_fresh():
    from app.services.tag_enrichment_sweep import run_enrichment_sweep

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.or_.return_value.limit.return_value.execute.return_value.data = []

    with patch("app.services.tag_enrichment_sweep.is_idle", return_value=True), \
         patch("app.services.tag_enrichment_sweep.get_service_supabase_client", return_value=mock_sb):
        result = await run_enrichment_sweep()

    assert result == {"skipped": "all_fresh"}


@pytest.mark.asyncio
async def test_run_enrichment_sweep_uses_python_cutoff_not_sql_expression():
    """The or_ filter must use a computed ISO timestamp, not a SQL expression."""
    from app.services.tag_enrichment_sweep import run_enrichment_sweep

    captured_or_args = []

    def make_mock_sb():
        mock_sb = MagicMock()
        or_mock = MagicMock()
        or_mock.limit.return_value.execute.return_value.data = []
        def capture_or(arg):
            captured_or_args.append(arg)
            return or_mock
        mock_sb.table.return_value.select.return_value.or_ = capture_or
        return mock_sb

    with patch("app.services.tag_enrichment_sweep.is_idle", return_value=True), \
         patch("app.services.tag_enrichment_sweep.get_service_supabase_client", side_effect=make_mock_sb):
        await run_enrichment_sweep()

    # Verify the or_ filter does NOT contain the SQL expression
    assert captured_or_args, "or_ was never called"
    for arg in captured_or_args:
        assert "interval" not in arg, f"SQL interval expression found in filter: {arg!r}"
        assert "now()" not in arg, f"SQL now() found in filter: {arg!r}"


@pytest.mark.asyncio
async def test_propagate_tag_encodes_multiword_tag_for_fts():
    """Multi-word tags must be joined with & for valid tsquery syntax."""
    from app.services.tag_enrichment_sweep import _propagate_tag

    captured_fts_values = []

    mock_sb = MagicMock()

    # Novelty check — tag not found
    novelty_mock = MagicMock()
    novelty_mock.execute.return_value.data = []
    mock_sb.table.return_value.select.return_value.filter.return_value.limit.return_value = novelty_mock

    # FTS search — capture the value passed
    fts_mock = MagicMock()
    fts_mock.execute.return_value.data = []
    # Also support novelty check chain: .filter(...).limit(1).execute().data
    fts_mock.limit.return_value.execute.return_value.data = []
    original_filter = mock_sb.table.return_value.select.return_value.filter

    def capture_filter(col, op, val):
        if op == "fts":
            captured_fts_values.append(val)
        return fts_mock

    mock_sb.table.return_value.select.return_value.filter = capture_filter

    await _propagate_tag(mock_sb, "carbon offset", origin_doc_id="doc-x")

    assert captured_fts_values, "fts filter was never called"
    assert captured_fts_values[0] == "carbon & offset", \
        f"Expected 'carbon & offset', got {captured_fts_values[0]!r}"
