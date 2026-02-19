-- Resize embedding vectors from 2048 (Qwen3 80B) to 768 (nomic-embed-text-v2-moe).
-- Existing chunk embeddings must be cleared and re-generated after applying this migration.
--
-- Steps after applying:
--   1. DELETE FROM chunks;  (or re-ingest documents to re-embed them)
--   2. Restart backend — it will re-embed on next ingest.

-- Drop indexes that depend on the column type
DROP INDEX IF EXISTS chunks_embedding_idx;

-- Resize the embedding column
ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(768);

-- Recreate HNSW index (768 < 2000 dim limit, so HNSW is usable again)
CREATE INDEX chunks_embedding_idx
  ON chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Update match_chunks RPC to use the new dimension
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding vector(768),
    match_count     int,
    p_user_id       uuid,
    date_from       date    DEFAULT NULL,
    date_to         date    DEFAULT NULL,
    recency_weight  float   DEFAULT 0.0
)
RETURNS TABLE (
    id              uuid,
    document_id     uuid,
    content         text,
    chunk_index     int,
    similarity      float
)
LANGUAGE plpgsql SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.document_id,
        c.content,
        c.chunk_index,
        CASE WHEN recency_weight > 0 AND d.document_date IS NOT NULL
             THEN (1 - recency_weight) * (1 - (c.embedding <=> query_embedding))
                  + recency_weight * (1 - exp(-0.1 * EXTRACT(EPOCH FROM (d.document_date - '2000-01-01'::date)) / 86400.0 / 365.0))
             ELSE 1 - (c.embedding <=> query_embedding)
        END AS similarity
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE d.user_id = p_user_id
      AND d.status = 'ready'
      AND (date_from IS NULL OR d.document_date >= date_from)
      AND (date_to   IS NULL OR d.document_date <= date_to)
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
