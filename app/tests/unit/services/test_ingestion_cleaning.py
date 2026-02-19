from backend.app.services.document_cleaner import clean_text


def test_clean_text_used_in_pipeline_result_is_deterministic():
    """Round-tripping clean text through clean_text() again is a no-op."""
    raw = "  Title\r\n\r\nSome text\x00 with issues.\n\n\n\nEnd."
    once = clean_text(raw)
    twice = clean_text(once)
    assert once == twice
