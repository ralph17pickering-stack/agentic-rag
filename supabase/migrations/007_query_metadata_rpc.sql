-- Read-only SQL execution RPC for text-to-SQL tool
-- SECURITY INVOKER ensures RLS applies (user only sees own data)

CREATE OR REPLACE FUNCTION query_document_metadata(sql_query TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    trimmed TEXT;
    result JSONB;
BEGIN
    trimmed := UPPER(LTRIM(sql_query));

    -- Only allow SELECT statements
    IF NOT trimmed LIKE 'SELECT%' THEN
        RAISE EXCEPTION 'Only SELECT statements are allowed';
    END IF;

    -- Reject mutation keywords
    IF trimmed ~ '\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY)\b' THEN
        RAISE EXCEPTION 'Mutation statements are not allowed';
    END IF;

    EXECUTE format(
        'SELECT COALESCE(jsonb_agg(row_to_json(t)), ''[]''::jsonb) FROM (%s) t',
        sql_query
    ) INTO result;

    RETURN result;
END;
$$;
