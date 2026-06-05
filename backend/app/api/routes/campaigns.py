"""Campaign CRUD-style routes used by the dashboard."""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import settings
from app.models.campaign import Campaign
from app.schemas.campaign import CampaignCreate, CampaignOut
from app.services.gemini_script import fallback_script, generate_script_with_gemini
from app.services.make_com import fire_make_com_webhook
from app.services.pexels_lookup import search_vertical_clip
from app.workers.render_worker import render_campaign_background

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_mock_payload(campaign: Campaign) -> dict:
    """Build a topic-specific script + real Pexels clip URLs.

    Tries Gemini first for a real LLM-generated script. Falls back to a
    simple keyword extractor if Gemini is unavailable. Either way, the
    search_terms used to query Pexels are derived from the topic — so
    "Gemini model" no longer produces a "nature" scene.
    """
    # 1. Generate the script (Gemini preferred, keyword-fallback otherwise)
    script = generate_script_with_gemini(
        topic=campaign.topic,
        scene_count=campaign.scene_count,
        voice=campaign.voice,
    )
    if script is None:
        logger.info(
            "Falling back to keyword-extractor script for topic %r",
            campaign.topic,
        )
        script = fallback_script(campaign.topic, campaign.scene_count)

    # 2. Query Pexels for each scene's search_term
    scenes = script.get("scenes", [])
    for scene in scenes:
        url = search_vertical_clip(scene.get("search_term", ""))
        scene["video_url"] = url

    # Fill in fields the schema expects
    return {
        "title": script.get("title", f"Reel: {campaign.topic}"),
        "voiceover_full": script.get(
            "voiceover_full", " ... ".join(s.get("narration", "") for s in scenes)
        ),
        "scenes": scenes,
    }


@router.post(
    "/campaigns",
    response_model=CampaignOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_campaign(
    payload: CampaignCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Campaign:
    """Create a campaign, fire the Make.com webhook, return 202 immediately.

    Critical contract: this endpoint must return within milliseconds.
    No long-running work happens on this thread. The actual script generation,
    asset lookup, and rendering all happen out-of-band.

    If MOCK_MODE=true in .env, the Make.com webhook is skipped and the
    backend calls Gemini directly (or the keyword fallback) to produce a
    topic-specific script, then kicks off the local render worker.
    """
    campaign = Campaign(
        topic=payload.topic,
        voice=payload.voice,
        scene_count=payload.scene_count,
        aspect_ratio=payload.aspect_ratio,
        status="pending",
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    # MOCK MODE: simulate the Make.com callback inline with topic-specific data
    if settings.mock_mode:
        logger.info(
            "MOCK_MODE active — generating topic-specific script for %s",
            campaign.id,
        )
        campaign.status = "processing"
        db.commit()
        db.refresh(campaign)

        mock = _build_mock_payload(campaign)
        campaign.title = mock["title"]
        campaign.voiceover_full = mock["voiceover_full"]
        campaign.scenes_with_assets = mock["scenes"]
        campaign.status = "ready_to_render"
        db.commit()
        db.refresh(campaign)
        background_tasks.add_task(render_campaign_background, str(campaign.id))
        return campaign

    # REAL MODE: fire Make.com. If the webhook fire itself fails, we don't
    # want to fail the request — the campaign row exists and an admin can
    # retry. But we do log loudly.
    campaign.status = "processing"
    db.commit()
    db.refresh(campaign)

    try:
        fire_make_com_webhook(campaign)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to fire Make.com webhook for campaign %s: %s",
            campaign.id,
            exc,
        )

    return campaign


@router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db)) -> list[Campaign]:
    """List recent campaigns, newest first. Used by the dashboard."""
    return (
        db.query(Campaign)
        .order_by(Campaign.created_at.desc())
        .limit(100)
        .all()
    )


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: UUID, db: Session = Depends(get_db)) -> Campaign:
    """Get a single campaign. The frontend polls this every ~3s."""
    # NB: compare against str(campaign_id) because the column is String(36).
    # SQLAlchemy on a UUID literal would use `.hex` (32 chars) which doesn't
    # match the 36-char stored value.
    campaign = db.query(Campaign).filter(Campaign.id == str(campaign_id)).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign
