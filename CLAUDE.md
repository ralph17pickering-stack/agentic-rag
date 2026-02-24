# CLAUDE.md

RAG app with chat (default) and document ingestion interfaces. Config via env vars, no admin UI.

## Stack
- Frontend: React + Vite + Tailwind + shadcn/ui
- Backend: Python + FastAPI
- Database: Supabase (Postgres, pgvector, Auth, Storage, Realtime)
- LLM: OpenAI (Module 1), OpenRouter (Module 2+)
- Observability: LangSmith

## Rules
- Python backend must use a `venv` virtual environment
- No LangChain, no LangGraph - raw SDK calls only
- Use Pydantic for structured LLM outputs
- All tables need Row-Level Security - users only see their own data unless sharing is enabled
- Stream chat responses via SSE
- Use Supabase Realtime for ingestion status updates
- Module 2+ uses stateless completions - store and send chat history yourself

## Planning
- Save all plans to `.agent/plans/` folder
- Naming convention: `{sequence}.{plan-name}.md` (e.g., `1.auth-setup.md`, `2.document-ingestion.md`)
- Plans should be detailed enough to execute without ambiguity
- Each task in the plan must include at least one validation test to verify it works
- Assess complexity and single-pass feasibility - can an agent realistically complete this in one go?
- Include a complexity indicator at the top of each plan:
  - ✅ **Simple** - Single-pass executable, low risk
  - ⚠️ **Medium** - May need iteration, some complexity
  - 🔴 **Complex** - Break into sub-plans before executing

## Development Flow
1. **Plan** - Create a detailed plan and save it to `.agent/plans/`
2. **Build** - Execute the plan to implement the feature
3. **Validate** - Test and verify the implementation works correctly. Use browser testing where applicable via an appropriate MCP
4. **Iterate** - Fix any issues found during validation

## Browser Testing — Slow Processing Steps

When a browser test triggers an action that involves background processing (LLM calls, ingestion pipelines, embedding, etc.), **do not poll the page in a loop**. Instead, after triggering the action, use `AskUserQuestion` with these options:

- **Check now** — proceed to inspect the page/API for the expected result
- **Skip this check** — accept code-review as sufficient verification and move on
- **Troubleshoot** — investigate why the page hasn't updated (check backend logs, API status, etc.)

This prevents burning tokens on repeated `browser_wait_for` / `browser_snapshot` calls while waiting for a slow local LLM or ingestion pipeline.

## Applying Database Migrations

`psql` is not in PATH. Apply migrations via the pg-meta HTTP API:

```bash
curl -s "http://127.0.0.1:8000/pg/query" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"$(cat /home/ralph/rag/db/migrations/<filename>.sql | tr '\n' ' ' | sed 's/"/\\"/g')\"}"
```

Or for multi-statement migrations, POST each statement separately, or paste directly into Supabase Studio at **http://localhost:54323** → SQL Editor.

To verify a migration worked, query the schema:
```bash
curl -s "http://127.0.0.1:8000/pg/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '\''<table>'\'' AND column_name = '\''<column>'\''"}' | python3 -m json.tool
```

Note: `db/` is in `.gitignore` — use `git add -f db/migrations/<file>.sql` to track migration files.

## Test Credentials
- Email: `test@agentic-rag.dev`
- Password: `TestPass123!`

## Progress
Check PROGRESS.md for current module status. Update it as you complete tasks.
Check and update LESSONS.md to take into account important takeaways from each session so that you can learn from what works and what doesn't.