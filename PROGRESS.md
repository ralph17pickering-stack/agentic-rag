# Progress

Track your progress through the masterclass. Update this file as you complete modules - Claude Code reads this to understand where you are in the project.

## Convention
- `[ ]` = Not started
- `[-]` = In progress
- `[x]` = Completed

## Modules

### Module 1: App Shell + Observability
- [x] Backend scaffolding (Python + FastAPI + venv)
- [x] Frontend scaffolding (Vite + React + Tailwind + shadcn/ui)
- [x] Root config files (.gitignore, .env.example)
- [x] Database migration (threads + messages tables with RLS)
- [x] Backend: config, JWT auth, Supabase client, thread CRUD, chat SSE endpoint, LLM service
- [x] Frontend: auth (login/signup), chat layout, thread sidebar, message area, SSE streaming
- [x] LangSmith observability (wrap_openai + @traceable)
- [x] **Manual step: Create Supabase project, run migration, populate .env files**

### Module 2: BYO Retrieval + Memory
- [x] Database schema: documents + chunks tables, pgvector extension, HNSW index, RLS, Realtime
- [x] match_chunks RPC function (similarity search with RLS)
- [x] Backend config: embedding_model, embedding_dim, chunk_size, chunk_overlap
- [x] Dependencies: python-multipart, tiktoken
- [x] Service role Supabase client (bypasses RLS for background ingestion)
- [x] Embedding service (batch + single, @traceable)
- [x] Chunker service (tiktoken cl100k_base, fixed-size with overlap)
- [x] Document models (Pydantic)
- [x] Ingestion pipeline (download → chunk → embed → store, background async)
- [x] Documents API (GET/POST/DELETE /api/documents)
- [x] Storage bucket auto-creation on startup
- [x] Retrieval service (query embedding → match_chunks RPC)
- [x] Tool-calling chat refactor (retrieve_documents tool definition + flow)
- [x] Frontend: Documents UI (upload, list, delete, status badges)
- [x] Frontend: Realtime status updates via Supabase
- [x] Frontend: Chat/Documents nav toggle
- [x] Integration testing + polish

### Module 3: Record Manager
- [ ] Not started

### Module 4: Metadata Extraction
- [ ] Not started

### Module 5: Multi-Format Support
- [ ] Not started

### Module 6: Hybrid Search & Reranking
- [ ] Not started

### Module 7: Additional Tools
- [ ] Not started

### Module 8: Sub-Agents
- [ ] Not started
