-- Fix embedding dimension from 1536 to 2048 to match local model
-- HNSW index has a 2000-dim limit in pgvector, so we drop it.
-- Sequential scan is fine for dev-scale data; add IVFFlat later if needed.
DROP INDEX IF EXISTS idx_chunks_embedding;
ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(2048);

-- Recreate match_chunks with correct dimension
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding vector(2048),
    match_count INTEGER DEFAULT 5,
    match_threshold FLOAT DEFAULT 0.3
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    content TEXT,
    chunk_index INTEGER,
    token_count INTEGER,
    similarity FLOAT
)
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.document_id,
        c.content,
        c.chunk_index,
        c.token_count,
        (1 - (c.embedding <=> query_embedding))::FLOAT AS similarity
    FROM chunks c
    WHERE c.user_id = (SELECT auth.uid())
      AND (1 - (c.embedding <=> query_embedding)) > match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
