-- 006: Hybrid Search - add full-text search to chunks

-- 1. Add tsvector column
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- 2. Backfill existing rows
UPDATE chunks SET search_vector = to_tsvector('english', content) WHERE search_vector IS NULL;

-- 3. GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_chunks_search_vector ON chunks USING GIN(search_vector);

-- 4. Auto-populate trigger on INSERT/UPDATE
CREATE OR REPLACE FUNCTION chunks_search_vector_update() RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', NEW.content);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS chunks_search_vector_trigger ON chunks;
CREATE TRIGGER chunks_search_vector_trigger
    BEFORE INSERT OR UPDATE OF content ON chunks
    FOR EACH ROW EXECUTE FUNCTION chunks_search_vector_update();

-- 5. Keyword search RPC (mirrors match_chunks structure)
CREATE OR REPLACE FUNCTION match_chunks_keyword(
    search_query TEXT,
    match_count INTEGER DEFAULT 20,
    filter_date_from DATE DEFAULT NULL,
    filter_date_to DATE DEFAULT NULL
)
RETURNS TABLE (
    id UUID, document_id UUID, content TEXT, chunk_index INTEGER,
    token_count INTEGER, rank FLOAT,
    doc_title TEXT, doc_topics TEXT[], doc_date DATE
)
LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
    RETURN QUERY
    SELECT c.id, c.document_id, c.content, c.chunk_index, c.token_count,
        ts_rank_cd(c.search_vector, websearch_to_tsquery('english', search_query))::FLOAT AS rank,
        d.title, d.topics, COALESCE(d.document_date, d.created_at::date)
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE c.user_id = (SELECT auth.uid())
      AND c.search_vector @@ websearch_to_tsquery('english', search_query)
      AND (filter_date_from IS NULL OR COALESCE(d.document_date, d.created_at::date) >= filter_date_from)
      AND (filter_date_to IS NULL OR COALESCE(d.document_date, d.created_at::date) <= filter_date_to)
    ORDER BY rank DESC LIMIT match_count;
END; $$;
