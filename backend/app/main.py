import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import threads, chat, documents
from app.services.supabase import get_service_supabase_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create documents storage bucket if it doesn't exist
    try:
        sb = get_service_supabase_client()
        existing = sb.storage.list_buckets()
        bucket_names = [b.name for b in existing]
        if "documents" not in bucket_names:
            sb.storage.create_bucket("documents", options={"public": False})
            logger.info("Created 'documents' storage bucket")
    except Exception:
        logger.exception("Failed to ensure documents storage bucket")
    yield


app = FastAPI(title="Agentic RAG", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(threads.router)
app.include_router(chat.router)
app.include_router(documents.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
