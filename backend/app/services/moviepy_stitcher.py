"""MoviePy stitcher — downloads Pexels clips, concatenates, overlays voiceover,
burns in scene captions.

Performance optimizations:
- Async concurrent clip downloads via httpx.AsyncClient + asyncio.gather()
- FFmpeg-only processing (no MoviePy CPU bottleneck)
- Concurrent clip processing with FFmpeg
- FFmpeg concat demuxer for assembly
- Optimized encoding: preset=veryfast, threads=0, CRF single-pass
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import httpx
import requests
from moviepy import AudioFileClip
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

TARGET_W = 1080
TARGET_H = 1920  # 9:16 vertical
TARGET_FPS = 30

# Caption block: bottom-of-screen strip with a slight backdrop for legibility.
CAPTION_HEIGHT = 240
CAPTION_BOTTOM_MARGIN = 220
CAPTION_FONT_SIZE = 64
CAPTION_STROKE_WIDTH = 6


# --- Font + caption rendering (PIL) ----------------------------------------

def _find_bold_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\segoeuib.ttf",
        "arialbd.ttf",
        "Arial Bold.ttf",
        "arial.ttf",
        "Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
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


def _render_caption_image(
    text: str,
    width: int,
    font_size: int = 64,
    stroke_width: int = 4,
) -> Image.Image:
    """Render caption text on a transparent RGBA image, bottom-aligned.

    Args:
        text: caption text
        width: image width (TARGET_W = 1080)
        font_size: font size (dynamic, larger for dramatic topics)
        stroke_width: outline thickness
    """
    cap_h = CAPTION_HEIGHT
    img = Image.new("RGBA", (width, cap_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _find_bold_font(font_size)
    max_text_w = int(width * 0.92)
    lines = _wrap_text(draw, text, font, max_text_w)
    bbox = draw.textbbox((0, 0), "Ay", font=font)
    line_h = int((bbox[3] - bbox[1]) * 1.2)
    # Place text at BOTTOM of the caption image (y near cap_h)
    # Each line goes upward from there
    y = cap_h - 20  # bottom margin from image bottom
    # Reverse iterate to place from bottom upward
    for line in reversed(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_h = bbox[3] - bbox[1]
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2 - bbox[0]
        # Black stroke
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y - text_h + dy), line, font=font, fill=(0, 0, 0, 255))
        # White fill
        draw.text((x, y - text_h), line, font=font, fill=(255, 255, 255, 255))
        y -= text_h
    return img


# --- Pexels download -------------------------------------------------------

def download_clip(url: str, dest_path: str) -> str:
    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    logger.info("Downloaded %s -> %s", url, dest_path)
    return dest_path


async def download_clip_async(url: str, dest_path: str) -> str:
    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "ReelBot/1.0"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _write_file, dest_path, r.content)
    logger.info("Async downloaded %s -> %s", url, dest_path)
    return dest_path


def _write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


async def download_clips_concurrent(
    scenes: list[dict[str, Any]],
    work_dir: str,
) -> list[tuple[int, str]]:
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    tasks = []
    scene_indices = []
    for i, scene in enumerate(scenes):
        url = scene.get("video_url")
        if not url:
            continue
        clip_path = os.path.join(work_dir, f"clip_{i}.mp4")
        tasks.append(download_clip_async(url, clip_path))
        scene_indices.append(i)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    successful = []
    for idx, result in zip(scene_indices, results):
        if isinstance(result, Exception):
            logger.error("Failed to download scene %d: %s", idx, result)
        else:
            successful.append((idx, result))
    return successful


# --- FFmpeg-only stitch -----------------------------------------------------

async def stitch_reel_async(
    scenes: list[dict[str, Any]],
    voiceover_path: str,
    output_path: str,
    work_dir: str,
) -> str:
    """Fully-FFmpeg reel stitch — clips processed concurrently for maximum speed.

    1. Render caption images with PIL (fast)
    2. Process each clip concurrently with FFmpeg (resize + crop + caption overlay)
    3. Concat all processed clips with FFmpeg concat demuxer
    4. Mux audio into final output
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(work_dir).mkdir(parents=True, exist_ok=True)

    # Caption overlay Y: absolute pixel position from top of 1920px frame
    cap_overlay_y = TARGET_H - CAPTION_HEIGHT - CAPTION_BOTTOM_MARGIN  # 1460

    # Build clip entries first (needed to count scenes for per_scene calc)
    clip_entries: list[tuple[int, str]] = []
    for i, scene in enumerate(scenes):
        url = scene.get("video_url")
        if url:
            clip_path = os.path.join(work_dir, f"clip_{i}.mp4")
            clip_entries.append((i, clip_path))

    if not clip_entries:
        raise RuntimeError("No video clips available to stitch")

    # Get voiceover duration to calculate per-scene clip duration
    audio = AudioFileClip(voiceover_path)
    total_duration = audio.duration
    audio.close()
    scene_count = max(1, len(clip_entries))
    per_scene = max(2.0, total_duration / scene_count)

    # Pre-render caption images (before process_clip so idx_to_cap is available)
    idx_to_cap: dict[int, str | None] = {}
    for i, scene in enumerate(scenes):
        narration = scene.get("narration", "").strip()
        cap_path = os.path.join(work_dir, f"caption_{i}.png")
        if narration:
            text_len = len(narration)
            if text_len > 80:
                fs, sw = 44, 3
            elif text_len > 50:
                fs, sw = 52, 4
            else:
                fs, sw = 64, 5
            cap_img = _render_caption_image(narration, width=TARGET_W, font_size=fs, stroke_width=sw)
            cap_img.save(cap_path, "PNG")
            idx_to_cap[i] = cap_path
        else:
            idx_to_cap[i] = None

    # 3. Process all clips concurrently with FFmpeg
    async def process_clip(idx: int, clip_path: str, cap_path: str | None) -> str | None:
        out = os.path.join(work_dir, f"proc_{idx}.mp4")
        if cap_path and os.path.exists(cap_path):
            cmd = [
                "ffmpeg", "-y",
                "-ss", "0", "-t", str(per_scene),
                "-i", os.path.basename(clip_path),
                "-i", os.path.basename(cap_path),
                "-filter_complex",
                (
                    f"[0:v]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
                    f"crop={TARGET_W}:{TARGET_H},format=yuv420p[v];"
                    f"[1:v]format=yuva420p[cap];"
                    f"[v][cap]overlay=0:{cap_overlay_y}[out]"
                ),
                "-map", "[out]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-threads", "2", "-an", os.path.basename(out),
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-ss", "0", "-t", str(per_scene),
                "-i", os.path.basename(clip_path),
                "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H},format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-threads", "2", "-an", os.path.basename(out),
            ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("FFmpeg clip %d failed: %s", idx, stderr.decode()[-500:])
            return None
        return out

    tasks = [process_clip(idx, cp, idx_to_cap.get(idx)) for idx, cp in clip_entries]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    processed = [r for r in results if isinstance(r, str) and r]
    if not processed:
        raise RuntimeError("No clips were successfully processed")

    # Sort by scene index to maintain order
    def scene_order(p: str) -> int:
        stem = Path(p).stem          # e.g. "proc_2"
        return int(stem.split("_")[1])
    sorted_processed = sorted(processed, key=scene_order)

    # 4. Write concat list
    concat_list_path = os.path.join(work_dir, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for p in sorted_processed:
            f.write(f"file '{os.path.basename(p)}'\n")

    # 5. Concat + mux audio in one FFmpeg command
    # voiceover_path is one level up from work_dir (clips/), so use ../voiceover.mp3
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", "concat_list.txt",
        "-i", "..//voiceover.mp3",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-threads", "0", "-shortest",
        "..//final.mp4",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=work_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("FFmpeg concat failed: %s", stderr.decode()[-500:])
        raise RuntimeError(f"FFmpeg concat failed: {stderr.decode()[-500:]}")

    # 6. Cleanup temp files
    try:
        os.remove(concat_list_path)
        for p in sorted_processed:
            os.remove(p)
        for cap_path in idx_to_cap.values():
            if cap_path and os.path.exists(cap_path):
                os.remove(cap_path)
    except OSError:
        pass

    logger.info("FFmpeg reel stitch complete -> %s", output_path)
    return output_path
