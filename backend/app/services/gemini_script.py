"""Direct Gemini API call for mock-mode script generation.

Used by mock mode to generate topic-specific scripts without going through
Make.com. Same response schema as the Make.com scenario.

If Gemini is unavailable (no key, network error, schema mismatch), we
fall back to a simple keyword-extractor that splits the topic into
search terms — still topic-related, just less polished.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "voiceover_full": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "narration": {"type": "string"},
                    "search_term": {"type": "string"},
                },
                "required": ["narration", "search_term"],
            },
        },
    },
    "required": ["title", "voiceover_full", "scenes"],
}

_SYSTEM_PROMPT = (
    "You are a short-form video scriptwriter for vertical news shorts "
    "(TikTok / Reels / YouTube Shorts). Output ONLY valid JSON. Keep "
    "narration punchy: 1-2 short sentences per scene. No emojis. No "
    "on-screen text. No hashtags. Use ' ... ' as a 250ms pause marker "
    "between scene narrations in voiceover_full."
)

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "in", "on", "at", "to",
    "for", "of", "and", "or", "but", "with", "by", "from", "as", "this",
    "that", "it", "be", "been", "have", "has", "had", "do", "does", "did",
    "will", "would", "should", "can", "could", "may", "might", "must",
    "shall", "i", "you", "he", "she", "we", "they", "me", "him", "her",
    "us", "them", "my", "your", "his", "its", "our", "their",
}


def generate_script_with_gemini(
    topic: str, scene_count: int, voice: str
) -> Optional[dict]:
    """Call Gemini directly and return a parsed script dict, or None on failure."""
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set — Gemini call skipped")
        return None

    user_prompt = (
        f"Topic: {topic}\n"
        f"Number of scenes: {scene_count}\n"
        f"Voice: {voice}\n"
        f"\n"
        f"Produce a short-form vertical video script. Output strict JSON with:\n"
        f"- title (max 60 chars, clickable)\n"
        f"- voiceover_full (full spoken script as one string; use ' ... ' "
        f"as 250ms pause marker between scene narrations)\n"
        f"- scenes (array of exactly {scene_count} items, each with: "
        f"narration (1-2 short sentences, max 25 words) and search_term "
        f"(1-3 lowercase keywords for stock video search, e.g. "
        f"'artificial intelligence'))"
    )

    payload = {
        "systemInstruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": _RESPONSE_SCHEMA,
        },
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{_GEMINI_URL}?key={settings.gemini_api_key}",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        r.raise_for_status()
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        # Sanity check the shape
        if not (isinstance(parsed, dict) and "scenes" in parsed and "title" in parsed):
            logger.warning("Gemini returned unexpected shape: %s", list(parsed.keys()))
            return None
        return parsed
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.warning("Gemini call failed for topic %r: %s", topic, exc)
        return None


def fallback_script(topic: str, scene_count: int) -> dict:
    """Topic-related script built from keyword extraction. Used when Gemini fails."""
    words = re.findall(r"\w+", topic.lower())
    keywords = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    if not keywords:
        keywords = ["news", "update"]
    # Repeat keywords if topic has fewer than scene_count words
    while len(keywords) < scene_count:
        keywords.append(keywords[0])
    keywords = keywords[:scene_count]

    # Vary the narration template per scene
    templates = [
        "Here's what's happening with {kw}.",
        "This is why {kw} matters right now.",
        "More updates on {kw} coming up.",
        "That's the latest on {kw}.",
        "Stay tuned for more on {kw}.",
    ]

    narrations = []
    for i, kw in enumerate(keywords):
        tpl = templates[i % len(templates)]
        narrations.append(tpl.format(kw=kw))

    return {
        "title": f"Reel: {topic}",
        "voiceover_full": " ... ".join(narrations),
        "scenes": [
            {"narration": narrations[i], "search_term": kw}
            for i, kw in enumerate(keywords)
        ],
    }
