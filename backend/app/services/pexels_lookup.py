"""Pexels API client — search for vertical stock video clips.

Used by:
- The Make.com scenario (Make.com calls Pexels directly via the HTTP module)
- The backend's mock mode (the backend queries Pexels itself for stubbed data)
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def search_vertical_clip(query: str, timeout: float = 10.0) -> str | None:
    """Search Pexels for a vertical (9:16) video clip matching `query`.

    Returns the best (largest vertical) video file URL, or None if nothing
    was found or the Pexels API key isn't configured.
    """
    if not settings.pexels_api_key:
        logger.warning("PEXELS_API_KEY not set — cannot query Pexels")
        return None

    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(
                "https://api.pexels.com/videos/search",
                params={
                    "query": query,
                    "orientation": "portrait",
                    "size": "medium",
                    "per_page": 5,
                },
                headers={
                    "Authorization": settings.pexels_api_key,
                    "User-Agent": "ReelBot/1.0",
                },
            )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Pexels search failed for '%s': %s", query, exc)
        return None

    data: dict[str, Any] = r.json()
    videos = data.get("videos", [])

    for video in videos:
        files = video.get("video_files", [])
        # Vertical means width < height; require at least 720p wide.
        vertical_files = [
            f for f in files
            if f.get("width", 0) < f.get("height", 0)
            and f.get("width", 0) >= 720
        ]
        if not vertical_files:
            continue
        # Pick the highest-resolution vertical file
        best = max(
            vertical_files,
            key=lambda f: f.get("width", 0) * f.get("height", 0),
        )
        return best.get("link")

    logger.warning("No vertical clips found for '%s'", query)
    return None
