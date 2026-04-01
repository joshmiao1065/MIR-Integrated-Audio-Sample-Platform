#!/usr/bin/env python3
"""
Prune unprocessed samples to bring Supabase Storage under a target size.

Strategy:
  - KEEP all samples that already have audio_embeddings (processed)
  - KEEP up to --keep-pending of the oldest pending samples (by created_at)
  - DELETE everything else from Supabase Storage + DB (cascades handle children)

Usage (from audio-sample-manager/):
    # Dry run — shows what would be deleted
    python -m scripts.prune_storage

    # Actually delete
    python -m scripts.prune_storage --execute

    # Custom keep count
    python -m scripts.prune_storage --keep-pending 300 --execute
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from supabase import create_client
from sqlalchemy import text

from app.config import settings
from app.database import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Storage base URL prefix to strip when building storage paths for deletion.
# Format: https://<project>.supabase.co/storage/v1/object/public/<bucket>/
STORAGE_PREFIX_TEMPLATE = "{supabase_url}/storage/v1/object/public/{bucket}/"

BATCH_SIZE = 100  # Supabase Storage remove() batch size


async def run(keep_pending: int, execute: bool) -> None:
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    bucket = settings.SUPABASE_STORAGE_BUCKET
    storage_prefix = STORAGE_PREFIX_TEMPLATE.format(
        supabase_url=settings.SUPABASE_URL, bucket=bucket
    )

    async with AsyncSessionLocal() as db:
        # ── 1. Collect IDs to KEEP ────────────────────────────────────────────

        # All processed samples (have embeddings)
        result = await db.execute(text("SELECT sample_id FROM audio_embeddings"))
        processed_ids = {str(row[0]) for row in result.all()}
        log.info("Processed samples (keep): %d", len(processed_ids))

        # Oldest N pending samples (by created_at)
        result = await db.execute(
            text("""
                SELECT s.id FROM samples s
                LEFT JOIN audio_embeddings ae ON ae.sample_id = s.id
                WHERE ae.sample_id IS NULL
                ORDER BY s.created_at ASC
                LIMIT :n
            """),
            {"n": keep_pending},
        )
        keep_pending_ids = {str(row[0]) for row in result.all()}
        log.info("Pending samples to keep:  %d", len(keep_pending_ids))

        keep_ids = processed_ids | keep_pending_ids
        log.info("Total samples to keep:    %d", len(keep_ids))

        # ── 2. Collect rows to DELETE ─────────────────────────────────────────
        result = await db.execute(
            text("""
                SELECT id::text, file_url FROM samples
                WHERE id::text != ALL(:keep)
            """),
            {"keep": list(keep_ids)},
        )
        rows_to_delete = result.all()
        log.info("Samples to delete:        %d", len(rows_to_delete))

        if not rows_to_delete:
            log.info("Nothing to delete.")
            return

        # Estimate storage freed (avg 669 KB/file based on 4000 samples = 2.676 GB)
        avg_kb = 669
        freed_mb = len(rows_to_delete) * avg_kb / 1024
        remaining_samples = len(keep_ids)
        remaining_mb = remaining_samples * avg_kb / 1024
        log.info(
            "Estimated freed:  %.0f MB  |  Remaining: %d samples ~%.0f MB",
            freed_mb, remaining_samples, remaining_mb,
        )

        if not execute:
            log.info("DRY RUN — pass --execute to perform deletion.")
            return

        # ── 3. Build storage paths ────────────────────────────────────────────
        storage_paths = []
        for _id, file_url in rows_to_delete:
            if file_url and file_url.startswith(storage_prefix):
                path = file_url[len(storage_prefix):]
                # Strip trailing '?' if present
                path = path.rstrip("?").rstrip("/")
                storage_paths.append(path)
            else:
                log.warning("Unexpected file_url format, skipping storage delete: %s", file_url)

        log.info("Deleting %d files from Supabase Storage in batches of %d…", len(storage_paths), BATCH_SIZE)
        for i in range(0, len(storage_paths), BATCH_SIZE):
            batch = storage_paths[i : i + BATCH_SIZE]
            try:
                supabase.storage.from_(bucket).remove(batch)
                log.info("  Deleted storage batch %d–%d", i + 1, i + len(batch))
            except Exception as exc:
                log.error("  Storage batch %d–%d failed: %s", i + 1, i + len(batch), exc)

        # ── 4. Delete from DB (cascades handle all child rows) ────────────────
        delete_ids = [str(row[0]) for row in rows_to_delete]
        log.info("Deleting %d rows from samples table…", len(delete_ids))

        # Delete in batches to avoid huge IN() clause
        for i in range(0, len(delete_ids), 500):
            batch = delete_ids[i : i + 500]
            await db.execute(
                text("DELETE FROM samples WHERE id::text = ANY(:ids)"),
                {"ids": batch},
            )
            await db.commit()
            log.info("  Deleted DB batch %d–%d", i + 1, i + len(batch))

        # ── 5. Clean orphaned tags ────────────────────────────────────────────
        log.info("Cleaning orphaned tags…")
        result = await db.execute(
            text("DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM sample_tags)")
        )
        await db.commit()
        log.info("Orphaned tags removed.")

        log.info("Done. Kept %d samples (~%.0f MB estimated).", remaining_samples, remaining_mb)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune unprocessed samples to save storage.")
    parser.add_argument(
        "--keep-pending",
        type=int,
        default=450,
        help="Number of oldest pending (unprocessed) samples to keep (default: 450)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform deletion (default is dry run)",
    )
    args = parser.parse_args()
    asyncio.run(run(keep_pending=args.keep_pending, execute=args.execute))


if __name__ == "__main__":
    main()
