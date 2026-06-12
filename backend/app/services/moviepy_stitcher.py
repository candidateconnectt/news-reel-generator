"""MoviePy stitcher — downloads Pexels clips, overlays voiceover, burns captions.
FIXED: Railway-compatible version with proper global variables and functions.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import shutil
from pathlib import Path
from typing import Any

import httpx
import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

TARGET_W = 1080
TARGET_H = 1920  # 9:16 vertical
TARGET_FPS = 30

# Caption block: bottom-of-screen strip
CAPTION_HEIGHT = 240
CAPTION_BOTTOM_MARGIN = 220
CAPTION_FONT_SIZE = 64
CAPTION_STROKE_WIDTH = 6

# Ken Burns motion parameters
KB_START_ZOOM = 1.0
KB_END_ZOOM = 1.08
KB_PAN_X = 5
KB_PAN_Y = 3

# ========== GLOBAL VARIABLES (CRITICAL FOR RAILWAY) ==========
_FFPROBE_PATH = None
_FFMPEG_PATH = None


# --- Helper to find ffmpeg/ffprobe ---
def find_ffprobe():
    """Find ffprobe executable path."""
    path = shutil.which('ffprobe')
    if path:
        return path
    for p in ['/usr/local/bin/ffprobe', '/usr/bin/ffprobe']:
        if os.path.exists(p):
            return p
    raise RuntimeError("ffprobe not found")


def find_ffmpeg():
    """Find ffmpeg executable path."""
    path = shutil.which('ffmpeg')
    if path:
        return path
    for p in ['/usr/local/bin/ffmpeg', '/usr/bin/ffmpeg']:
        if os.path.exists(p):
            return p
    raise RuntimeError("ffmpeg not found")


# --- ACTUAL AUDIO DURATION (THE MASTER CLOCK) ---

async def get_audio_duration(file_path: str) -> float:
    """Get EXACT duration of audio file using ffprobe."""
    global _FFPROBE_PATH
    if _FFPROBE_PATH is None:
        _FFPROBE_PATH = find_ffprobe()
    
    cmd = [
        _FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return float(stdout.decode().strip())


async def get_video_duration(file_path: str) -> float:
    """Get accurate duration of video file using ffprobe."""
    global _FFPROBE_PATH
    if _FFPROBE_PATH is None:
        _FFPROBE_PATH = find_ffprobe()
    
    cmd = [
        _FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return float(stdout.decode().strip())


# --- Font + caption rendering (PIL) ----------------------------------------

def _find_bold_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\segoeuib.ttf",
        "arialbd.ttf",
        "Arial Bold.ttf",
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

async def download_clip_async(url: str, dest_path: str) -> str:
    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "ReelBot/1.0"}
    async with httpx.AsyncClient(timeout=120.0) as client:
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
        clip_path = os.path.join(work_dir, f"clip_{i:03d}.mp4")
        tasks.append(download_clip_async(url, clip_path))
        scene_indices.append(i)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    successful = []
    for idx, result in zip(scene_indices, results):
        if isinstance(result, Exception):
            logger.error("Failed to download scene %d: %s", idx, result)
        else:
            successful.append((idx, result))
    return sorted(successful, key=lambda x: x[0])


async def extract_audio_segment(
    voiceover_path: str,
    start_time: float,
    duration: float,
    output_path: str,
) -> str:
    """Extract precise audio segment for a scene."""
    global _FFMPEG_PATH
    if _FFMPEG_PATH is None:
        _FFMPEG_PATH = find_ffmpeg()
    
    cmd = [
        _FFMPEG_PATH, "-y", "-threads", "1",
        "-ss", str(start_time),
        "-t", str(duration),
        "-i", voiceover_path,
        "-c:a", "aac", "-b:a", "128k",
        "-ar", "44100",
        output_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Audio extraction failed: {stderr.decode()[:500]}")
        raise RuntimeError(f"Audio extraction failed for {start_time}-{duration}")
    return output_path


# --- WORKING CHUNK CREATION FOR RAILWAY ---

async def create_normalized_video_chunk(
    clip_path: str,
    idx: int,
    target_duration: float,
    caption_path: str,
    work_dir: str,
) -> str:
    """Create a normalized video chunk in a SINGLE ffmpeg pass.

    Consolidates the previous 4-step pipeline (scale -> pad -> trim ->
    overlay, 3 intermediate files per scene) into one
    filter_complex invocation. ~3x less disk I/O, ~3x fewer
    encode passes, no intermediate scaled_/padded_/trimmed_*.mp4
    files left on Railway's 1GB disk.
    """
    global _FFMPEG_PATH
    if _FFMPEG_PATH is None:
        _FFMPEG_PATH = find_ffmpeg()

    # Defensive: make sure work_dir exists.
    os.makedirs(work_dir, exist_ok=True)

    output_path = os.path.join(work_dir, f"chunk_{idx:03d}.mp4")
    cap_overlay_y = TARGET_H - CAPTION_HEIGHT - CAPTION_BOTTOM_MARGIN

    clip_duration = await get_video_duration(clip_path)
    logger.info(f"Scene {idx}: Clip={clip_duration:.2f}s, Target={target_duration:.2f}s")

    # Build the pre-overlay filter chain. The whole pipeline lives
    # in one ffmpeg invocation now -- no scaled_/padded_/trimmed_*.mp4
    # intermediate files.
    #
    # Filter order (left to right = applied in order):
    #   scale=...:force_original_aspect_ratio=decrease -> fit within 1080x1920
    #   pad=...   -> exactly 1080x1920 (black bars if needed)
    #   loop=...  -> (only if target > clip) extend by looping
    #   trim=...  -> cut to target_duration
    #   setpts    -> reset timestamps to 0
    #   fps=30    -> force 30fps output
    #   format=yuv420p -> required for libx264 + most players
    pre_filters = [
        f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease",
        f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2",
    ]
    if target_duration > clip_duration:
        # Clip too short -> loop it to reach target duration before trimming.
        # The size uses TARGET_FPS as an upper bound; the loop filter
        # is lenient about exact frame counts (works on Windows ffmpeg
        # and the johnvansickle static build on Railway).
        loops_needed = int(target_duration / clip_duration) + 1
        pre_filters.append(
            f"loop=loop={loops_needed}:size={int(clip_duration * TARGET_FPS)}"
        )
    pre_filters.extend([
        f"trim=duration={target_duration}",
        "setpts=PTS-STARTPTS",
        f"fps={TARGET_FPS}",
        "format=yuv420p",
    ])
    base_chain = ",".join(pre_filters)

    if caption_path and os.path.exists(caption_path):
        # Two-input filter_complex: [0:v] is the Pexels clip with
        # the pre_chain applied -> [v]; [1:v] is the caption PNG;
        # overlay the caption on [v] -> [out]. Map only [out] so
        # no audio stream is included (-an is implied by -map).
        filter_complex = (
            f"{base_chain}[v];"
            f"[1:v]format=yuva420p[cap];"
            f"[v][cap]overlay=0:{cap_overlay_y}[out]"
        )
        cmd = [
            _FFMPEG_PATH, "-y", "-threads", "1",
            "-i", clip_path,
            "-i", caption_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-r", str(TARGET_FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-an",
            output_path,
        ]
    else:
        # No caption: simpler single-input -vf chain.
        cmd = [
            _FFMPEG_PATH, "-y", "-threads", "1",
            "-i", clip_path,
            "-vf", base_chain,
            "-r", str(TARGET_FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-an",
            output_path,
        ]

    logger.info(f"Scene {idx}: chunk cmd = {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        # Log the FULL stderr, not a 300-char truncation. The actual
        # ffmpeg reason (OOM, bad filter arg, missing codec) is
        # usually later in the output, not the version banner.
        err = stderr.decode(errors="replace")
        logger.error(f"Scene {idx}: chunk failed (rc={proc.returncode})")
        logger.error(f"Scene {idx}: chunk full stderr:\n{err}")
        raise RuntimeError(
            f"Chunk failed for scene {idx}: "
            f"{err.splitlines()[-1] if err else 'no stderr'}"
        )

    logger.info(f"Scene {idx}: Chunk created (single-pass)")
    return output_path


async def create_normalized_image_chunk(
    img_path: str,
    idx: int,
    target_duration: float,
    caption_path: str,
    work_dir: str,
) -> str:
    """Create a normalized video chunk from an image with Ken Burns motion."""
    global _FFMPEG_PATH
    if _FFMPEG_PATH is None:
        _FFMPEG_PATH = find_ffmpeg()
    
    output_path = os.path.join(work_dir, f"chunk_{idx:03d}.mp4")
    cap_overlay_y = TARGET_H - CAPTION_HEIGHT - CAPTION_BOTTOM_MARGIN
    
    nb_frames = int(target_duration * TARGET_FPS)
    if nb_frames < 1:
        nb_frames = 1
    
    zoom_start, zoom_end = KB_START_ZOOM, KB_END_ZOOM
    if idx % 2 == 0:
        zoom_start, zoom_end = KB_END_ZOOM, KB_START_ZOOM
    
    x_center = (TARGET_W // 2) + (KB_PAN_X if idx % 2 == 0 else -KB_PAN_X)
    y_center = (TARGET_H // 2) + (KB_PAN_Y if idx % 4 < 2 else -KB_PAN_Y)
    
    zoompan_filter = (
        f"zoompan=z='min({zoom_end},max({zoom_start},{zoom_start}+({zoom_end}-{zoom_start})*s/{nb_frames}))':"
        f"d={nb_frames}:s={TARGET_W}x{TARGET_H}:x={x_center}:y={y_center}:fps={TARGET_FPS},"
        f"setpts=PTS-STARTPTS"
    )
    
    temp_video = os.path.join(work_dir, f"temp_image_{idx:03d}.mp4")
    cmd_video = [
        _FFMPEG_PATH, "-y", "-threads", "1", "-loop", "1", "-i", img_path,
        "-vf", f"{zoompan_filter},format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-video_track_timescale", str(TARGET_FPS),
        "-r", str(TARGET_FPS), "-vsync", "cfr",
        "-t", str(target_duration), temp_video,
    ]
    proc = await asyncio.create_subprocess_exec(*cmd_video, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Image video failed: {stderr.decode()[:300]}")
        raise RuntimeError(f"Image video failed for scene {idx}")
    
    if caption_path and os.path.exists(caption_path):
        cmd_overlay = [
            _FFMPEG_PATH, "-y", "-threads", "1",
            "-i", temp_video, "-i", caption_path,
            "-filter_complex", f"[1:v]format=yuva420p[cap];[0:v][cap]overlay=0:{cap_overlay_y},format=yuv420p[out]",
            "-map", "[out]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(*cmd_overlay, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"Overlay failed: {stderr.decode()[:300]}")
            raise RuntimeError(f"Overlay failed for scene {idx}")
        os.unlink(temp_video)
    else:
        os.rename(temp_video, output_path)
    
    return output_path


# --- Main Stitching Functions ---

async def stitch_reel_async(
    scenes: list[dict[str, Any]],
    voiceover_path: str,
    output_path: str,
    work_dir: str,
) -> str:
    """Main stitching function."""
    global _FFMPEG_PATH
    if _FFMPEG_PATH is None:
        _FFMPEG_PATH = find_ffmpeg()
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    chunks_dir = os.path.join(work_dir, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)
    
    scenes = sorted(scenes, key=lambda s: s.get("scene_index", 0))
    full_voiceover_duration = await get_audio_duration(voiceover_path)
    
    narrations = [scene.get("narration", "") for scene in scenes]
    total_chars = sum(len(n) for n in narrations)
    if total_chars == 0:
        raise RuntimeError("No narration text found")
    
    timings = []
    current_time = 0.0
    for i, narration in enumerate(narrations):
        proportion = len(narration) / total_chars
        duration = proportion * full_voiceover_duration
        timings.append((i, current_time, current_time + duration))
        current_time += duration
    
    logger.info(f"Total voiceover: {full_voiceover_duration:.2f}s")
    
    caption_paths = {}
    for i, scene in enumerate(scenes):
        narration = scene.get("narration", "").strip()
        if narration:
            caption_path = os.path.join(chunks_dir, f"caption_{i:03d}.png")
            text_len = len(narration)
            fs = 64 if text_len <= 50 else (52 if text_len <= 80 else 44)
            sw = 5 if text_len <= 50 else (4 if text_len <= 80 else 3)
            cap_img = _render_caption_image(narration, width=TARGET_W, font_size=fs, stroke_width=sw)
            cap_img.save(caption_path, "PNG")
            caption_paths[i] = caption_path
        else:
            caption_paths[i] = None
    
    processed_chunks = []
    processed_audios = []
    
    for i, scene in enumerate(scenes):
        clip_path = scene.get("video_url")
        if not clip_path or not os.path.exists(clip_path):
            raise RuntimeError(f"Scene {i}: no valid video")
        
        _, start_time, end_time = timings[i]
        duration = end_time - start_time
        logger.info(f"Scene {i}: duration={duration:.2f}s")
        
        video_chunk = await create_normalized_video_chunk(clip_path, i, duration, caption_paths.get(i), chunks_dir)
        processed_chunks.append(video_chunk)
        
        audio_chunk = os.path.join(chunks_dir, f"audio_{i:03d}.m4a")
        await extract_audio_segment(voiceover_path, start_time, duration, audio_chunk)
        processed_audios.append(audio_chunk)
    
    # Concat videos
    concat_file = os.path.join(chunks_dir, "concat_video.txt")
    with open(concat_file, "w") as f:
        for chunk in processed_chunks:
            f.write(f"file '{chunk}'\n")
    
    combined_video = os.path.join(chunks_dir, "combined_video.mp4")
    cmd_concat = [_FFMPEG_PATH, "-y", "-threads", "1", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", combined_video]
    proc = await asyncio.create_subprocess_exec(*cmd_concat, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Video concat failed: {stderr.decode()[:500]}")
        raise RuntimeError("Video concatenation failed")
    
    # Concat audios
    concat_file = os.path.join(chunks_dir, "concat_audio.txt")
    with open(concat_file, "w") as f:
        for audio in processed_audios:
            f.write(f"file '{audio}'\n")
    
    combined_audio = os.path.join(chunks_dir, "combined_audio.m4a")
    cmd_concat = [_FFMPEG_PATH, "-y", "-threads", "1", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", combined_audio]
    proc = await asyncio.create_subprocess_exec(*cmd_concat, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Audio concat failed: {stderr.decode()[:500]}")
        raise RuntimeError("Audio concatenation failed")
    
    # Mux
    cmd_mux = [_FFMPEG_PATH, "-y", "-threads", "1", "-i", combined_video, "-i", combined_audio, "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", output_path]
    proc = await asyncio.create_subprocess_exec(*cmd_mux, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Mux failed: {stderr.decode()[:500]}")
        raise RuntimeError("Muxing failed")
    
    logger.info(f"Reel complete: {output_path}")
    return output_path


async def stitch_images_async(
    images: list[dict[str, Any]],
    voiceover_path: str,
    output_path: str,
    work_dir: str,
) -> str:
    """Render AI-image-based reel with perfect sync."""
    global _FFMPEG_PATH
    if _FFMPEG_PATH is None:
        _FFMPEG_PATH = find_ffmpeg()
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    chunks_dir = os.path.join(work_dir, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)
    
    images = sorted(images, key=lambda i: i.get("scene_index", 0))
    full_voiceover_duration = await get_audio_duration(voiceover_path)
    
    narrations = [img.get("narration", "") for img in images]
    total_chars = sum(len(n) for n in narrations)
    if total_chars == 0:
        raise RuntimeError("No narration text found")
    
    timings = []
    current_time = 0.0
    for i, narration in enumerate(narrations):
        proportion = len(narration) / total_chars
        duration = proportion * full_voiceover_duration
        timings.append((i, current_time, current_time + duration))
        current_time += duration
    
    logger.info(f"Total voiceover: {full_voiceover_duration:.2f}s")
    
    downloaded = await download_images_concurrent(images, chunks_dir)
    if not downloaded:
        raise RuntimeError("No images downloaded")
    
    caption_paths = {}
    for i, img in enumerate(images):
        narration = img.get("narration", "").strip()
        if narration:
            caption_path = os.path.join(chunks_dir, f"caption_{i:03d}.png")
            text_len = len(narration)
            fs = 64 if text_len <= 50 else (52 if text_len <= 80 else 44)
            sw = 5 if text_len <= 50 else (4 if text_len <= 80 else 3)
            cap_img = _render_caption_image(narration, width=TARGET_W, font_size=fs, stroke_width=sw)
            cap_img.save(caption_path, "PNG")
            caption_paths[i] = caption_path
        else:
            caption_paths[i] = None
    
    downloaded_map = {idx: path for idx, path in downloaded}
    processed_chunks = []
    processed_audios = []
    
    for i, img in enumerate(images):
        img_path = downloaded_map.get(img.get("scene_index", i))
        if not img_path or not os.path.exists(img_path):
            raise RuntimeError(f"Image {i}: no valid file")
        
        _, start_time, end_time = timings[i]
        duration = end_time - start_time
        logger.info(f"Image {i}: duration={duration:.2f}s")
        
        video_chunk = await create_normalized_image_chunk(img_path, i, duration, caption_paths.get(i), chunks_dir)
        processed_chunks.append(video_chunk)
        
        audio_chunk = os.path.join(chunks_dir, f"audio_{i:03d}.m4a")
        await extract_audio_segment(voiceover_path, start_time, duration, audio_chunk)
        processed_audios.append(audio_chunk)
    
    # Concat videos
    concat_file = os.path.join(chunks_dir, "concat_video.txt")
    with open(concat_file, "w") as f:
        for chunk in processed_chunks:
            f.write(f"file '{chunk}'\n")
    
    combined_video = os.path.join(chunks_dir, "combined_video.mp4")
    cmd_concat = [_FFMPEG_PATH, "-y", "-threads", "1", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", combined_video]
    proc = await asyncio.create_subprocess_exec(*cmd_concat, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Video concat failed: {stderr.decode()[:500]}")
        raise RuntimeError("Video concatenation failed")
    
    # Concat audios
    concat_file = os.path.join(chunks_dir, "concat_audio.txt")
    with open(concat_file, "w") as f:
        for audio in processed_audios:
            f.write(f"file '{audio}'\n")
    
    combined_audio = os.path.join(chunks_dir, "combined_audio.m4a")
    cmd_concat = [_FFMPEG_PATH, "-y", "-threads", "1", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", combined_audio]
    proc = await asyncio.create_subprocess_exec(*cmd_concat, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Audio concat failed: {stderr.decode()[:500]}")
        raise RuntimeError("Audio concatenation failed")
    
    # Mux
    cmd_mux = [_FFMPEG_PATH, "-y", "-threads", "1", "-i", combined_video, "-i", combined_audio, "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", output_path]
    proc = await asyncio.create_subprocess_exec(*cmd_mux, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Mux failed: {stderr.decode()[:500]}")
        raise RuntimeError("Muxing failed")
    
    logger.info(f"Image reel complete: {output_path}")
    return output_path


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
        img_path = os.path.join(work_dir, f"img_{img.get('scene_index', 0):03d}.jpg")
        tasks.append(download_image_async(url, img_path))
        scene_indices.append(img.get("scene_index", 0))
    
    if not tasks:
        return []
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    successful = []
    for idx, result in zip(scene_indices, results):
        if isinstance(result, Exception):
            logger.error("Image download scene %d failed: %s", idx, result)
        else:
            successful.append((idx, result))
    return sorted(successful, key=lambda x: x[0])


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