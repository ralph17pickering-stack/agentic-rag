-- GraphRAG schema: entities, relationships, chunk_entities, and helper RPCs

CREATE TABLE IF NOT EXISTS entities (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    name_lower  TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'UNKNOWN',
    description TEXT,
    document_ids UUID[] DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, name_lower)
);
CREATE INDEX IF NOT EXISTS idx_entities_user_id    ON entities(user_id);
CREATE INDEX IF NOT EXISTS idx_entities_name_lower ON entities(user_id, name_lower);

CREATE TABLE IF NOT EXISTS relationships (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_id     UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_id     UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    description   TEXT,
    weight        FLOAT DEFAULT 1.0,
    document_ids  UUID[] DEFAULT '{}',
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, source_id, target_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_relationships_user   ON relationships(user_id);
CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_id);

CREATE TABLE IF NOT EXISTS chunk_entities (
    chunk_id  UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    user_id   UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    PRIMARY KEY (chunk_id, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_chunk_entities_entity ON chunk_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_chunk_entities_chunk  ON chunk_entities(chunk_id);

ALTER TABLE entities       ENABLE ROW LEVEL SECURITY;
ALTER TABLE relationships  ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunk_entities ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users see own entities"       ON entities       FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users see own relationships"  ON relationships  FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "users see own chunk_entities" ON chunk_entities FOR ALL USING (auth.uid() = user_id);

-- RPC: entity-neighbour expansion (used in Sub-plan C)
CREATE OR REPLACE FUNCTION get_entity_neighbor_chunks(p_user_id UUID, p_entity_ids UUID[], p_limit INT DEFAULT 10)
RETURNS TABLE (chunk_id UUID, entity_count BIGINT) LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT ce.chunk_id, COUNT(DISTINCT ce.entity_id) AS entity_count
    FROM chunk_entities ce
    WHERE ce.user_id = p_user_id AND ce.entity_id = ANY(p_entity_ids)
    GROUP BY ce.chunk_id ORDER BY entity_count DESC LIMIT p_limit;
$$;

-- RPC: upsert entity (avoids raw SQL in Python client)
CREATE OR REPLACE FUNCTION upsert_entity(
    p_user_id UUID, p_name TEXT, p_name_lower TEXT,
    p_entity_type TEXT, p_description TEXT, p_document_id UUID
)
RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE v_id UUID;
BEGIN
    INSERT INTO entities(user_id, name, name_lower, entity_type, description, document_ids)
    VALUES (p_user_id, p_name, p_name_lower, p_entity_type, p_description, ARRAY[p_document_id])
    ON CONFLICT (user_id, name_lower) DO UPDATE SET
        entity_type  = EXCLUDED.entity_type,
        description  = COALESCE(EXCLUDED.description, entities.description),
        document_ids = array_append(array_remove(entities.document_ids, p_document_id), p_document_id),
        updated_at   = NOW()
    RETURNING id INTO v_id;
    RETURN v_id;
END; $$;

-- RPC: upsert relationship
CREATE OR REPLACE FUNCTION upsert_relationship(
    p_user_id UUID, p_source_id UUID, p_target_id UUID,
    p_relation_type TEXT, p_description TEXT, p_document_id UUID
)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    INSERT INTO relationships(user_id, source_id, target_id, relation_type, description, document_ids)
    VALUES (p_user_id, p_source_id, p_target_id, p_relation_type, p_description, ARRAY[p_document_id])
    ON CONFLICT (user_id, source_id, target_id, relation_type) DO UPDATE SET
        weight       = relationships.weight + 1,
        description  = COALESCE(EXCLUDED.description, relationships.description),
        document_ids = array_append(array_remove(relationships.document_ids, p_document_id), p_document_id),
        updated_at   = NOW();
END; $$;

-- RPCs used by Sub-Plan C (retrieval)
CREATE OR REPLACE FUNCTION get_entities_for_chunks(p_user_id UUID, p_chunk_ids UUID[])
RETURNS TABLE (entity_id UUID, entity_name TEXT, entity_type TEXT)
LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT DISTINCT e.id, e.name, e.entity_type
    FROM chunk_entities ce JOIN entities e ON e.id = ce.entity_id
    WHERE ce.user_id = p_user_id AND ce.chunk_id = ANY(p_chunk_ids);
$$;

-- BFS shortest path between two entities (up to depth 4)
CREATE OR REPLACE FUNCTION find_entity_path(
    p_user_id UUID, p_source_lower TEXT, p_target_lower TEXT, p_max_depth INT DEFAULT 4
)
RETURNS TABLE (entity_id UUID, entity_name TEXT, hop INT)
LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
DECLARE v_source_id UUID; v_target_id UUID;
BEGIN
    SELECT id INTO v_source_id FROM entities WHERE user_id = p_user_id AND name_lower = p_source_lower LIMIT 1;
    SELECT id INTO v_target_id FROM entities WHERE user_id = p_user_id AND name_lower = p_target_lower LIMIT 1;
    IF v_source_id IS NULL OR v_target_id IS NULL THEN RETURN; END IF;
    RETURN QUERY
    WITH RECURSIVE bfs AS (
        SELECT v_source_id AS node_id, ARRAY[v_source_id] AS path, 0 AS depth
        UNION ALL
        SELECT
            CASE WHEN r.source_id = bfs.node_id THEN r.target_id ELSE r.source_id END,
            bfs.path || CASE WHEN r.source_id = bfs.node_id THEN r.target_id ELSE r.source_id END,
            bfs.depth + 1
        FROM bfs JOIN relationships r
          ON (r.source_id = bfs.node_id OR r.target_id = bfs.node_id)
         AND r.user_id = p_user_id
         AND NOT (CASE WHEN r.source_id = bfs.node_id THEN r.target_id ELSE r.source_id END) = ANY(bfs.path)
        WHERE bfs.depth < p_max_depth AND NOT v_target_id = ANY(bfs.path)
    )
    SELECT DISTINCT e.id, e.name, b.depth FROM bfs b JOIN entities e ON e.id = b.node_id
    WHERE v_target_id = ANY(b.path) ORDER BY b.depth;
END; $$;
