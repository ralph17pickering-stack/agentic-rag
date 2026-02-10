-- Add metadata columns to documents
ALTER TABLE documents ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS summary TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS topics TEXT[] DEFAULT '{}';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_date DATE;

-- Replace match_chunks to return doc metadata and support date filtering + recency boost
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding vector(2048),
    match_count INTEGER DEFAULT 5,
    match_threshold FLOAT DEFAULT 0.3,
    filter_date_from DATE DEFAULT NULL,
    filter_date_to DATE DEFAULT NULL,
    recency_weight FLOAT DEFAULT 0.0
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    content TEXT,
    chunk_index INTEGER,
    token_count INTEGER,
    similarity FLOAT,
    doc_title TEXT,
    doc_topics TEXT[],
    doc_date DATE
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
        CASE
            WHEN recency_weight > 0 AND d.document_date IS NOT NULL THEN
                ((1 - recency_weight) * (1 - (c.embedding <=> query_embedding))
                 + recency_weight * (1.0 / (1.0 + EXTRACT(EPOCH FROM (now() - d.document_date::timestamp)) / 86400.0 / 365.0)))::FLOAT
            ELSE
                (1 - (c.embedding <=> query_embedding))::FLOAT
        END AS similarity,
        d.title AS doc_title,
        d.topics AS doc_topics,
        COALESCE(d.document_date, d.created_at::date) AS doc_date
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE c.user_id = (SELECT auth.uid())
      AND (1 - (c.embedding <=> query_embedding)) > match_threshold
      AND (filter_date_from IS NULL OR COALESCE(d.document_date, d.created_at::date) >= filter_date_from)
      AND (filter_date_to IS NULL OR COALESCE(d.document_date, d.created_at::date) <= filter_date_to)
    ORDER BY
        CASE
            WHEN recency_weight > 0 AND d.document_date IS NOT NULL THEN
                ((1 - recency_weight) * (1 - (c.embedding <=> query_embedding))
                 + recency_weight * (1.0 / (1.0 + EXTRACT(EPOCH FROM (now() - d.document_date::timestamp)) / 86400.0 / 365.0)))
            ELSE
                (1 - (c.embedding <=> query_embedding))
        END DESC
    LIMIT match_count;
END;
$$;
