import re


def clean_text(text: str) -> str:
    """Clean extracted document text before chunking.

    - Normalises line endings (CRLF → LF)
    - Removes non-printable control characters (keeps printable ASCII + extended latin)
    - Collapses tabs and runs of spaces within a line to a single space
    - Strips leading/trailing whitespace per line
    - Preserves paragraph breaks (double newlines) for document structure
    - Collapses 3+ consecutive blank lines to at most 2
    """
    if not text:
        return text

    # Normalise line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Remove non-printable control chars (keep \t=0x09, \n=0x0A, printable 0x20–0x7E, extended 0x80–0xFF)
    text = re.sub(r'[^\x09\x0A\x20-\x7E\x80-\xFF]', '', text)

    # Collapse tabs and runs of spaces/tabs within each line
    lines = text.split('\n')
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in lines]
    text = '\n'.join(lines)

    # Collapse 3+ consecutive blank lines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()
