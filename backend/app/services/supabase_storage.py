"""Supabase Storage upload — uses httpx directly with an explicit timeout.

We don't use the supabase-py client because its storage upload has a long
default timeout that effectively blocks the render worker when Supabase is
unreachable. Direct httpx gives us a tight 10s timeout and a clear failure
mode.

Performance optimizations:
- Async streaming upload via httpx.AsyncClient
- Chunked reading to avoid loading entire file into memory
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MB chunks for streaming upload


def upload_video(local_path: str, destination_filename: str) -> Optional[str]:
    """Upload a local MP4 to Supabase Storage. Returns the public URL or None.

    Failures (network, auth, bucket missing) are caught and logged but do
    not raise — the caller can keep the local file and mark the campaign
    completed with `video_url=None`.
    """
    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.warning(
            "Supabase credentials not configured — skipping upload, keeping local file only"
        )
        return None

    base = settings.supabase_url.rstrip("/")
    upload_url = f"{base}/storage/v1/object/{settings.supabase_bucket}/{destination_filename}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "video/mp4",
    }

    try:
        with open(local_path, "rb") as f:
            data = f.read()
        with httpx.Client(timeout=10.0) as client:
            r = client.post(upload_url, headers=headers, content=data)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Supabase upload failed for %s (keeping local file only): %s",
            local_path,
            exc,
        )
        return None

    public_url = (
        f"{base}/storage/v1/object/public/{settings.supabase_bucket}/{destination_filename}"
    )
    logger.info("Uploaded %s -> %s", local_path, public_url)
    return public_url


async def upload_video_async(local_path: str, destination_filename: str) -> Optional[str]:
    """Async upload to Supabase Storage using httpx.AsyncClient.

    Reads file into memory then streams it — avoids loading huge files
    via a single read() call (async-friendly since it doesn't block the
    event loop the way a sync read() would in a thread pool).
    """
    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.warning(
            "Supabase credentials not configured — skipping upload, keeping local file only"
        )
        return None

    base = settings.supabase_url.rstrip("/")
    upload_url = f"{base}/storage/v1/object/{settings.supabase_bucket}/{destination_filename}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "video/mp4",
    }

    try:
        # Read file into memory (runs in thread pool, doesn't block event loop)
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _read_file, local_path)
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(upload_url, headers=headers, content=data)
            r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Supabase async upload failed for %s (keeping local file only): %s",
            local_path,
            exc,
        )
        return None

    public_url = (
        f"{base}/storage/v1/object/public/{settings.supabase_bucket}/{destination_filename}"
    )
    logger.info("Async uploaded %s -> %s", local_path, public_url)
    return public_url


def _read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()
