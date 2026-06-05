"""Render worker — orchestrates edge-tts → MoviePy → Supabase upload.

Runs in a FastAPI BackgroundTask. Any exception is caught and persisted as
status='failed' on the campaign row, so the worker can never crash the API.
"""
from __future__ import annotations

import logging
import os
import traceback
from datetime import datetime, timezone

from app.config import settings
from app.database import SessionLocal
from app.models.campaign import Campaign
from app.services.edge_tts_service import run_synthesize_sync
from app.services.moviepy_stitcher import stitch_reel
from app.services.supabase_storage import upload_video

logger = logging.getLogger(__name__)


def render_campaign_background(campaign_id: str) -> None:
    """Top-level orchestration. Safe to call from a BackgroundTask."""
    logger.info("Starting render for campaign %s", campaign_id)
    db = SessionLocal()
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            logger.error("Campaign %s not found in render worker", campaign_id)
            return

        if not campaign.voiceover_full:
            raise RuntimeError("voiceover_full is empty — Make.com callback missing?")
        if not campaign.scenes_with_assets:
            raise RuntimeError("scenes_with_assets is empty — Make.com callback missing?")

        # 1. Mark rendering
        campaign.status = "rendering"
        db.commit()

        work_dir = os.path.join(settings.local_storage_dir, str(campaign_id))
        os.makedirs(work_dir, exist_ok=True)

        # 2. Synthesize voiceover
        voiceover_path = os.path.join(work_dir, "voiceover.mp3")
        run_synthesize_sync(
            voiceover_text=campaign.voiceover_full,
            output_path=voiceover_path,
            voice=campaign.voice,
        )

        # 3. Stitch MP4
        output_path = os.path.join(work_dir, "final.mp4")
        stitch_reel(
            scenes=campaign.scenes_with_assets,
            voiceover_path=voiceover_path,
            output_path=output_path,
            work_dir=os.path.join(work_dir, "clips"),
        )
        logger.info("Stitch complete for %s: %s", campaign_id, output_path)

        # 4. Upload to Supabase. Skipped entirely in mock mode — the whole
        # point of mock mode is local testing, and a hang here used to wedge
        # the worker when Supabase was unreachable. In mock mode we point
        # video_url at the local static-file mount so the frontend can play it.
        if settings.mock_mode:
            local_url = (
                f"{settings.app_base_url.rstrip('/')}/storage/{campaign_id}/final.mp4"
            )
            logger.info(
                "MOCK_MODE active — skipping Supabase upload, serving local file at %s",
                local_url,
            )
            video_url: str | None = local_url
        else:
            video_url = upload_video(output_path, f"{campaign_id}.mp4")

        # 5. Mark complete
        campaign.video_path = output_path
        campaign.video_url = video_url
        campaign.status = "completed"
        campaign.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(
            "Render complete for campaign %s: %s",
            campaign_id,
            video_url or output_path,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Render failed for campaign %s: %s\n%s",
            campaign_id,
            exc,
            traceback.format_exc(),
        )
        try:
            # Re-query the campaign — the original `campaign` binding may not
            # exist if the query itself raised.
            failed = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if failed is not None:
                failed.status = "failed"
                failed.error_message = str(exc)[:2000]
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to persist failure state for %s", campaign_id)
    finally:
        db.close()
