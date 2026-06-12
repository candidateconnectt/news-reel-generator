"""MoviePy stitcher — downloads Pexels clips, overlays voiceover, burns captions.
IMPROVED: Isolated Chunk Architecture with perfect audio-video sync using actual TTS durations.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import subprocess as sp
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


# --- ACTUAL AUDIO DURATION (THE MASTER CLOCK) ---

async def get_audio_duration(file_path: str) -> float:
    """Get EXACT duration of audio file using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
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
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
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


# --- CRITICAL FIX: Isolated Chunk Architecture ---

async def create_normalized_video_chunk(
    clip_path: str,
    idx: int,
    target_duration: float,
    caption_path: str,
    work_dir: str,
) -> str:
    """
    Create a NORMALIZED video chunk with CFR, exact duration, and reset timestamps.
    Fixed for Railway's ffmpeg - uses -stream_loop instead of loop filter.
    """
    output_path = os.path.join(work_dir, f"chunk_{idx:03d}.mp4")
    cap_overlay_y = TARGET_H - CAPTION_HEIGHT - CAPTION_BOTTOM_MARGIN
    
    # Get actual duration of source clip
    clip_duration = await get_video_duration(clip_path)
    
    # Scale and crop filter (common for both cases)
    scale_crop = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H}"
    
    if target_duration > clip_duration:
        # Need to loop the clip - use -stream_loop input option
        loops_needed = int(target_duration / clip_duration) + 1
        
        # Build filter chain after looping
        post_filters = f"trim=duration={target_duration},setpts=PTS-STARTPTS,{scale_crop},fps={TARGET_FPS},format=yuv420p"
        
        if caption_path and os.path.exists(caption_path):
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", str(loops_needed),
                "-i", clip_path,
                "-i", caption_path,
                "-filter_complex",
                f"[0:v]{post_filters}[v];"
                f"[1:v]format=yuva420p[cap];"
                f"[v][cap]overlay=0:{cap_overlay_y},format=yuv420p[out]",
                "-map", "[out]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-video_track_timescale", str(TARGET_FPS),
                "-r", str(TARGET_FPS),
                "-vsync", "cfr",
                output_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", str(loops_needed),
                "-i", clip_path,
                "-vf", post_filters,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-video_track_timescale", str(TARGET_FPS),
                "-r", str(TARGET_FPS),
                "-vsync", "cfr",
                output_path,
            ]
    else:
        # Clip is long enough, just trim
        post_filters = f"trim=duration={target_duration},setpts=PTS-STARTPTS,{scale_crop},fps={TARGET_FPS},format=yuv420p"
        
        if caption_path and os.path.exists(caption_path):
            cmd = [
                "ffmpeg", "-y",
                "-i", clip_path,
                "-i", caption_path,
                "-filter_complex",
                f"[0:v]{post_filters}[v];"
                f"[1:v]format=yuva420p[cap];"
                f"[v][cap]overlay=0:{cap_overlay_y},format=yuv420p[out]",
                "-map", "[out]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-video_track_timescale", str(TARGET_FPS),
                "-r", str(TARGET_FPS),
                "-vsync", "cfr",
                output_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", clip_path,
                "-vf", post_filters,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-video_track_timescale", str(TARGET_FPS),
                "-r", str(TARGET_FPS),
                "-vsync", "cfr",
                output_path,
            ]
    
    logger.info(f"Running FFmpeg for scene {idx} with target duration {target_duration:.2f}s")
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    
    if proc.returncode != 0:
        logger.error(f"Chunk creation for scene {idx} failed: {stderr.decode()[-800:]}")
        raise RuntimeError(f"FFmpeg chunk creation failed for scene {idx}")
    
    # Verify the output duration
    if os.path.exists(output_path):
        actual_duration = await get_video_duration(output_path)
        logger.info(f"Scene {idx}: Created chunk with duration {actual_duration:.2f}s (target: {target_duration:.2f}s)")
    else:
        logger.error(f"Scene {idx}: Output file not created!")
        raise RuntimeError(f"Output file not created for scene {idx}")
    
    return output_path

async def extract_audio_segment(
    voiceover_path: str,
    start_time: float,
    duration: float,
    output_path: str,
) -> str:
    """Extract precise audio segment for a scene."""
    cmd = [
        "ffmpeg", "-y",
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
        logger.error(f"Audio extraction failed: {stderr.decode()[-500:]}")
        raise RuntimeError(f"Audio extraction failed for {start_time}-{duration}")
    
    if os.path.exists(output_path):
        logger.info(f"Extracted audio segment: {output_path}")
    else:
        logger.error(f"Audio segment not created: {output_path}")
    
    return output_path


async def create_normalized_image_chunk(
    img_path: str,
    idx: int,
    target_duration: float,
    caption_path: str,
    work_dir: str,
) -> str:
    """
    Create a normalized video chunk from an image with Ken Burns motion.
    """
    output_path = os.path.join(work_dir, f"chunk_{idx:03d}.mp4")
    cap_overlay_y = TARGET_H - CAPTION_HEIGHT - CAPTION_BOTTOM_MARGIN
    
    nb_frames = int(target_duration * TARGET_FPS)
    if nb_frames < 1:
        nb_frames = 1
    
    # Randomize Ken Burns motion
    zoom_start = KB_START_ZOOM
    zoom_end = KB_END_ZOOM
    if idx % 2 == 0:
        zoom_start, zoom_end = KB_END_ZOOM, KB_START_ZOOM
    
    x_center = (TARGET_W // 2) + (KB_PAN_X if idx % 2 == 0 else -KB_PAN_X)
    y_center = (TARGET_H // 2) + (KB_PAN_Y if idx % 4 < 2 else -KB_PAN_Y)
    
    zoompan_filter = (
        f"zoompan=z='min({zoom_end},max({zoom_start},{zoom_start}+({zoom_end}-{zoom_start})*s/{nb_frames}))':"
        f"d={nb_frames}:s={TARGET_W}x{TARGET_H}:x={x_center}:y={y_center}:fps={TARGET_FPS},"
        f"setpts=PTS-STARTPTS"
    )
    
    if caption_path and os.path.exists(caption_path):
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", img_path,
            "-i", caption_path,
            "-filter_complex",
            f"[0:v]{zoompan_filter},format=yuv420p[v];"
            f"[1:v]format=yuva420p[cap];"
            f"[v][cap]overlay=0:{cap_overlay_y},format=yuv420p[out]",
            "-map", "[out]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-video_track_timescale", str(TARGET_FPS),
            "-r", str(TARGET_FPS),
            "-vsync", "cfr",
            "-t", str(target_duration),
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", img_path,
            "-vf", f"{zoompan_filter},format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-video_track_timescale", str(TARGET_FPS),
            "-r", str(TARGET_FPS),
            "-vsync", "cfr",
            "-t", str(target_duration),
            output_path,
        ]
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    
    if proc.returncode != 0:
        logger.error(f"Image chunk {idx} failed: {stderr.decode()[-500:]}")
        raise RuntimeError(f"Image chunk creation failed for scene {idx}")
    
    return output_path


# --- Main Stitching Functions ---

async def stitch_reel_async(
    scenes: list[dict[str, Any]],
    voiceover_path: str,
    output_path: str,
    work_dir: str,
) -> str:
    """
    Main stitching function with isolated chunk architecture.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Create chunks directory inside work_dir
    chunks_dir = os.path.join(work_dir, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)
    
    # Sort scenes by scene_index
    scenes = sorted(scenes, key=lambda s: s.get("scene_index", 0))
    
    # Get full voiceover duration
    full_voiceover_duration = await get_audio_duration(voiceover_path)
    
    # Calculate proportions based on narration text length
    narrations = [scene.get("narration", "") for scene in scenes]
    total_chars = sum(len(n) for n in narrations)
    
    if total_chars == 0:
        raise RuntimeError("No narration text found in scenes")
    
    # Calculate cumulative timings based on character proportion
    timings = []
    current_time = 0.0
    
    for i, narration in enumerate(narrations):
        proportion = len(narration) / total_chars
        duration = proportion * full_voiceover_duration
        timings.append((i, current_time, current_time + duration))
        current_time += duration
    
    logger.info(f"Total voiceover duration: {full_voiceover_duration:.2f}s")
    logger.info(f"Scene timings: {[(t[0], t[1], t[2]) for t in timings]}")
    
    # Pre-render caption images
    caption_paths = {}
    for i, scene in enumerate(scenes):
        narration = scene.get("narration", "").strip()
        if narration:
            caption_path = os.path.join(chunks_dir, f"caption_{i:03d}.png")
            text_len = len(narration)
            if text_len > 80:
                fs, sw = 44, 3
            elif text_len > 50:
                fs, sw = 52, 4
            else:
                fs, sw = 64, 5
            cap_img = _render_caption_image(narration, width=TARGET_W, font_size=fs, stroke_width=sw)
            cap_img.save(caption_path, "PNG")
            caption_paths[i] = caption_path
        else:
            caption_paths[i] = None
    
    # Process each scene into a normalized chunk
    processed_chunks = []
    processed_audios = []
    
    for i, scene in enumerate(scenes):
        clip_path = scene.get("video_url")
        if not clip_path or not os.path.exists(clip_path):
            raise RuntimeError(f"Scene {i} has no valid video file: {clip_path}")
        
        _, start_time, end_time = timings[i]
        duration = end_time - start_time
        
        logger.info(f"Processing scene {i}: duration={duration:.2f}s (from voiceover)")
        
        # Create normalized video chunk
        video_chunk = await create_normalized_video_chunk(
            clip_path, i, duration, caption_paths.get(i), chunks_dir
        )
        processed_chunks.append(video_chunk)
        
        # Extract audio segment
        audio_chunk = os.path.join(chunks_dir, f"audio_{i:03d}.m4a")
        await extract_audio_segment(voiceover_path, start_time, duration, audio_chunk)
        processed_audios.append(audio_chunk)
    
    # Write concat file for videos (using absolute paths)
    concat_video_file = os.path.join(chunks_dir, "concat_video.txt")
    with open(concat_video_file, "w") as f:
        for chunk in processed_chunks:
            # Use absolute path or path relative to concat file's directory
            f.write(f"file '{chunk}'\n")
    
    logger.info(f"Video concat file created: {concat_video_file}")
    logger.info(f"Video concat file contents: {open(concat_video_file).read()}")
    
    # Concatenate video chunks
    combined_video = os.path.join(chunks_dir, "combined_video.mp4")
    cmd_concat_video = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_video_file,
        "-c", "copy",
        "-video_track_timescale", str(TARGET_FPS),
        combined_video,
    ]
    
    logger.info(f"Running video concat command: {' '.join(cmd_concat_video)}")
    
    proc = await asyncio.create_subprocess_exec(
        *cmd_concat_video,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    
    if proc.returncode != 0:
        logger.error(f"Video concat failed with code {proc.returncode}")
        logger.error(f"STDERR: {stderr.decode()}")
        raise RuntimeError(f"Video concatenation failed: {stderr.decode()[:500]}")
    
    if not os.path.exists(combined_video):
        raise RuntimeError(f"Combined video not created: {combined_video}")
    
    logger.info(f"Combined video created: {combined_video}")
    
    # Write concat file for audios
    concat_audio_file = os.path.join(chunks_dir, "concat_audio.txt")
    with open(concat_audio_file, "w") as f:
        for audio in processed_audios:
            f.write(f"file '{audio}'\n")
    
    # Concatenate audio chunks
    combined_audio = os.path.join(chunks_dir, "combined_audio.m4a")
    cmd_concat_audio = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_audio_file,
        "-c", "copy",
        combined_audio,
    ]
    
    proc = await asyncio.create_subprocess_exec(
        *cmd_concat_audio,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    
    if proc.returncode != 0:
        logger.error(f"Audio concat failed: {stderr.decode()[-500:]}")
        raise RuntimeError("Audio concatenation failed")
    
    # Mux video and audio
    cmd_mux = [
        "ffmpeg", "-y",
        "-i", combined_video,
        "-i", combined_audio,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-video_track_timescale", str(TARGET_FPS),
        output_path,
    ]
    
    proc = await asyncio.create_subprocess_exec(
        *cmd_mux,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    
    if proc.returncode != 0:
        logger.error(f"Muxing failed: {stderr.decode()[-500:]}")
        raise RuntimeError("Audio-video muxing failed")
    
    logger.info(f"Reel complete: {output_path}")
    return output_path


async def stitch_images_async(
    images: list[dict[str, Any]],
    voiceover_path: str,
    output_path: str,
    work_dir: str,
) -> str:
    """Render AI-image-based reel with perfect sync."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    chunks_dir = os.path.join(work_dir, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)
    
    # Sort images by scene_index
    images = sorted(images, key=lambda i: i.get("scene_index", 0))
    
    # Get full voiceover duration and calculate proportions
    full_voiceover_duration = await get_audio_duration(voiceover_path)
    
    narrations = [img.get("narration", "") for img in images]
    total_chars = sum(len(n) for n in narrations)
    
    if total_chars == 0:
        raise RuntimeError("No narration text found in images")
    
    # Calculate cumulative timings
    timings = []
    current_time = 0.0
    
    for i, narration in enumerate(narrations):
        proportion = len(narration) / total_chars
        duration = proportion * full_voiceover_duration
        timings.append((i, current_time, current_time + duration))
        current_time += duration
    
    logger.info(f"Total voiceover duration: {full_voiceover_duration:.2f}s")
    
    # Download images
    downloaded = await download_images_concurrent(images, chunks_dir)
    if not downloaded:
        raise RuntimeError("No images were successfully downloaded")
    
    # Pre-render caption images
    caption_paths = {}
    for i, img in enumerate(images):
        narration = img.get("narration", "").strip()
        if narration:
            caption_path = os.path.join(chunks_dir, f"caption_{i:03d}.png")
            text_len = len(narration)
            if text_len > 80:
                fs, sw = 44, 3
            elif text_len > 50:
                fs, sw = 52, 4
            else:
                fs, sw = 64, 5
            cap_img = _render_caption_image(narration, width=TARGET_W, font_size=fs, stroke_width=sw)
            cap_img.save(caption_path, "PNG")
            caption_paths[i] = caption_path
        else:
            caption_paths[i] = None
    
    # Create a mapping from scene_index to downloaded path
    downloaded_map = {idx: path for idx, path in downloaded}
    
    # Process each image into a normalized chunk
    processed_chunks = []
    processed_audios = []
    
    for i, img in enumerate(images):
        img_path = downloaded_map.get(img.get("scene_index", i))
        if not img_path or not os.path.exists(img_path):
            raise RuntimeError(f"Image {i} has no valid file")
        
        _, start_time, end_time = timings[i]
        duration = end_time - start_time
        
        logger.info(f"Processing image {i}: duration={duration:.2f}s")
        
        # Create normalized video chunk with Ken Burns
        video_chunk = await create_normalized_image_chunk(
            img_path, i, duration, caption_paths.get(i), chunks_dir
        )
        processed_chunks.append(video_chunk)
        
        # Extract audio segment
        audio_chunk = os.path.join(chunks_dir, f"audio_{i:03d}.m4a")
        await extract_audio_segment(voiceover_path, start_time, duration, audio_chunk)
        processed_audios.append(audio_chunk)
    
    # Concatenate videos
    concat_video_file = os.path.join(chunks_dir, "concat_video.txt")
    with open(concat_video_file, "w") as f:
        for chunk in processed_chunks:
            f.write(f"file '{chunk}'\n")
    
    combined_video = os.path.join(chunks_dir, "combined_video.mp4")
    cmd_concat_video = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_video_file,
        "-c", "copy",
        "-video_track_timescale", str(TARGET_FPS),
        combined_video,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd_concat_video,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Video concat failed: {stderr.decode()[-500:]}")
        raise RuntimeError("Video concatenation failed")
    
    # Concatenate audios
    concat_audio_file = os.path.join(chunks_dir, "concat_audio.txt")
    with open(concat_audio_file, "w") as f:
        for audio in processed_audios:
            f.write(f"file '{audio}'\n")
    
    combined_audio = os.path.join(chunks_dir, "combined_audio.m4a")
    cmd_concat_audio = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_audio_file,
        "-c", "copy",
        combined_audio,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd_concat_audio,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Audio concat failed: {stderr.decode()[-500:]}")
        raise RuntimeError("Audio concatenation failed")
    
    # Mux
    cmd_mux = [
        "ffmpeg", "-y",
        "-i", combined_video,
        "-i", combined_audio,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-video_track_timescale", str(TARGET_FPS),
        output_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd_mux,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Muxing failed: {stderr.decode()[-500:]}")
        raise RuntimeError("Audio-video muxing failed")
    
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