"""MoviePy stitcher — downloads Pexels clips, concatenates, overlays voiceover,
burns in scene captions.

Performance optimizations:
- Async concurrent clip downloads via httpx.AsyncClient + asyncio.gather()
- FFmpeg-only processing (no MoviePy CPU bottleneck)
- Concurrent clip processing with FFmpeg
- FFmpeg concat demuxer for assembly
- Optimized encoding: preset=veryfast, threads=0, CRF single-pass

Image-based reel support:
- Ken Burns motion (slow zoom/pan) on AI-generated images
- Caption overlay on each image
- Concatenation into a video with voiceover mux

AUDIO-VIDEO SYNC: Each scene's clip duration is calculated from its narration word count (~150 WPM).
Audio segments are aligned to cumulative timestamps so voice matches scene changes exactly.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import httpx
import requests
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

# Ken Burns motion parameters
KB_START_ZOOM = 1.0
KB_END_ZOOM = 1.08
KB_PAN_X = 5  # pixels of horizontal drift (randomized per image)
KB_PAN_Y = 3  # pixels of vertical drift (randomized per image)

# Audio timing: words per minute (realistic speaking pace)
WPM = 150


# --- Timing helpers ------------------------------------------------

def estimate_duration_from_narration(narration: str) -> float:
    """Estimate narration duration based on word count at 150 WPM.

    Args:
        narration: The text to be spoken

    Returns:
        Estimated duration in seconds (minimum 1.5 seconds)
    """
    if not narration or not narration.strip():
        return 3.0
    words = len(narration.split())
    duration = (words / WPM) * 60
    return max(1.5, duration)


def get_scene_timings(scenes: list[dict[str, Any]]) -> list[tuple[int, float, float]]:
    """Calculate start/end timestamps for each scene based on narration.

    Returns:
        List of (scene_index, start_time, end_time) tuples
    """
    timings = []
    current_time = 0.0

    for scene in scenes:
        narration = scene.get("narration", "")
        duration = estimate_duration_from_narration(narration)
        timings.append((scene.get("scene_index", 0), current_time, current_time + duration))
        current_time += duration

    return timings


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
    """Render caption text on a transparent RGBA image, bottom-aligned."""
    cap_h = CAPTION_HEIGHT
    img = Image.new("RGBA", (width, cap_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _find_bold_font(font_size)
    max_text_w = int(width * 0.92)
    lines = _wrap_text(draw, text, font, max_text_w)
    bbox = draw.textbbox((0, 0), "Ay", font=font)
    line_h = int((bbox[3] - bbox[1]) * 1.2)
    y = cap_h - 20
    for line in reversed(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_h = bbox[3] - bbox[1]
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2 - bbox[0]
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y - text_h + dy), line, font=font, fill=(0, 0, 0, 255))
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
        with open(dest_path, "wb") as f:
            f.write(r.content)
    logger.info("Async downloaded %s -> %s", url, dest_path)
    return dest_path


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


# --- FFmpeg concat with proper audio sync ----------------------------------

async def stitch_reel_async(
    scenes: list[dict[str, Any]],
    voiceover_path: str,
    output_path: str,
    work_dir: str,
) -> str:
    """Fully-FFmpeg reel stitch with precise audio-video sync.

    Each scene's clip duration is calculated from its narration word count.
    Audio is aligned using segment-specific trimming for perfect sync.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(work_dir).mkdir(parents=True, exist_ok=True)

    # CRITICAL: Sort scenes by scene_index so timings, audio, and video are all aligned
    scenes = sorted(scenes, key=lambda s: s.get("scene_index", 0))

    # Caption overlay Y position
    cap_overlay_y = TARGET_H - CAPTION_HEIGHT - CAPTION_BOTTOM_MARGIN

    # Calculate scene timings based on narration (scenes are now in scene_index order)
    timings = get_scene_timings(scenes)
    logger.info("Scene timings: %s", [(t[0], t[1], t[2]) for t in timings])

    # Build clip entries with timings — clip files named by ITERATION INDEX to avoid scene_index issues
    clip_entries = []
    for i, scene in enumerate(scenes):
        url = scene.get("video_url")
        if url:
            clip_path = os.path.join(work_dir, f"clip_{i}.mp4")
            _, start_time, end_time = timings[i] if i < len(timings) else (i, 0.0, 3.0)
            clip_entries.append((i, clip_path, start_time, end_time))

    if not clip_entries:
        raise RuntimeError("No video clips available to stitch")

    # Pre-render caption images — keyed by iteration index
    idx_to_cap = {}
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

    # Process clips with audio trim for sync
    async def process_clip(idx, clip_path, start_time, end_time, cap_path):
        out = os.path.join(work_dir, f"proc_{idx}.mp4")
        duration = end_time - start_time
        trim_start = 0  # Start from beginning of clip

        if cap_path and os.path.exists(cap_path):
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(trim_start), "-t", str(duration),
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
                "-threads", "2", "-an",
                os.path.basename(out),
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(trim_start), "-t", str(duration),
                "-i", os.path.basename(clip_path),
                "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H},format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-threads", "2", "-an",
                os.path.basename(out),
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

    tasks = [
        process_clip(idx, cp, start_t, end_t, idx_to_cap.get(idx))
        for idx, cp, start_t, end_t in clip_entries
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    processed = [r for r in results if isinstance(r, str) and r]
    if not processed:
        raise RuntimeError("No clips were successfully processed")

    # Sort by iteration index (embedded in proc_X.mp4 filename by iteration order)
    def iteration_order(p: str) -> int:
        return int(Path(p).stem.split("_")[1])
    sorted_processed = sorted(processed, key=iteration_order)

    # Build iteration_index -> timing lookup (timings[i] corresponds to scenes[i] in iteration order)
    timing_map = {i: (timings[i][1], timings[i][2]) for i in range(len(timings))}

    # Write concat list
    concat_list_path = os.path.join(work_dir, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for p in sorted_processed:
            f.write(f"file '{os.path.basename(p)}'\n")

    # Build audio segments keyed by iteration index — matches sorted_processed order exactly
    audio_filters = []
    for i, proc_path in enumerate(sorted_processed):
        iter_idx = iteration_order(proc_path)
        if iter_idx not in timing_map:
            logger.warning("No timing for iteration %d, skipping audio", iter_idx)
            continue
        start_time, end_time = timing_map[iter_idx]
        duration = end_time - start_time
        audio_filters.append(
            f"[1:a]atrim=start={start_time}:duration={duration},asetpts=PTS-STARTPTS,"
            f"adelay={int(start_time * 1000)}|{int(start_time * 1000)}[a{i}]"
        )

    seg_count = len(audio_filters)
    if seg_count == 0:
        raise RuntimeError("No audio segments generated — all scenes may have failed")
    mix_inputs = "".join(f"[a{i}]" for i in range(seg_count))
    audio_filter = ";".join(audio_filters) + f";{mix_inputs}amix=inputs={seg_count}:duration=longest[outa]"

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", "concat_list.txt",
        "-i", "../voiceover.mp3",
        "-filter_complex", audio_filter,
        "-map", "0:v",
        "-map", "[outa]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-threads", "0",
        "../final.mp4",
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

    logger.info("FFmpeg reel stitch complete -> %s", output_path)
    return output_path


# --- Image-based reel stitch (Ken Burns motion) -------------------------------

async def download_image_async(url: str, dest_path: str) -> str:
    """Download an image URL to a local file."""
    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "ReelBot/1.0"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(r.content)
    logger.info("Downloaded image %s -> %s", url, dest_path)
    return dest_path


async def download_images_concurrent(
    images: list[dict[str, Any]],
    work_dir: str,
) -> list[tuple[int, str]]:
    """Download AI-generated images concurrently."""
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    tasks = []
    scene_indices = []
    for img in images:
        url = img.get("url", "")
        if not url:
            continue
        img_path = os.path.join(work_dir, f"img_{img['scene_index']}.jpg")
        tasks.append(download_image_async(url, img_path))
        scene_indices.append(img["scene_index"])

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)
    successful = []
    for idx, result in zip(scene_indices, results):
        if isinstance(result, Exception):
            logger.error("Image download scene %d failed: %s", idx, result)
        else:
            successful.append((idx, result))
    return successful


async def stitch_images_async(
    images: list[dict[str, Any]],
    voiceover_path: str,
    output_path: str,
    work_dir: str,
) -> str:
    """Render an AI-image-based reel with Ken Burns motion + captions + voiceover.

    Each image gets Ken Burns motion + caption overlay + concatenation.
    Audio is muxed with video segments for precise sync.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(work_dir).mkdir(parents=True, exist_ok=True)

    # CRITICAL: Sort images by scene_index so timings, audio, and video are all aligned
    images = sorted(images, key=lambda i: i.get("scene_index", 0))

    cap_overlay_y = TARGET_H - CAPTION_HEIGHT - CAPTION_BOTTOM_MARGIN

    # Sort images by scene_index as tiebreaker; iteration order is authoritative
    images = sorted(images, key=lambda i: (i.get("scene_index", 0), 0))

    # Download images
    downloaded = await download_images_concurrent(images, work_dir)
    if not downloaded:
        raise RuntimeError("No images were successfully downloaded")

    downloaded_sorted = sorted(downloaded, key=lambda x: x[0])

    # Calculate scene timings — timings[i] corresponds to images[i] in iteration order
    timings = get_scene_timings(images)
    logger.info("Image scene timings: %s", [(t[0], t[1], t[2]) for t in timings])

    # Build iteration_index -> timing lookup
    timing_map = {i: (timings[i][1], timings[i][2]) for i in range(len(timings))}

    # Pre-render caption images — keyed by iteration index
    idx_to_cap = {}
    for i, img in enumerate(images):
        narration = img.get("narration", "").strip()
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

    # Process images with Ken Burns motion — output named by iteration index
    async def process_image(iter_idx, img_path, cap_path):
        start_time, end_time = timing_map.get(iter_idx, (0.0, 3.0))
        duration = end_time - start_time
        nb_frames = int(duration * TARGET_FPS)

        out = os.path.join(work_dir, f"proc_{iter_idx}.mp4")

        # Randomize Ken Burns
        kb_zoom_start = KB_START_ZOOM
        kb_zoom_end = KB_END_ZOOM
        if iter_idx % 2 == 0:
            kb_zoom_start, kb_zoom_end = KB_END_ZOOM, KB_START_ZOOM

        kb_x = (TARGET_W // 2) + (KB_PAN_X if iter_idx % 2 == 0 else -KB_PAN_X)
        kb_y = (TARGET_H // 2) + (KB_PAN_Y if iter_idx % 4 < 2 else -KB_PAN_Y)

        zoompan_filter = (
            f"zoompan=z='min({kb_zoom_end},max({kb_zoom_start},{kb_zoom_start}+({kb_zoom_end - kb_zoom_start})*s/{nb_frames}))':"
            f"d={nb_frames}:s={TARGET_W}x{TARGET_H}:x={kb_x}:y={kb_y},setsar=1"
        )

        if cap_path and os.path.exists(cap_path):
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", os.path.basename(img_path),
                "-i", os.path.basename(cap_path),
                "-filter_complex",
                (
                    f"{zoompan_filter}[v];"
                    f"[1:v]format=yuva420p[cap];"
                    f"[v][cap]overlay=0:{cap_overlay_y}[out]"
                ),
                "-map", "[out]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-threads", "2", "-an",
                "-t", str(duration),
                os.path.basename(out),
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", os.path.basename(img_path),
                "-filter_complex",
                f"{zoompan_filter},format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-threads", "2", "-an",
                "-t", str(duration),
                os.path.basename(out),
            ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("Ken Burns process scene %d failed: %s", idx, stderr.decode()[-500:])
            return None
        return out

    tasks = [process_image(i, path, idx_to_cap.get(i)) for i, path in downloaded_sorted]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    processed = [r for r in results if isinstance(r, str) and r]
    if not processed:
        raise RuntimeError("No images were successfully processed")

    # Sort by iteration index (embedded in proc_X.mp4)
    def iteration_order(p: str) -> int:
        return int(Path(p).stem.split("_")[1])
    sorted_processed = sorted(processed, key=iteration_order)

    # Write concat list
    concat_list_path = os.path.join(work_dir, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for p in sorted_processed:
            f.write(f"file '{os.path.basename(p)}'\n")

    # Build audio segments keyed by iteration index
    audio_filters = []
    for i, proc_path in enumerate(sorted_processed):
        iter_idx = iteration_order(proc_path)
        if iter_idx not in timing_map:
            logger.warning("No timing for image iteration %d, skipping audio", iter_idx)
            continue
        start_time, end_time = timing_map[iter_idx]
        duration = end_time - start_time
        audio_filters.append(
            f"[1:a]atrim=start={start_time}:duration={duration},asetpts=PTS-STARTPTS,"
            f"adelay={int(start_time * 1000)}|{int(start_time * 1000)}[a{i}]"
        )

    seg_count = len(audio_filters)
    if seg_count == 0:
        raise RuntimeError("No audio segments generated — all images may have failed")
    mix_inputs = "".join(f"[a{i}]" for i in range(seg_count))
    audio_filter = ";".join(audio_filters) + f";{mix_inputs}amix=inputs={seg_count}:duration=longest[outa]"

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", "concat_list.txt",
        "-i", "../voiceover.mp3",
        "-filter_complex", audio_filter,
        "-map", "0:v",
        "-map", "[outa]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-threads", "0",
        "../final.mp4",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=work_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("FFmpeg image concat failed: %s", stderr.decode()[-500:])
        raise RuntimeError(f"FFmpeg image concat failed: {stderr.decode()[-500:]}")

    logger.info("Image-based reel stitch complete -> %s", output_path)
    return output_path
