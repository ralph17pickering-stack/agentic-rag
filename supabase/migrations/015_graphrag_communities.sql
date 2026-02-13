-- GraphRAG communities: entity community detection and LLM summaries

CREATE TABLE IF NOT EXISTS communities (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    entity_ids   UUID[] NOT NULL DEFAULT '{}',
    document_ids UUID[] NOT NULL DEFAULT '{}',
    size         INT NOT NULL DEFAULT 0,
    level        INT NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_communities_user_id ON communities(user_id);
ALTER TABLE communities ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users see own communities" ON communities FOR ALL USING (auth.uid() = user_id);

-- RPC: get communities for a user (min size filter)
CREATE OR REPLACE FUNCTION get_user_communities(p_user_id UUID, p_min_size INT DEFAULT 2)
RETURNS TABLE (id UUID, title TEXT, summary TEXT, entity_ids UUID[], document_ids UUID[], size INT)
LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT id, title, summary, entity_ids, document_ids, size FROM communities
    WHERE user_id = p_user_id AND size >= p_min_size ORDER BY size DESC;
$$;

-- RPC: get communities that contain any of the given entity IDs
CREATE OR REPLACE FUNCTION get_communities_for_entities(p_user_id UUID, p_entity_ids UUID[])
RETURNS TABLE (id UUID, title TEXT, summary TEXT, size INT)
LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT id, title, summary, size FROM communities
    WHERE user_id = p_user_id AND entity_ids && p_entity_ids ORDER BY size DESC;
$$;
