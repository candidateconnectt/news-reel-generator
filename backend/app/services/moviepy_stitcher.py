"""MoviePy stitcher — downloads Pexels clips, concatenates, overlays voiceover,
burns in scene captions.

Uses MoviePy v2.x import style. Captions are rendered with PIL (no
ImageMagick dependency required) and composited onto each scene before
concatenation.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import requests
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

TARGET_W = 1080
TARGET_H = 1920  # 9:16 vertical
TARGET_FPS = 30

# Caption block: bottom-of-screen strip with a slight backdrop for legibility.
CAPTION_HEIGHT = 240
CAPTION_BOTTOM_MARGIN = 220  # distance from bottom of frame to caption block
CAPTION_FONT_SIZE = 64
CAPTION_STROKE_WIDTH = 6


# --- Font + caption rendering (PIL) ----------------------------------------

def _find_bold_font(size: int) -> ImageFont.FreeTypeFont:
    """Find a bold sans-serif font on the system, with a graceful fallback chain."""
    candidates = [
        # Windows
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\segoeuib.ttf",
        "arialbd.ttf",
        "Arial Bold.ttf",
        "arial.ttf",
        "Arial.ttf",
        # macOS
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    """Word-wrap text to fit within `max_width` pixels."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = (current + " " + word) if current else word
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _render_caption_image(text: str, width: int) -> Image.Image:
    """Render caption text on a transparent RGBA image.

    White text with a thick black stroke, word-wrapped to 90% of the video
    width. Returns a PIL Image sized (width, CAPTION_HEIGHT).
    """
    img = Image.new("RGBA", (width, CAPTION_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _find_bold_font(CAPTION_FONT_SIZE)

    max_text_w = int(width * 0.9)
    lines = _wrap_text(draw, text, font, max_text_w)

    # Measure line height from font metrics
    bbox = draw.textbbox((0, 0), "Ay", font=font)
    line_h = int((bbox[3] - bbox[1]) * 1.15)
    total_h = len(lines) * line_h
    y = (CAPTION_HEIGHT - total_h) // 2 - bbox[1]

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2 - bbox[0]
        # Black stroke (outline)
        sw = CAPTION_STROKE_WIDTH
        for dx in range(-sw, sw + 1):
            for dy in range(-sw, sw + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
        # White fill
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_h

    return img


def _overlay_caption(
    video_clip: VideoFileClip, narration: str, video_w: int, video_h: int
) -> VideoFileClip:
    """Composite a caption clip onto a single scene's video clip."""
    if not narration or not narration.strip():
        return video_clip
    cap_img = _render_caption_image(narration, width=video_w)
    cap_clip = ImageClip(np.array(cap_img))
    cap_clip = cap_clip.with_duration(video_clip.duration)
    cap_clip = cap_clip.with_position(
        ("center", video_h - CAPTION_BOTTOM_MARGIN - CAPTION_HEIGHT)
    )
    return CompositeVideoClip([video_clip, cap_clip])


# --- Pexels download -------------------------------------------------------

def download_clip(url: str, dest_path: str) -> str:
    """Download a remote video clip to disk. Streams to handle large files."""
    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    logger.info("Downloaded %s -> %s", url, dest_path)
    return dest_path


# --- Vertical fitting ------------------------------------------------------

def _fit_vertical(clip: VideoFileClip) -> VideoFileClip:
    """Resize + center-crop / pad the clip to TARGET_W x TARGET_H (1080x1920)."""
    if clip.h < clip.w:
        clip = clip.resized(height=TARGET_H)
        if clip.w > TARGET_W:
            x_center = clip.w / 2
            clip = clip.cropped(
                x1=x_center - TARGET_W / 2,
                y1=0,
                x2=x_center + TARGET_W / 2,
                y2=TARGET_H,
            )
    else:
        clip = clip.resized(height=TARGET_H)
        if clip.w > TARGET_W:
            x_center = clip.w / 2
            clip = clip.cropped(
                x1=x_center - TARGET_W / 2,
                y1=0,
                x2=x_center + TARGET_W / 2,
                y2=TARGET_H,
            )

    if (clip.w, clip.h) != (TARGET_W, TARGET_H):
        bg = ColorClip(
            size=(TARGET_W, TARGET_H),
            color=(0, 0, 0),
            duration=clip.duration,
        )
        clip = CompositeVideoClip(
            [bg, clip.with_position("center")],
            size=(TARGET_W, TARGET_H),
        )
    return clip


# --- Main stitch -----------------------------------------------------------

def stitch_reel(
    scenes: list[dict[str, Any]],
    voiceover_path: str,
    output_path: str,
    work_dir: str,
) -> str:
    """Stitch Pexels clips + voiceover into a final vertical MP4 with burned-in captions."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(work_dir).mkdir(parents=True, exist_ok=True)

    audio = AudioFileClip(voiceover_path)
    total_duration = audio.duration
    scene_count = max(1, len(scenes))
    per_scene = max(2.0, total_duration / scene_count)

    video_clips: list[VideoFileClip] = []
    for i, scene in enumerate(scenes):
        url = scene.get("video_url")
        if not url:
            logger.warning("Scene %d has no video_url; skipping", i)
            continue
        clip_path = os.path.join(work_dir, f"clip_{i}.mp4")
        try:
            download_clip(url, clip_path)
            clip = VideoFileClip(clip_path)
            clip = _fit_vertical(clip)
            take = min(per_scene, clip.duration)
            clip = clip.subclipped(0, take)
            # Burn in the scene's narration as a caption
            clip = _overlay_caption(
                clip, scene.get("narration", ""), TARGET_W, TARGET_H
            )
            video_clips.append(clip)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to process scene %d (%s): %s", i, url, exc)
            continue

    if not video_clips:
        audio.close()
        raise RuntimeError("No video clips were successfully processed")

    final_video = concatenate_videoclips(video_clips, method="compose")
    final_video = final_video.with_audio(audio)
    final_video.write_videofile(
        output_path,
        fps=TARGET_FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        logger="bar",
    )

    for clip in video_clips:
        clip.close()
    final_video.close()
    audio.close()

    logger.info("Stitched final reel -> %s", output_path)
    return output_path
