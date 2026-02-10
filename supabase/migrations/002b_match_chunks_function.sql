-- Similarity search RPC function
-- Uses SECURITY INVOKER so RLS policies are enforced via auth.uid()
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding vector(1536),
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
