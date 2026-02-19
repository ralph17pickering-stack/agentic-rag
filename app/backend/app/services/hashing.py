import hashlib


def sha256_hex(data: bytes) -> str:
    """SHA-256 hash of raw bytes (for file content)."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """SHA-256 hash of text (for chunk content)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
