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
