# Lessons Learned

## Session: Applying Supabase Database Migration

### Supabase Self-Hosted Networking

**Host ports 5432 and 6543 are Supavisor (the connection pooler), NOT direct Postgres.**

The `docker-compose.yml` maps these ports from the `supavisor` service, not the `db` service. The actual Postgres container (`supabase-db`) does not expose any ports to the host — it's only reachable within the Docker network.

Attempting to connect as `postgres` on port 5432 from the host gives:
```
FATAL: Tenant or user not found
```

This is Supavisor rejecting the connection because it expects tenant-qualified usernames.

### Connecting to the Database

**Two methods:**

1. **Direct access via `docker exec`** (bypasses the pooler entirely):
   ```bash
   docker exec supabase-db psql -U postgres -d postgres
   ```
   Pipe SQL files with `-f -`:
   ```bash
   docker exec supabase-db psql -U postgres -d postgres -f - < migration.sql
   ```

2. **Through Supavisor pooler** (from host, port 5432 or 6543):
   Use tenant-qualified usernames: `postgres.your-tenant-id`
   The tenant ID is set in `.env` as `POOLER_TENANT_ID` (default: `your-tenant-id`).
   ```python
   psycopg2.connect(
       host='127.0.0.1', port=5432,
       user='postgres.your-tenant-id',
       password='<POSTGRES_PASSWORD>',
       dbname='postgres'
   )
   ```

### Key File Locations

| File | Purpose |
|------|---------|
| `/home/ralph/dev/supabase-project/docker-compose.yml` | Supabase service definitions and port mappings |
| `/home/ralph/dev/supabase-project/.env` | All Supabase configuration (passwords, keys, ports) |
| `/home/ralph/dev/supabase-project/supbase-secrets.txt` | Generated secrets reference |
| `/home/ralph/dev/agentic-rag/supabase/migrations/` | App-specific SQL migrations |

### Applying Migrations Without Supabase CLI

Since the project doesn't use `supabase init` / `config.toml`, migrations are applied manually. The most reliable method is `docker exec` piping the SQL file directly to psql inside the container. This avoids all pooler/networking complications.

### psql Not Installed on Host

The host machine doesn't have `psql` installed. Options:
- Use `docker exec supabase-db psql ...` (preferred)
- Use Python with `psycopg2-binary` through the backend venv and connect via Supavisor

---

## Session: Module 2 — Document Ingestion & Retrieval

### Local LLM Embeddings Require Explicit Startup Flag

The local LLM server at `:8081` does **not** serve the `/v1/embeddings` endpoint by default. Calling it returns:
```json
{"error":{"code":501,"message":"This server does not support embeddings. Start it with `--embeddings`","type":"not_supported_error"}}
```

**Action needed**: Restart the local LLM with the `--embeddings` flag before testing ingestion or retrieval. Verify the embedding dimension matches `embedding_dim` in `backend/app/config.py` (currently: 2048).

### pgvector Works Out of the Box in Supabase Self-Hosted

`CREATE EXTENSION IF NOT EXISTS vector` succeeds without any extra setup in the `supabase-db` container. No need to install packages or modify Dockerfiles — the extension is pre-bundled.

### Supabase Storage Bucket Must Exist Before Upload

Storage uploads fail if the bucket doesn't exist. The app creates the `documents` bucket at startup via the `lifespan` handler using the service role client. This runs once per server start — if the bucket already exists, it's a no-op.

### Service Role Client for Background Tasks

Background ingestion (`asyncio.create_task`) has no user JWT, so it can't use the normal RLS-scoped Supabase client. The `get_service_supabase_client()` uses the service role key to bypass RLS. The `user_id` is set explicitly on each inserted row to maintain data ownership.

### Splitting Migration Files for Functions

RPC functions like `match_chunks` are kept in a separate migration file (`002b_match_chunks_function.sql`) from table definitions. This makes it easy to `CREATE OR REPLACE FUNCTION` independently when the function signature or logic changes, without re-running table creation.

### HNSW Index Has a 2000-Dimension Limit in pgvector

When the local embedding model returns 2048-dimensional vectors, `CREATE INDEX USING hnsw` fails:
```
ERROR: column cannot have more than 2000 dimensions for hnsw index
```

**Workaround**: Skip the HNSW index entirely — sequential scan is fine for dev-scale data. If performance becomes an issue, use IVFFlat instead (no dimension limit, but requires `lists` parameter tuning based on dataset size).

### Tool-Calling Chat: Non-Streaming First, Streaming Second

When integrating tool calling with SSE streaming, use a two-phase approach:
1. **Non-streaming call with tools** — detect if the LLM wants to call a tool
2. **If tool call**: execute the tool, append the result, then make a **streaming call** for the final response
3. **If no tool call**: yield the content from the non-streaming response directly

This avoids the complexity of parsing tool calls from a streaming response. The first call is fast (just deciding whether to use a tool), so the user barely notices the non-streaming phase.

### FormData Uploads: Don't Set Content-Type

When uploading files via `FormData`, do **not** set `Content-Type: application/json` (the default in `apiFetch`). The browser must auto-set the multipart boundary. Use `fetch` directly instead of `apiFetch` for file uploads.
