"""Make.com webhook fire — called synchronously from POST /campaigns.

We block for at most a few seconds waiting for Make.com to acknowledge the
webhook. Make.com returns 200 fast (it's just a trigger acknowledgment);
all the real work happens in the scenario, asynchronously.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.models.campaign import Campaign

logger = logging.getLogger(__name__)


def fire_make_com_webhook(campaign: Campaign) -> None:
    """Fire the Make.com scenario webhook with the campaign payload."""
    if not settings.make_com_webhook_url:
        logger.warning(
            "MAKE_COM_WEBHOOK_URL not configured — skipping webhook fire for %s. "
            "Set it in backend/.env once you've built the Make.com scenario.",
            campaign.id,
        )
        return

    payload = {
        "campaign_id": str(campaign.id),
        "topic": campaign.topic,
        "voice": campaign.voice,
        "scene_count": campaign.scene_count,
        "aspect_ratio": campaign.aspect_ratio,
    }

    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.post(settings.make_com_webhook_url, json=payload)
        logger.info(
            "Make.com webhook fired for %s: HTTP %s",
            campaign.id,
            r.status_code,
        )
    except httpx.HTTPError as exc:
        logger.error("Make.com webhook failed for %s: %s", campaign.id, exc)
        raise
