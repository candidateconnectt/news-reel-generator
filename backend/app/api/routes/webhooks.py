"""Make.com → FastAPI callback endpoints (HMAC-protected)."""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import verify_webhook_secret
from app.models.campaign import Campaign
from app.schemas.campaign import CampaignFailCallback, CampaignScriptCallback
from app.workers.render_worker import render_campaign_background

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/campaigns/{campaign_id}/script")
async def receive_script_callback(
    campaign_id: UUID,
    payload: CampaignScriptCallback,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Make.com calls this once it has the script + Pexels clip URLs.

    Persists everything to the campaign row, flips status to ready_to_render,
    and kicks off the local render worker. Returns 200 fast so Make.com's webhook
    doesn't time out — heavy work runs in the background.
    """
    await verify_webhook_secret(request)

    campaign = db.query(Campaign).filter(Campaign.id == str(campaign_id)).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.title = payload.title
    campaign.voiceover_full = payload.voiceover_full
    campaign.script_json = {
        "title": payload.title,
        "voiceover_full": payload.voiceover_full,
        "scenes": payload.scenes,
    }
    campaign.scenes_with_assets = payload.scenes
    campaign.status = "ready_to_render"
    db.commit()
    db.refresh(campaign)

    # Fire-and-forget the local render. BackgroundTasks runs after the response
    # is sent, so Make.com gets a 200 quickly.
    background_tasks.add_task(render_campaign_background, str(campaign.id))

    logger.info("Campaign %s ready to render", campaign_id)
    return {"status": "received", "campaign_id": str(campaign_id)}


@router.post("/campaigns/{campaign_id}/fail")
async def receive_fail_callback(
    campaign_id: UUID,
    payload: CampaignFailCallback,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Make.com calls this on any module error. Marks the campaign failed."""
    await verify_webhook_secret(request)

    campaign = db.query(Campaign).filter(Campaign.id == str(campaign_id)).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.status = "failed"
    campaign.error_message = f"[{payload.module or 'unknown'}] {payload.reason}"
    db.commit()

    logger.warning("Campaign %s failed: %s", campaign_id, campaign.error_message)
    return {"status": "acknowledged"}
