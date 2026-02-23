import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.routers import threads, chat, documents
from app.services.supabase import get_service_supabase_client
from app.services.topic_consolidator import consolidate_all_users
from app.services.community_builder import build_communities_for_all_users
from app.services.tag_quality_sweep import sweep_random_user
from app.services.activity import record_activity
from app.services.tag_enrichment_sweep import run_enrichment_sweep
from app.config import settings

logger = logging.getLogger(__name__)


class ActivityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        record_activity()
        return await call_next(request)


async def _community_rebuild_loop():
    """Periodic community rebuild — runs every 24 hours."""
    while True:
        await asyncio.sleep(86400)
        logger.info("Running periodic community rebuild")
        try:
            await build_communities_for_all_users()
        except Exception:
            logger.exception("Community rebuild loop error")


async def _topic_consolidation_loop():
    interval = settings.topic_consolidation_interval_hours * 3600
    while True:
        await asyncio.sleep(interval)
        logger.info("Running periodic topic consolidation")
        try:
            await consolidate_all_users()
        except Exception:
            logger.exception("Topic consolidation loop error")


async def _tag_quality_sweep_loop():
    interval = settings.tag_quality_sweep_interval_hours * 3600
    while True:
        await asyncio.sleep(interval)
        logger.info("Running periodic tag quality sweep")
        try:
            await sweep_random_user()
        except Exception:
            logger.exception("Tag quality sweep loop error")


async def _tag_enrichment_sweep_loop():
    interval = settings.tag_enrichment_sweep_interval_minutes * 60
    while True:
        await asyncio.sleep(interval)
        logger.info("Running periodic tag enrichment sweep")
        try:
            await run_enrichment_sweep()
        except Exception:
            logger.exception("Tag enrichment sweep loop error")


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

    if settings.topic_consolidation_enabled:
        asyncio.create_task(_topic_consolidation_loop())

    if settings.graphrag_community_rebuild_enabled:
        asyncio.create_task(_community_rebuild_loop())

    if settings.tag_quality_sweep_enabled:
        asyncio.create_task(_tag_quality_sweep_loop())

    if settings.tag_enrichment_sweep_enabled:
        asyncio.create_task(_tag_enrichment_sweep_loop())

    yield


app = FastAPI(title="Agentic RAG", lifespan=lifespan)

app.add_middleware(ActivityMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
