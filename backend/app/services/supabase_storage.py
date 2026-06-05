"""Supabase Storage upload — uses httpx directly with an explicit timeout.

We don't use the supabase-py client because its storage upload has a long
default timeout that effectively blocks the render worker when Supabase is
unreachable. Direct httpx gives us a tight 10s timeout and a clear failure
mode.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


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
