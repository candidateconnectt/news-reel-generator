"""Campaign CRUD-style routes used by the dashboard."""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import settings
from app.models.campaign import Campaign
from app.schemas.campaign import (
    CampaignCreate,
    CampaignOut,
    ImageGenRequest,
    ImageGenResponse,
    ReelSceneImageRequest,
    ReelImageGenResponse,
)
from app.services.gemini_script import fallback_script, generate_script_with_gemini
from app.services.image_gen_service import BrandContext, GeneratedImage, ImageGenService, ReelScene
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
    try:
        campaign = Campaign(
            topic=payload.topic,
            voice=payload.voice,
            scene_count=payload.scene_count,
            aspect_ratio=payload.aspect_ratio,
            campaign_type=payload.campaign_type,
            brand_context=payload.brand_context,
            status="pending",
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
    except Exception as exc:
        logger.error("Campaign insert/refresh failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"DB error: {exc}") from exc

    # MOCK MODE: simulate the Make.com callback inline with topic-specific data
    if settings.mock_mode:
        logger.info(
            "MOCK_MODE active — generating topic-specific script for %s",
            campaign.id,
        )
        campaign.status = "processing"
        db.commit()

        try:
            mock = _build_mock_payload(campaign)
            campaign.title = mock["title"]
            campaign.voiceover_full = mock["voiceover_full"]
            campaign.scenes_with_assets = mock["scenes"]
        except Exception as exc:
            logger.error("Mock payload build failed: %s", exc)
            campaign.status = "pending_images"
            campaign.title = f"Reel: {campaign.topic}"
            campaign.voiceover_full = ""
            campaign.scenes_with_assets = []
            db.commit()
            return campaign

        if campaign.campaign_type == "reel_image":
            campaign.status = "pending_images"
            db.commit()
            logger.info("Campaign %s waiting for image generation", campaign.id)
        else:
            campaign.status = "ready_to_render"
            db.commit()
            background_tasks.add_task(render_campaign_background, str(campaign.id))
        return campaign

    # REAL MODE: fire Make.com. If the webhook fire itself fails, we don't
    # want to fail the request — the campaign row exists and an admin can
    # retry. But we do log loudly.
    campaign.status = "processing"
    db.commit()

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


# ---------------------------------------------------------------------------
# Image Generation
# ---------------------------------------------------------------------------

def _build_brand_context(raw: dict | None) -> BrandContext:
    """Convert a stored brand_context dict into a BrandContext dataclass."""
    if not raw:
        return BrandContext()
    return BrandContext(
        company_name=raw.get("company", ""),
        industry=raw.get("industry", ""),
        primary_color=raw.get("primaryColor", "#0057FF"),
        secondary_color=raw.get("secondaryColor", "#FFFFFF"),
        accent_color=raw.get("accentColor", "#FF6B35"),
        font_style=raw.get("fontStyle", "Inter"),
        tone=raw.get("tone", "Professional"),
        visual_style=raw.get("visualStyle", "Modern SaaS"),
        logo_url=raw.get("logo_url", ""),
    )


@router.post("/campaigns/{campaign_id}/generate-post-image", response_model=ImageGenResponse)
def generate_post_image(
    campaign_id: UUID,
    payload: ImageGenRequest,
    db: Session = Depends(get_db),
) -> ImageGenResponse:
    """Generate a single brand-consistent AI image for a social media post.

    The image inherits the campaign's brand context (colors, industry, tone,
    visual style). Returns the image URL and the provider's revised prompt.
    """
    campaign = db.query(Campaign).filter(Campaign.id == str(campaign_id)).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Merge brand contexts (request override takes precedence)
    brand_raw = payload.brand_context_override or campaign.brand_context or {}
    brand = _build_brand_context(brand_raw)

    svc = ImageGenService()
    try:
        result = asyncio.run(svc.generate_post(
            brand=brand,
            headline=payload.headline,
            supporting_text=payload.supporting_text,
            cta=payload.cta,
            design_direction=payload.design_direction,
            is_reel=False,
        ))
    except RuntimeError as exc:
        logger.error("Post image generation failed for campaign %s: %s", campaign_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not result.url:
        raise HTTPException(status_code=502, detail="Image generation returned empty URL")

    # Persist to campaign
    image_record = {
        "url": result.url,
        "revised_prompt": result.revised_prompt,
        "provider": result.provider,
        "scene_index": None,
        "type": "post",
        "headline": payload.headline,
    }
    existing = campaign.generated_images or []
    existing.append(image_record)
    campaign.generated_images = existing

    prompt_record = {
        "headline": payload.headline,
        "supporting_text": payload.supporting_text,
        "cta": payload.cta,
        "design_direction": payload.design_direction,
        "prompt": result.revised_prompt or "",
        "provider": result.provider,
        "type": "post",
    }
    prompts = campaign.image_prompts or []
    prompts.append(prompt_record)
    campaign.image_prompts = prompts

    db.commit()
    logger.info("Post image generated for campaign %s: %s", campaign_id, result.url[:60])

    return ImageGenResponse(
        url=result.url,
        revised_prompt=result.revised_prompt,
        provider=result.provider,
        scene_index=None,
    )


@router.post("/campaigns/{campaign_id}/generate-reel-scenes", response_model=ReelImageGenResponse)
def generate_reel_scenes(
    campaign_id: UUID,
    payload: ReelSceneImageRequest,
    db: Session = Depends(get_db),
) -> ReelImageGenResponse:
    """Generate a storyboard of brand-consistent AI images for a reel.

    ALL scenes share the same visual world (brand colors, lighting, mood).
    Each scene gets its own image prompt derived from its narration.

    Request body: {scenes: [{scene_index: int, narration: str}, ...]}
    """
    campaign = db.query(Campaign).filter(Campaign.id == str(campaign_id)).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    brand_raw = payload.brand_context_override or campaign.brand_context or {}
    brand = _build_brand_context(brand_raw)

    # Build ReelScene objects sorted by scene_index
    scenes = [ReelScene(scene_number=s["scene_index"], narration=s["narration"]) for s in payload.scenes]
    scenes.sort(key=lambda s: s.scene_number)

    svc = ImageGenService()
    try:
        results = asyncio.run(svc.generate_reel_scenes(
            brand=brand,
            hook=campaign.title or campaign.topic,
            body="",
            cta="",
            scenes=scenes,
        ))
    except RuntimeError as exc:
        logger.error("Reel scene generation failed for campaign %s: %s", campaign_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    successful = [r for r in results if r.url]
    if not successful:
        raise HTTPException(status_code=502, detail="All image generation requests returned empty URLs")

    # Persist results
    image_records = []
    prompt_records = []
    for scene_req, result in zip(payload.scenes, results):
        image_records.append({
            "url": result.url,
            "revised_prompt": result.revised_prompt,
            "provider": result.provider,
            "scene_index": scene_req["scene_index"],
            "type": "reel",
            "narration": scene_req["narration"],
        })
        prompt_records.append({
            "scene_index": scene_req["scene_index"],
            "narration": scene_req["narration"],
            "prompt": result.revised_prompt or "",
            "provider": result.provider,
            "type": "reel",
        })

    existing_images = campaign.generated_images or []
    existing_images.extend(image_records)
    campaign.generated_images = existing_images

    existing_prompts = campaign.image_prompts or []
    existing_prompts.extend(prompt_records)
    campaign.image_prompts = existing_prompts

    db.commit()
    logger.info("Reel scenes generated for campaign %s: %d images", campaign_id, len(results))

    return ReelImageGenResponse(
        scenes=[
            ImageGenResponse(
                url=r.url,
                revised_prompt=r.revised_prompt,
                provider=r.provider,
                scene_index=scene_req["scene_index"],
            )
            for scene_req, r in zip(payload.scenes, results)
        ],
        provider="minimax",  # svc.provider.value would need refactor
        total=len(results),
    )


@router.get("/campaigns/{campaign_id}/images")
def get_campaign_images(campaign_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Return all AI-generated images and their prompts for a campaign."""
    campaign = db.query(Campaign).filter(Campaign.id == str(campaign_id)).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {
        "images": campaign.generated_images or [],
        "prompts": campaign.image_prompts or [],
    }


@router.post("/campaigns/{campaign_id}/render")
def trigger_render(
    campaign_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Manually trigger the render worker for a campaign.

    Use this after calling /generate-reel-scenes on image-based campaigns
    to start the Ken Burns video render.
    """
    campaign = db.query(Campaign).filter(Campaign.id == str(campaign_id)).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status not in ("pending_images", "ready_to_render"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot render campaign in status '{campaign.status}'. "
                   "Expected 'pending_images' or 'ready_to_render'.",
        )

    campaign.status = "rendering"
    db.commit()
    background_tasks.add_task(render_campaign_background, str(campaign.id))
    logger.info("Render triggered for campaign %s", campaign_id)
    return {"status": "rendering", "campaign_id": str(campaign_id)}
