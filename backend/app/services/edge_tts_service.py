"""edge-tts wrapper — synthesizes voiceover to MP3."""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

import edge_tts

logger = logging.getLogger(__name__)

# The Gemini prompt asks for ' ... ' as a pause marker; we expand it to
# a sentence boundary for natural prosody, since edge-tts doesn't have a
# direct SSML-break shortcut in its plain text API.
_PAUSE_RE = re.compile(r"\s*\.\.\.\s*")


def _normalize_pauses(text: str) -> str:
    return _PAUSE_RE.sub(". ", text).strip()


async def synthesize_voiceover(
    voiceover_text: str,
    output_path: str,
    voice: str = "en-US-GuyNeural",
) -> str:
    """Synthesize speech from text using edge-tts. Writes MP3 to output_path."""
    cleaned = _normalize_pauses(voiceover_text)
    if not cleaned:
        raise ValueError("voiceover_text is empty")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(cleaned, voice=voice)
    await communicate.save(output_path)
    logger.info("Wrote voiceover MP3 (%d chars) → %s", len(cleaned), output_path)
    return output_path


def run_synthesize_sync(
    voiceover_text: str,
    output_path: str,
    voice: str = "en-US-GuyNeural",
) -> str:
    """Synchronous wrapper for use inside FastAPI BackgroundTasks."""
    return asyncio.run(
        synthesize_voiceover(voiceover_text, output_path, voice=voice)
    )
