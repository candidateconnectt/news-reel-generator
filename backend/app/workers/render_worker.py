"""Render worker — orchestrates edge-tts → MoviePy → Supabase upload.

Runs in a FastAPI BackgroundTask. Any exception is caught and persisted as
status='failed' on the campaign row, so the worker can never crash the API.

Performance optimizations:
- Async clip downloads (concurrent via asyncio.gather)
- FFmpeg concat demuxer for faster video assembly
- Async Supabase upload with thread-pool file reads
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import traceback
from datetime import datetime, timezone

from app.config import settings
from app.database import SessionLocal
from app.models.campaign import Campaign
from app.services.edge_tts_service import run_synthesize_sync
from app.services.supabase_storage import upload_video_async

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

        campaign.status = "rendering"
        db.commit()

        # Use a temp directory — cleaned up automatically after upload
        work_dir = tempfile.mkdtemp(prefix=f"reel_{campaign_id}_")
        clips_dir = os.path.join(work_dir, "clips")
        voiceover_path = os.path.join(work_dir, "voiceover.mp3")
        output_path = os.path.join(work_dir, "final.mp4")
        os.makedirs(clips_dir, exist_ok=True)

        asyncio.run(_render_and_upload(
            campaign, output_path, clips_dir, voiceover_path, db,
        ))
        logger.info("Render complete for %s", campaign_id)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Render failed for campaign %s: %s\n%s",
            campaign_id,
            exc,
            traceback.format_exc(),
        )
        try:
            failed = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if failed is not None:
                failed.status = "failed"
                failed.error_message = str(exc)[:2000]
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to persist failure state for %s", campaign_id)
    finally:
        db.close()


async def _render_and_upload(
    campaign: Campaign,
    output_path: str,
    clips_dir: str,
    voiceover_path: str,
    db,
) -> None:
    """Render video and upload to Supabase, then clean up the temp dir."""
    try:
        # Synthesize voiceover
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_synthesize_sync,
            campaign.voiceover_full, voiceover_path, campaign.voice)

        # Route based on campaign type
        if campaign.campaign_type == "reel_image":
            # AI-generated image storyboard → Ken Burns motion + captions + voiceover
            from app.services.ffmpeg_stitcher import stitch_images_async
            images = campaign.generated_images or []
            if not images:
                raise RuntimeError("generated_images is empty — call /generate-reel-scenes first")
            await stitch_images_async(
                images=images,
                voiceover_path=voiceover_path,
                output_path=output_path,
                work_dir=clips_dir,
            )
            logger.info("Image-based stitch complete for %s: %s", campaign.id, output_path)
        else:
            # Pexels video clips → resize + caption overlay + concat + voiceover
            from app.services.ffmpeg_stitcher import download_clips_concurrent, stitch_reel_async
            successful_downloads = await download_clips_concurrent(
                campaign.scenes_with_assets, clips_dir,
            )
            if not successful_downloads:
                raise RuntimeError("No clips were successfully downloaded")

            scenes_with_paths = []
            for idx, clip_path in successful_downloads:
                scene = campaign.scenes_with_assets[idx]
                scene["video_url"] = clip_path
                scenes_with_paths.append(scene)

            await stitch_reel_async(
                scenes=scenes_with_paths,
                voiceover_path=voiceover_path,
                output_path=output_path,
                work_dir=clips_dir,
            )
            logger.info("Video-based stitch complete for %s: %s", campaign.id, output_path)

        # Upload to Supabase (always, no mock bypass)
        video_url = await upload_video_async(output_path, f"{campaign.id}.mp4")

        # Clean up entire temp directory
        import shutil as _sh
        try:
            _sh.rmtree(os.path.dirname(os.path.dirname(output_path)))
            logger.info("Cleaned up temp directory")
        except OSError as e:
            logger.warning("Failed to clean up temp dir: %s", e)

        # Mark complete
        campaign.video_path = None
        campaign.video_url = video_url
        campaign.status = "completed"
        campaign.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Render complete for campaign %s: %s", campaign.id, video_url)
    except Exception as exc:
        raise RuntimeError(f"Render failed: {exc}") from exc
