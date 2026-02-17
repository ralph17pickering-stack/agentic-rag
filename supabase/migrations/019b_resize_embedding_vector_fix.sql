-- Recovery migration: migration 019 partially applied.
-- State after 019: column still vector(2048), no HNSW index, match_chunks already takes vector(768).
--
-- Fix: clear existing chunk rows (incompatible dimension), drop+re-add the column,
-- rebuild the HNSW index, and reset documents for re-ingestion.

-- 1. Clear existing chunk data (2048-dim vectors are incompatible with the new 768-dim column)
DELETE FROM chunks;

-- 2. Reset all documents to pending so they are re-embedded on next startup
UPDATE documents SET status = 'pending', chunk_count = 0 WHERE status IN ('ready', 'error');

-- 3. Resize the column — safe now that the table is empty
ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(768)
    USING NULL::vector(768);

-- 4. Recreate HNSW index (768 < 2000 dim limit — HNSW is usable)
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
