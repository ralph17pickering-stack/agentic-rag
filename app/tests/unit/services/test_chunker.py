from backend.app.services.chunker import chunk_text


def test_no_headings_falls_back_to_token_chunking():
    """Plain text with no headings uses existing token-based chunking."""
    text = "word " * 1000  # plenty of tokens, no headings
    chunks = chunk_text(text)
    assert len(chunks) > 1
    for c in chunks:
        assert c.content.strip()


def test_single_short_section_is_one_chunk():
    """A document with one heading and short body → single chunk."""
    text = "# Introduction\n\nThis is a short intro."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert "# Introduction" in chunks[0].content


def test_two_sections_produce_separate_chunks():
    """Two short sections stay in separate chunks."""
    text = "# Section One\n\nContent of section one.\n\n# Section Two\n\nContent of section two."
    chunks = chunk_text(text)
    assert len(chunks) >= 2
    combined = " ".join(c.content for c in chunks)
    assert "# Section One" in combined
    assert "# Section Two" in combined


def test_heading_preserved_in_continuation_chunks():
    """When a section exceeds chunk_size, the heading is prepended to each continuation."""
    long_body = "word " * 600  # ~600 tokens
    text = f"# Big Section\n\n{long_body}"
    chunks = chunk_text(text)
    assert len(chunks) >= 2
    for c in chunks:
        assert "# Big Section" in c.content


def test_chunk_indices_are_sequential():
    """chunk_index values must be 0, 1, 2, ... regardless of split mode."""
    text = "# A\n\nsome content\n\n# B\n\nmore content\n\n# C\n\neven more content"
    chunks = chunk_text(text)
    for i, c in enumerate(chunks):
        assert c.chunk_index == i


def test_chunks_have_content_hash():
    """Every chunk must have a non-empty content_hash."""
    text = "# Hello\n\nSome text."
    chunks = chunk_text(text)
    for c in chunks:
        assert c.content_hash
        assert len(c.content_hash) == 64  # sha256 hex


def test_table_not_split_mid_table():
    """A markdown table within a section must not be broken in half."""
    table = (
        "| Name | Score |\n"
        "| --- | --- |\n"
        "| Alice | 95 |\n"
        "| Bob | 87 |\n"
        "| Carol | 72 |\n"
    )
    text = f"# Results\n\n{table}"
    chunks = chunk_text(text)
    table_chunk = next((c for c in chunks if "| Name | Score |" in c.content), None)
    assert table_chunk is not None
    assert "| --- | --- |" in table_chunk.content


def test_empty_text_returns_empty_list():
    chunks = chunk_text("")
    assert chunks == []


def test_whitespace_only_returns_empty_list():
    chunks = chunk_text("   \n  \n  ")
    assert chunks == []
