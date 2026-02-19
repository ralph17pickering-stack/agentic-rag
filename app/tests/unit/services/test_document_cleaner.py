import pytest
from backend.app.services.document_cleaner import clean_text


def test_clean_text_removes_extra_spaces_within_line():
    assert clean_text("hello   world") == "hello world"


def test_clean_text_strips_leading_trailing_whitespace():
    assert clean_text("  hello world  ") == "hello world"


def test_clean_text_preserves_paragraph_breaks():
    """Double newlines (paragraph breaks) must be preserved."""
    text = "paragraph one\n\nparagraph two"
    assert "paragraph one" in clean_text(text)
    assert "paragraph two" in clean_text(text)
    assert "\n\n" in clean_text(text)


def test_clean_text_collapses_excessive_blank_lines():
    """3+ consecutive newlines collapse to 2."""
    text = "line one\n\n\n\nline two"
    result = clean_text(text)
    assert "\n\n\n" not in result
    assert "line one" in result
    assert "line two" in result


def test_clean_text_normalizes_crlf_line_endings():
    text = "line one\r\nline two\r\nline three"
    result = clean_text(text)
    assert "\r" not in result
    assert "line one" in result
    assert "line two" in result


def test_clean_text_removes_non_printable_characters():
    """Control characters like \x00, \x01 etc. are stripped."""
    text = "hello\x00world\x01foo"
    result = clean_text(text)
    assert "\x00" not in result
    assert "\x01" not in result
    assert "helloworld" in result or "hello" in result


def test_clean_text_preserves_tabs_normalised_to_space():
    """Tabs within a line become spaces."""
    text = "col1\tcol2\tcol3"
    result = clean_text(text)
    assert "\t" not in result
    assert "col1" in result
    assert "col2" in result


def test_clean_text_empty_string():
    assert clean_text("") == ""


def test_clean_text_only_whitespace():
    assert clean_text("   \n\n\t  ") == ""
