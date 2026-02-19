#!/usr/bin/env python3
"""
Re-ingest documents stuck in 'pending' (or 'error') status.

Usage (from the app/backapp/frontend/ directory with venv active):

    # Dry run — list what would be processed
    python scripts/reingest_pending.py --dry-run

    # Re-ingest pending documents (default)
    python scripts/reingest_pending.py

    # Also retry documents that previously errored
    python scripts/reingest_pending.py --include-errors

    # Target a specific document by ID
    python scripts/reingest_pending.py --document-id <uuid>

    # Run up to N documents concurrently (default: 1 — LLM is the bottleneck)
    python scripts/reingest_pending.py --concurrency 2
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Allow imports from the app package when run from app/backapp/frontend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.supabase import get_service_supabase_client
from app.services.ingestion import ingest_document


def fetch_pending(include_errors: bool, document_id: str | None) -> list[dict]:
    sb = get_service_supabase_client()

    if document_id:
        result = sb.table("documents").select("id,user_id,storage_path,file_type,status,filename").eq("id", document_id).execute()
    else:
        statuses = ["pending", "error"] if include_errors else ["pending"]
        result = (
            sb.table("documents")
            .select("id,user_id,storage_path,file_type,status,filename")
            .in_("status", statuses)
            .order("created_at")
            .execute()
        )

    return result.data


async def reingest(docs: list[dict], concurrency: int, dry_run: bool) -> None:
    if not docs:
        print("No documents to process.")
        return

    print(f"{'DRY RUN — ' if dry_run else ''}Found {len(docs)} document(s) to process:\n")
    for doc in docs:
        print(f"  [{doc['status']:>8}]  {doc['filename'][:60]:<60}  {doc['id']}")

    if dry_run:
        return

    print()
    semaphore = asyncio.Semaphore(concurrency)
    completed = 0
    failed = 0

    async def _run(doc: dict) -> None:
        nonlocal completed, failed
        async with semaphore:
            print(f"→ Starting:  {doc['filename']} ({doc['id']})")
            try:
                await ingest_document(
                    document_id=doc["id"],
                    user_id=doc["user_id"],
                    storage_path=doc["storage_path"],
                    file_type=doc["file_type"],
                )
                completed += 1
                print(f"✓ Completed: {doc['filename']} ({doc['id']})")
            except Exception as exc:
                failed += 1
                print(f"✗ Failed:    {doc['filename']} ({doc['id']}): {exc}", file=sys.stderr)

    await asyncio.gather(*[_run(doc) for doc in docs])

    print(f"\nDone. {completed} succeeded, {failed} failed.")
    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-ingest pending/errored documents.")
    parser.add_argument("--include-errors", action="store_true", help="Also retry documents with status=error")
    parser.add_argument("--document-id", metavar="UUID", help="Target a single document by ID")
    parser.add_argument("--concurrency", type=int, default=1, metavar="N", help="Max parallel ingestions (default: 1)")
    parser.add_argument("--dry-run", action="store_true", help="List matching documents without processing them")
    args = parser.parse_args()

    docs = fetch_pending(include_errors=args.include_errors, document_id=args.document_id)
    asyncio.run(reingest(docs=docs, concurrency=args.concurrency, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
