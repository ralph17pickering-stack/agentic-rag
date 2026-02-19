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

### Don't Run Docker/Infrastructure Commands — Print Them Instead

Bash permission mode blocks commands that touch Docker, `docker compose`, or other infrastructure outside the project directory. Instead of attempting to run these commands (which will be denied), **print the command for the user to run manually**. This applies to:
- `docker compose restart/up/down`
- `docker exec ...`
- Any command operating on `/home/ralph/dev/supabase-project/`

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

**Action needed**: Restart the local LLM with the `--embeddings` flag before testing ingestion or retrieval. Verify the embedding dimension matches `embedding_dim` in `app/backapp/frontend/app/config.py` (currently: 2048).

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

---

## Session: Module 5 — Multi-Format Support

### Extraction as a Dispatcher Pattern

Adding new file formats is cleanest as a single `extract_text(file_bytes, file_type) -> str` dispatcher that normalizes any format to plain text before the existing chunking pipeline. This keeps the ingestion service format-agnostic — it only ever sees plain text.

### Content-Type Matters for Supabase Storage

When uploading binary formats (PDF, DOCX) to Supabase Storage, the content-type must match the actual file format. The original code hardcoded `text/plain`, which works for txt/md but causes issues when downloading binary files. Use a `CONTENT_TYPES` mapping keyed by extension.

### DB CHECK Constraints Need Explicit Widening

Adding new allowed values to an existing `CHECK` constraint requires dropping and recreating it — Postgres doesn't support `ALTER CONSTRAINT` to add values. Use `DROP CONSTRAINT IF EXISTS` + `ADD CONSTRAINT` in the migration for safety.

---

## Session: Module 6 — Hybrid Search & Reranking

### Reciprocal Rank Fusion (RRF) is Simple and Effective

RRF merges multiple ranked lists without needing normalized scores. Formula: `score = sum(1 / (k + rank + 1))` where `k=60` is standard. Chunks appearing in multiple lists naturally get higher scores. No tuning needed beyond the `k` constant.

### Postgres Full-Text Search Auto-Populates via Trigger

Adding a `tsvector` column with a `BEFORE INSERT OR UPDATE` trigger means new chunks automatically get their search vector populated during ingestion — no ingestion code changes needed. Existing rows are backfilled in the migration.

### LLM Reranking Needs Graceful Fallback

LLM-based reranking can fail (bad JSON, timeout, etc.). Always fall back to returning the original order truncated to `top_n` rather than failing the entire retrieval pipeline. Log the error for debugging.

### Keep Retrieval Signature Stable

The hybrid pipeline changes internals but keeps `retrieve_chunks()` signature identical. This means zero changes to the chat router, LLM tool definition, or frontend — the pipeline is an implementation detail behind a stable interface.

---

## Session: Debugging Document Upload Failure

### `docker exec` Without `-i` Silently Drops Stdin

**Critical**: `docker exec supabase-db psql -U postgres -d postgres -f - < file.sql` does **not** work. Without the `-i` flag, `docker exec` does not forward stdin to the container. The host shell opens the file and redirects it, but Docker never passes it through. psql receives empty input, does nothing, and exits with code 0 — **no error, no output, no indication of failure**.

**Correct command:**
```bash
docker exec -i supabase-db psql -U postgres -d postgres -f - < file.sql
```

This caused migrations 003–006 to appear applied when they never actually ran.

### FastAPI UploadFile vs Starlette UploadFile (Version Mismatch)

In FastAPI 0.128.6 + Starlette 0.52.1, `fastapi.UploadFile` and `starlette.datastructures.UploadFile` are **different classes**. When using `request.form()` (a Starlette method) to parse multipart uploads, the returned file parts are Starlette `UploadFile` instances. An `isinstance(file, fastapi.UploadFile)` check will always return `False`.

**Fix:** Import `UploadFile` from `starlette.datastructures` when using `request.form()` directly.

### CORS Errors Often Mask Backend 500s

When a FastAPI endpoint raises an unhandled exception, the 500 response may lack CORS headers (the error propagates before the CORS middleware can add them). The browser then reports "CORS Missing Allow Origin" instead of showing the actual server error. **Always check backend logs** (`/tmp/agentic-rag-backend.log`) when you see a CORS error — the real cause is usually an unhandled exception.

### Supabase Storage Has Default-Deny RLS

The `storage.objects` table has RLS enabled with no default policies. Uploading via a user-scoped Supabase client (anon key + JWT) will get a 403 "new row violates row-level security policy" unless explicit policies exist.

**Fix:** Use the service role client (`get_service_supabase_client()`) for storage operations. The backend already authenticates the user via `get_current_user`, so bypassing storage RLS is safe. Keep the user-scoped client for `documents`/`chunks` table queries where RLS enforces data isolation.

### Verify Migrations Actually Applied

After running a migration, always verify the schema changed:
```bash
docker exec supabase-db psql -U postgres -d postgres -c "\d tablename"
```
Don't trust the exit code or lack of error output — especially with piped commands through Docker.

### Supabase SQL Editor as Migration Fallback

When `docker exec` is problematic (permissions, missing `-i` flag, credential issues), the Supabase Studio SQL editor (accessible via the web UI) is a reliable alternative for running migrations manually.

---

## Session: Module 7 — Additional Tools

### Multi-Tool Dispatch Generalizes Cleanly

The single-tool two-phase approach (non-streaming tool check → streaming final) generalizes to multi-tool with a loop: up to N rounds of non-streaming tool-check calls, processing all tool calls per round, then streaming the final response. The `ToolContext` dataclass replaces individual callback params and scales to any number of tools.

### ToolEvent Pattern for Non-Token SSE Data

When tools produce structured data for the frontend (e.g., web search results for a sidebar), yield a `ToolEvent` dataclass alongside token strings from the generator. The chat router checks `isinstance(event, ToolEvent)` and emits a different SSE field (`web_results` instead of `token`). This keeps the streaming interface clean — callers handle `str | ToolEvent`.

### SECURITY INVOKER for User-Scoped SQL Execution

Postgres functions default to `SECURITY DEFINER` (runs as the function owner). For text-to-SQL where the user's RLS context must apply, use `SECURITY INVOKER` so the function inherits the calling role's permissions. Combined with prefix + keyword checks, this safely restricts to read-only queries on user-visible data.

### Flex Layouts with Multiple Sidebars

When a flex row has two fixed-width sidebars plus a flexible center, all fixed-width children need `shrink-0` or the browser may compress them. The center column needs `min-w-0` to allow it to shrink below its content size. Avoid `overflow-hidden` on the outer container as it breaks inner scroll areas — instead constrain each child properly.

### Long URLs Break Sidebar Layouts

URLs in sidebar cards will expand the card beyond its parent width. Use `overflow-hidden` on the card, `break-all` on URL text, and `truncate` where single-line display is acceptable.

### useCallback Stale Closure Pitfall

Chaining `useCallback` hooks (e.g., `handleKeyDown` depends on `handleSubmit` which depends on `content`) can create stale closures where the inner callback captures an outdated state value. Using a ref (`contentRef.current = content`) avoids the dependency chain entirely.

---

## Session: UX Redesign — Panel System & Responsive Layout

### CSS Transitions Require Persistent DOM Elements

For CSS transitions on panels (slide in/out), the element must always be in the DOM — just transformed off-screen. Conditionally rendering with `{isOpen && <Panel />}` means mount/unmount with no transition. Instead, always render the panel and toggle `translate-x-0` vs `translate-x-full` (or `-translate-x-[292px]` for left panels). Same applies to the scrim overlay — always render it with `opacity-0 pointer-events-none` when inactive.

### Overlay Panels Need `overflow-hidden` on Container

When sliding panels are positioned absolute and translated off-screen, they can still cause horizontal scrollbars on the parent. Add `overflow-hidden` to the containing flex layout.

### `next-themes` Setup in Tailwind v4

`next-themes` works with Tailwind v4's `@custom-variant dark` when configured with `attribute="class"`. The CSS custom properties in `:root` and `.dark` selector work as-is. The `enableSystem` prop enables `prefers-color-scheme` detection. The package was already installed but just needed the `<ThemeProvider>` wrapper in App.tsx.

### Panel State Management Pattern

A dedicated `usePanelState` hook centralising left/right panel states, keyboard shortcuts, and breakpoint-aware constraints keeps the ChatLayout clean. The hook enforces rules like "no pinning on tablet" and "force-close panels on mobile" via effects reacting to breakpoint changes.

---

## Session: Module 8 — Sub-Agent (Deep Analysis)

### Sub-Agents as Just Another Tool

The simplest sub-agent architecture is "just another tool" in the existing tool-calling loop. The main LLM decides when to delegate (same as picking `web_search` vs `retrieve_documents`), and the sub-agent runs its own internal tool loop with a restricted tool set. No orchestration framework, no delegation policy engine — the LLM's judgment is the policy.

### Status Callbacks via List Collection

When a sub-agent runs inside `_execute_tool` (which is `await`ed sequentially), status updates can't be yielded directly from the generator. Instead, use a list that the sub-agent's `on_status` callback appends to, then yield all collected events after `_execute_tool` returns. This avoids asyncio.Queue complexity while keeping the streaming interface (`str | ToolEvent`) clean.

### Allowlist Filtering for Sub-Agent Tool Calls

The sub-agent's text tool call parser filters against an explicit allowlist (`retrieve_documents`, `query_documents_metadata`). This prevents the local LLM from attempting to call `web_search` or `deep_analysis` itself (which would cause recursion or unauthorized API calls). The native tool call path also checks the allowlist before execution.

---

## Session: Module 11 — RAG-Fusion

### RAG-Fusion as a Thin Query-Side Wrapper

**RAG-Fusion requires no DB changes** — the existing `reciprocal_rank_fusion()` already accepts N lists. The entire feature is a query-side wrapper: generate sub-queries → run retrieval per query in parallel → merge all result lists via RRF. The retrieval pipeline, reranker, and DB are completely unchanged.

### Async Closure Pattern for Per-Query Dispatch

Extracting a `_retrieve_one(q)` inner async closure lets you dispatch multiple queries cleanly with `asyncio.gather(*[_retrieve_one(q) for q in all_queries])`. The closure captures `mode`, `user_token`, `candidates`, etc. from the outer scope — no need to thread them through a helper function signature.

### Zero-Overhead Feature Flags

When a feature is off (`rag_fusion_enabled=False`), `all_queries = [query]`, `asyncio.gather` runs exactly one coroutine, `len(per_query_results) == 1` skips the extra RRF call. Truly zero overhead on the disabled path — just a list of length 1.

---

## Session: File Metadata Editing

### Align Hook Return Types With Prop Types

**When a hook function returns `Promise<T>`, prop interfaces must accept `Promise<T>`, not `Promise<void>`.**

`updateDocument` returns `Promise<Document>` (the updated record). The `DocumentsPanel` `onUpdate` prop was initially typed as `Promise<void>`, causing a TypeScript error. The fix is to use the exact return type from the hook throughout — prop type, modal `onSave` type, and any wrappers. Widening to `Promise<void>` is tempting but incorrect since callers may need the returned value.

### `/next` Command Workflow

The `/next` → plan → compact → `/build` loop works well for self-contained features. Reading `PROGRESS.md` to identify the next unchecked item and asking targeted questions before planning keeps context focused and avoids building the wrong thing.

---

## Session: Module 14 — GraphRAG

### ToolContext Needs user_id, Not Just user_token

GraphRAG RPCs use `SECURITY DEFINER` and require an explicit `p_user_id` parameter. The Supabase client obtained via `get_supabase_client(user_token)` only sets postgrest auth — `sb.auth.get_user()` does **not** work on this client. Always pass `user_id` explicitly from the `get_current_user` dependency down through `ToolContext` (add a `user_id: str = ""` field) and into any service that needs it for RPC calls.

### Communities are Derived Data — Delete and Reinsert

Community detection output is fully derived from entities+relationships. Rather than trying to upsert or diff communities, the cleanest approach is `DELETE WHERE user_id = ...` then bulk INSERT after each rebuild. This avoids stale community rows and merge conflicts.

### NetworkX `greedy_modularity_communities` Works on Small Graphs

For typical document collections, `greedy_modularity_communities(G, weight="weight")` from `networkx.algorithms.community` produces meaningful clusters without tuning. Filter results by `min_size` to avoid noise from singleton or pair communities. Import NetworkX lazily inside functions (not at module top level) to keep startup fast.

### Entity-Neighbour Expansion is Purely Additive

Graph expansion appends extra chunks to existing retrieval results rather than replacing them. This means the core relevance ranking is unchanged — expansion only enriches context. Guard with `if user_id` since the service role ingestion path has no user context.

### Test File Placement for Playwright File Upload

Playwright's `browser_file_upload` enforces allowed roots (the project directory). Create test files under the project root rather than `/tmp/` to avoid `File access denied` errors.

### Duplicating Tool Call Parsing is Acceptable

The sub-agent duplicates `_parse_text_tool_calls` from `llm.py` rather than sharing it. The sub-agent version adds allowlist filtering and operates in a different context (isolated tool loop vs main chat loop). Extracting a shared utility would couple the two modules and add complexity for minimal DRY benefit — especially since the parsing logic is ~15 lines.

---

## Session: Chat History Delete Button (Firefox Debugging)

### Tailwind v4 + oklch Colors Are Invisible if CSS Variable Chain Fails

**Never use Tailwind CSS variable-based color utilities (`text-muted-foreground`, `text-foreground/50`, `text-slate-400`) for small decorative elements that must be visible in all browsers.**

In Tailwind v4 with shadcn/ui, all semantic colors (`muted-foreground`, `slate-400`, etc.) resolve through a chain of CSS custom properties that ultimately produce `oklch(...)` values. If the variable chain fails (misconfigured theme, browser quirk, or unsupported CSS feature), the computed color is transparent/invalid — making SVG icons with `stroke: currentColor` completely invisible. The element remains in the DOM and takes up space, making layout-based debugging misleading.

**Fix:** Use an explicit hex color via `style={{ color: '#94a3b8' }}` for decorative icons that must be guaranteed visible. Hex values bypass the CSS variable chain entirely.

### CSS Grid is More Reliable than Flexbox for Truncated-Text + Fixed-Button Rows

**For a "title (truncated) + action button" row layout, use `grid-cols-[1fr_auto]` instead of flex.**

The flex approach (`flex-1 truncate` on the span + `shrink-0` on the button) requires `min-w-0` on both the flex container and the child span to work across all browsers. Firefox's flex algorithm handles `min-width: auto` differently from Chromium, meaning the span won't truncate and the button gets pushed off-screen. CSS grid with `grid-template-columns: 1fr auto` is semantically clearer and works consistently across all browsers — the first column gets all available space and truncation "just works".

### Debug Invisible Elements by Checking Computed Color, Not Just Layout

**When an element seems missing, check `window.getComputedStyle(el).color` before investigating layout.**

The delete button was confirmed in the DOM via accessibility snapshot (`button "Delete chat"` was present), had correct dimensions (20×20px), and was within the panel bounds — yet was invisible. Checking computed color revealed an `oklch()` value that rendered as transparent in Firefox. The debugging path should be: DOM presence → computed styles (color, opacity, visibility) → layout/overflow.

### Multiple Vite Dev Servers Accumulate Across Sessions

Running `npm run dev` multiple times without stopping previous instances creates zombie Vite processes, each claiming incrementing ports (5173, 5174, …5184+). All instances watch the same source files and pick up changes, but the proliferation wastes memory. Clean up with `pkill -f vite` before starting a new dev session.

---

## Session: Ingestion Pipeline Optimisation + Tool Registry

### Qwen3-Thinking Emits `<think>` Blocks Before Structured Output

**Qwen3 (and similar reasoning models) wrap chain-of-thought in `<think>...</think>` before producing their actual output.** This breaks any code that calls `json.loads()` directly on the response — the parser sees `<think>` and immediately fails with `Expecting value: line 1 column 1`.

**Fix:** Strip thinking blocks before parsing with `re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()`. Also send `/no_think` as a system message (Qwen3-specific directive) to suppress CoT entirely for structured output tasks where reasoning is not needed.

### Local LLMs Use Multiple Text-Format Tool Call Syntaxes

**The OpenAI `tool_calls` API field is not the only way local LLMs signal tool use.** Three formats are common:
1. `<function=name><parameter=k>v</parameter></function>` — hermes/chatml style
2. `<tool_call>{"name": "...", "arguments": {...}}</tool_call>` — Qwen3 native
3. `[{"name": "...", "arguments": {...}}]` — bare JSON array

A parser that handles only one format will silently fail for models using another, causing the model's response to render as raw text in the chat. Always implement all three formats and guard Format 3 against false positives (any JSON object with a `"name"` key) by checking against the set of registered tool names.

### Replace LLM Calls With Python Libraries Where Intelligence Is Not Required

**Metadata extraction (title, summary, topics, date) does not require an LLM.** Using an LLM for these tasks made ingestion slow (multiple round-trips to an 80B model) and fragile (thinking tokens, JSON parse failures). Python replacements:

- **Title:** First `#` heading → first non-blank line → filename stem (pure string ops)
- **Topics:** [YAKE](https://github.com/LIAAD/yake) — pure Python, no model download, top-5 keyphrases in milliseconds
- **Date:** Regex matching ISO / month-name / DD-MM-YYYY formats
- **Summary:** First 2–3 sentences ≥20 chars that aren't headings

Reserve LLM calls for tasks requiring genuine reasoning.

### Decouple Long-Running Background Work From Document Readiness

**Fire-and-forget `asyncio.create_task()` is the right pattern for work that enriches a document after it's already usable.** GraphRAG extraction (35+ LLM calls for a 175-chunk document) was blocking the document from becoming `ready` for minutes. The fix: mark the document `ready` immediately after embedding is done, then launch GraphRAG as a background task with `asyncio.create_task(_run_graphrag(...))`. The document is searchable instantly; the knowledge graph appears later.

### File-Based Autodiscovery for Plugin Registries

**For extensible plugin systems, glob-based autodiscovery is simpler and more maintainable than explicit registration.** The pattern:
1. Each plugin is a `.py` file in a designated directory exposing a module-level `plugin` variable
2. `_registry.py` globs `*.py`, skips `_*.py`, imports each, and collects `plugin` instances
3. Startup logs `"Loaded tool: <name>"` or `"Failed to load: ..."` for immediate visibility

Circular import risk: shared types (`ToolContext`, `ToolEvent`) must live in the registry module (not in the module that imports from it), so tool files can import types without back-importing the consuming service.

### `ToolContext` Must Be Passed In Full — Never Reconstruct Partial Copies

**When a function needs to evaluate tool availability, pass the full `ToolContext` rather than extracting individual fields.** `get_tools(has_documents: bool)` constructed a partial `ToolContext(has_documents=has_documents)`, silently discarding `user_id` and `user_token`. Any future `enabled` lambda checking user-specific state would have silently misbehaved. The fix: `get_tools(ctx: ToolContext)` — accept and forward the full context.
