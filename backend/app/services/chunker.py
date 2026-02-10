import tiktoken
from pydantic import BaseModel
from app.config import settings
from app.services.hashing import sha256_text

encoding = tiktoken.get_encoding("cl100k_base")


class Chunk(BaseModel):
    content: str
    chunk_index: int
    token_count: int
    content_hash: str


def chunk_text(text: str) -> list[Chunk]:
    """Split text into fixed-size token chunks with overlap."""
    tokens = encoding.encode(text)
    chunks = []
    start = 0
    index = 0

    while start < len(tokens):
        end = start + settings.chunk_size
        chunk_tokens = tokens[start:end]
        content = encoding.decode(chunk_tokens)
        chunks.append(
            Chunk(
                content=content,
                chunk_index=index,
                token_count=len(chunk_tokens),
                content_hash=sha256_text(content),
            )
        )
        start += settings.chunk_size - settings.chunk_overlap
        index += 1

    return chunks
