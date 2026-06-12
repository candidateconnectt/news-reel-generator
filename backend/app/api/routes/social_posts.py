"""Social post generation routes — DeepSeek as creative director. Supabase only."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from textwrap import wrap
from typing import Optional, List as ListType

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import settings
from app.models.social_post import SocialPostCampaign

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class BrandCoreInput(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    industry: str = Field(default="", max_length=200)
    primary_color: str = Field(default="#0057FF", pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    accent_color: str = Field(default="#FF6B35", pattern=r"^#[0-9A-Fa-f]{6}$")
    font_style: str = Field(default="Inter", max_length=50)
    brand_tone: str = Field(default="Professional", max_length=100)
    visual_style: str = Field(default="Modern SaaS", max_length=200)
    tagline: str = Field(default="", max_length=200)
    website_url: str = Field(default="", max_length=200)
    target_audience: str = Field(default="", max_length=500)
    key_products: ListType[str] = Field(default_factory=list)
    brand_values: ListType[str] = Field(default_factory=list)


class CampaignGoalInput(BaseModel):
    objective: str = Field(default="brand_awareness", max_length=100)
    key_messages: ListType[str] = Field(default_factory=list)
    campaign_tone: str = Field(default="Professional", max_length=100)
    target_platform: str = Field(default="LinkedIn", max_length=50)
    number_of_posts: int = Field(default=8, ge=1, le=20)


class SocialPostCreateRequest(BaseModel):
    brand: BrandCoreInput
    campaign: CampaignGoalInput
    image_provider: str = Field(default="minimax", pattern="^(gemini|openai|minimax|openrouter)$")
    key_choice: str = Field(default="primary", pattern="^(primary|secondary)$")


class SocialPostResponse(BaseModel):
    campaign_id: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class BrandCore:
    company_name: str
    industry: str
    primary_color: str
    secondary_color: str
    accent_color: str
    font_style: str
    brand_tone: str
    visual_style: str
    tagline: str
    website_url: str
    target_audience: str
    key_products: ListType[str]
    brand_values: ListType[str]


@dataclass
class CampaignGoal:
    objective: str
    key_messages: ListType[str]
    campaign_tone: str
    target_platform: str
    number_of_posts: int


@dataclass
class GeneratedPost:
    id: int
    content_type: str
    headline: str
    supporting_text: str
    cta: str
    visual_description: str
    mood: str
    layout_strategy: str
    background_prompt: str
    features: ListType[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    quote: str = ""
    background_image_bytes: Optional[bytes] = None
    final_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Supabase Helper
# ---------------------------------------------------------------------------

def get_supabase_client():
    """Get Supabase client"""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None
    try:
        from supabase import create_client
        return create_client(settings.supabase_url, settings.supabase_service_role_key)
    except Exception as e:
        logger.error("Failed to create Supabase client: %s", e)
        return None


async def upload_bytes_to_supabase(
    image_bytes: bytes,
    campaign_id: str,
    filename: str,
    content_type: str = "image/jpeg"
) -> Optional[str]:
    """Upload image bytes directly to Supabase Storage, return public URL"""
    client = get_supabase_client()
    if not client:
        logger.error("Supabase client not available")
        return None

    try:
        bucket = settings.supabase_bucket or "social-posts"
        file_path = f"{campaign_id}/{filename}"

        # Upload
        client.storage.from_(bucket).upload(file_path, image_bytes, {"content-type": content_type})

        # Get public URL
        public_url = client.storage.from_(bucket).get_public_url(file_path)
        logger.info("Uploaded to Supabase: %s", public_url)
        return public_url

    except Exception as e:
        logger.error("Supabase upload failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Helper: Get API Key based on choice
# ---------------------------------------------------------------------------

def _get_gemini_key(choice: str = "primary") -> tuple[str, str]:
    if choice == "secondary" and settings.gemini_api_key2:
        return settings.gemini_api_key2, "secondary"
    return settings.gemini_api_key, "primary"


def _get_openrouter_key(choice: str = "primary") -> tuple[str, str]:
    if choice == "secondary" and settings.openai_api_key2:
        return settings.openai_api_key2, "secondary"
    return settings.openai_api_key, "primary"


# ---------------------------------------------------------------------------
# DeepSeek API
# ---------------------------------------------------------------------------

async def deepseek_call(system: str, user: str, max_tokens: int = 800) -> str:
    if not settings.deepseek_api_key:
        raise HTTPException(status_code=500, detail="DEEPSEEK_API_KEY not configured")

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "max_tokens": max_tokens,
                "temperature": 0.8,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
        )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"DeepSeek error: {data['error']}")
    return data["choices"][0]["message"]["content"].strip()


def parse_json(raw: str) -> dict:
    """Parse JSON object from LLM response with robust error handling"""
    try:
        clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        return json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r'\{[^{}]*\}', clean, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        # Fix common JSON issues
        cleaned = clean.replace("'", '"')
        cleaned = re.sub(r'(\w+):', r'"\1":', cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            raise RuntimeError(f"Could not parse JSON from response: {raw[:200]}")


def parse_json_array(raw: str) -> list:
    """Parse JSON array from LLM response with robust error handling"""
    try:
        clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        return json.loads(clean)
    except json.JSONDecodeError:
        # Try to find array in the text
        match = re.search(r'\[[^\[\]]*\]', clean, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
        # Try extracting from potential JSON object wrapping
        match = re.search(r'"posts"\s*:\s*(\[[^\[\]]*\])', clean, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # Last resort fix
        cleaned = clean.replace("'", '"')
        cleaned = re.sub(r'(\w+):', r'"\1":', cleaned)
        try:
            result = json.loads(cleaned)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        raise RuntimeError(f"Could not parse JSON array from response: {raw[:200]}")


async def research_company_context(brand: BrandCore, goal: CampaignGoal) -> dict:
    system = """You are a Senior Brand Strategist. Analyze the company and campaign goal.
    Think like a creative director preparing for a campaign.
    Return your analysis as a JSON object."""

    user = f"""
COMPANY: {brand.company_name}
INDUSTRY: {brand.industry}
BRAND TONE: {brand.brand_tone}
VISUAL STYLE: {brand.visual_style}
TAGLINE: {brand.tagline}
TARGET AUDIENCE: {brand.target_audience}
KEY PRODUCTS: {', '.join(brand.key_products)}
BRAND VALUES: {', '.join(brand.brand_values)}

CAMPAIGN OBJECTIVE: {goal.objective}
KEY MESSAGES: {', '.join(goal.key_messages)}
CAMPAIGN TONE: {goal.campaign_tone}
TARGET PLATFORM: {goal.target_platform}

Analyze this company and provide:
{{
  "company_voice": "How this brand speaks (2-3 sentences)",
  "emotional_triggers": ["List of 3-4 emotions that resonate with their audience"],
  "visual_themes": ["List of 3-4 visual themes that represent the brand"],
  "content_opportunities": ["List of 3-4 angles/messages that would work well"],
  "differentiators": "What makes this brand unique"
}}
"""
    raw = await deepseek_call(system, user, max_tokens=600)
    return parse_json(raw)


async def generate_post_concepts(brand: BrandCore, goal: CampaignGoal, context: dict, num_posts: int) -> ListType[dict]:
    system = """You are a Senior Creative Director and Copywriter.
    Generate UNIQUE, ENGAGING social media post concepts.
    Each post should have a different angle, emotion, and visual approach.
    Return ONLY valid JSON array."""

    user = f"""
CAMPAIGN CONTEXT:
Company: {brand.company_name}
Industry: {brand.industry}
Brand Values: {', '.join(brand.brand_values)}
Key Products: {', '.join(brand.key_products)}
Target Audience: {brand.target_audience}

Campaign Goal: {goal.objective}
Key Messages: {', '.join(goal.key_messages)}
Campaign Tone: {goal.campaign_tone}
Platform: {goal.target_platform}

Company Voice: {context.get('company_voice', 'Professional yet approachable')}
Emotional Triggers: {context.get('emotional_triggers', ['trust', 'innovation'])}
Visual Themes: {context.get('visual_themes', ['modern', 'clean'])}
Differentiators: {context.get('differentiators', 'Innovative transit technology')}

Generate {num_posts} UNIQUE post concepts. Each post should:
- Have a different content type (hiring, announcement, educational, inspirational, product, case study, testimonial, industry_insight)
- Have a unique angle and emotion
- Be appropriate for {goal.target_platform}
- Include a compelling headline (max 40 chars)
- Include 1-2 sentence supporting text
- Include a clear CTA
- Suggest a visual direction (1 sentence)

Return as JSON array:
[
  {{
    "content_type": "e.g., announcement, educational, inspirational, product, hiring, case_study",
    "headline": "Short, punchy headline",
    "supporting_text": "Engaging supporting copy",
    "cta": "Action button text",
    "visual_theme": "From the visual themes above",
    "emotional_angle": "Primary emotion this post should evoke"
  }}
]
"""
    raw = await deepseek_call(system, user, max_tokens=2000)
    return parse_json_array(raw)


async def enrich_post_content(post_concept: dict, brand: BrandCore, goal: CampaignGoal) -> dict:
    system = """You are a Content Strategist. Enhance this post with specific details.
    Add relevant statistics, features, or a customer quote.
    Return ONLY valid JSON."""

    user = f"""
Brand: {brand.company_name}
Industry: {brand.industry}
Key Products: {', '.join(brand.key_products)}
Campaign Goal: {goal.objective}

POST CONCEPT:
Content Type: {post_concept.get('content_type')}
Headline: {post_concept.get('headline')}
Supporting Text: {post_concept.get('supporting_text')}
Emotional Angle: {post_concept.get('emotional_angle')}

Enhance this post by adding:
{{
  "enhanced_headline": "Refined headline (if needed)",
  "enhanced_supporting_text": "Expanded supporting text with details",
  "features": ["List of 2-4 relevant features or benefits"],
  "stats": {{"key1": "value1", "key2": "value2"}} (add realistic industry stats if relevant),
  "quote": "Optional customer or expert quote (30-40 words)"
}}
"""
    raw = await deepseek_call(system, user, max_tokens=800)
    enriched = parse_json(raw)

    return {
        "content_type": post_concept.get('content_type'),
        "headline": enriched.get('enhanced_headline', post_concept.get('headline')),
        "supporting_text": enriched.get('enhanced_supporting_text', post_concept.get('supporting_text')),
        "cta": post_concept.get('cta'),
        "features": enriched.get('features', []),
        "stats": enriched.get('stats', {}),
        "quote": enriched.get('quote', ''),
        "visual_theme": post_concept.get('visual_theme'),
        "emotional_angle": post_concept.get('emotional_angle')
    }


async def determine_layout_strategy(post: dict, brand: BrandCore) -> dict:
    system = """You are a Senior Graphic Designer.
    Based on the content, decide the best layout strategy.
    Return ONLY valid JSON."""

    user = f"""
Content Type: {post.get('content_type')}
Headline: {post.get('headline')}
Features: {len(post.get('features', []))} features
Has Stats: {bool(post.get('stats'))}
Has Quote: {bool(post.get('quote'))}
Brand Visual Style: {brand.visual_style}

Choose layout strategy:
- hero_centered: Big central message (announcements, celebrations)
- feature_list: Bullet points (product features, hiring benefits)
- stats_dense: Numbers prominent (achievements, growth metrics)
- split_vertical: Image left, text right (balanced storytelling)
- quote_centered: Testimonial style
- educational: Problem-solution format

Return JSON:
{{
  "layout_strategy": "chosen strategy",
  "visual_hierarchy": "text_dominant OR image_dominant OR balanced",
  "headline_position": "top OR center OR bottom",
  "content_density": "minimal OR standard OR dense",
  "background_role": "atmospheric OR contextual OR abstract"
}}
"""
    raw = await deepseek_call(system, user, max_tokens=300)
    return parse_json(raw)


async def create_visual_bible(post: dict, layout: dict, brand: BrandCore, goal: CampaignGoal) -> dict:
    system = """You are a Creative Director specializing in brand-consistent design.
    Create a unique visual treatment for this specific post.
    Return ONLY valid JSON."""

    user = f"""
BRAND: {brand.company_name}
Primary Color: {brand.primary_color}
Accent Color: {brand.accent_color}
Font Style: {brand.font_style}
Visual Style: {brand.visual_style}

POST:
Content Type: {post.get('content_type')}
Headline: {post.get('headline')}
Emotional Angle: {post.get('emotional_angle')}
Features: {', '.join(post.get('features', [])[:2])}

LAYOUT STRATEGY: {layout.get('layout_strategy')}
BACKGROUND ROLE: {layout.get('background_role')}

Create Visual Bible:
{{
  "mood": "Emotional atmosphere (3-4 words)",
  "color_palette": ["#hex1", "#hex2", "#hex3"],
  "typography": "Font weights and sizes",
  "composition": "How elements are arranged",
  "lighting": "Lighting style for background",
  "texture": "Texture or pattern overlay",
  "background_description": "DETAILED scene description for AI image generation"
}}

RULES:
- ALWAYS include {brand.primary_color} in palette
- NO TEXT in the background description
"""
    raw = await deepseek_call(system, user, max_tokens=600)
    return parse_json(raw)


async def generate_background_prompt(post: dict, bible: dict, layout: dict, brand: BrandCore) -> str:
    system = """You are a Prompt Engineer for AI image generation.
    Create a detailed, cinematic prompt for the background image.
    Return ONLY the prompt string."""

    user = f"""
Brand: {brand.company_name}
Industry: {brand.industry}
Content Type: {post.get('content_type')}
Mood: {bible.get('mood')}
Visual Theme: {post.get('visual_theme')}
Colors: {', '.join(bible.get('color_palette', []))}
Layout Strategy: {layout.get('layout_strategy')}
Scene Description: {bible.get('background_description')}

Create an image generation prompt (max 150 words):
- High quality, cinematic, {brand.visual_style} style
- Leave space for text overlay
- Match the mood: {bible.get('mood')}
- Use colors from palette
- NO text, NO UI elements, NO people reading/holding phones
"""
    return await deepseek_call(system, user, max_tokens=300)


# ---------------------------------------------------------------------------
# Image Generation
# ---------------------------------------------------------------------------

async def generate_image_with_provider(provider: str, prompt: str, key_choice: str = "primary") -> tuple[bytes, str]:
    if provider == "gemini":
        return await _gemini_via_http(prompt, key_choice)
    elif provider == "openai":
        return await _openai_dalle(prompt), "primary"
    elif provider == "minimax":
        return await _minimax_http(prompt), "primary"
    elif provider == "openrouter":
        return await _openrouter_http(prompt, key_choice), key_choice
    raise RuntimeError(f"Unknown provider: {provider}")


async def _gemini_via_http(prompt: str, key_choice: str = "primary") -> bytes:
    api_key, key_label = _get_gemini_key(key_choice)
    if not api_key:
        raise RuntimeError(f"Gemini {key_label} API key not configured")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]}
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            for part in parts:
                if "inlineData" in part:
                    return base64.b64decode(part["inlineData"]["data"])

    raise RuntimeError("No image data in Gemini response")


async def _openai_dalle(prompt: str) -> bytes:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
            json={"model": "dall-e-3", "prompt": prompt, "size": "1024x1024", "quality": "standard", "n": 1}
        )
        if resp.status_code != 200:
            raise RuntimeError(f"DALL-E error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        items = data.get("data", [])
        if items and items[0].get("b64_json"):
            return base64.b64decode(items[0]["b64_json"])
        elif items and items[0].get("url"):
            img_resp = await client.get(items[0]["url"])
            img_resp.raise_for_status()
            return img_resp.content

    raise RuntimeError("No image data from DALL-E")


async def _minimax_http(prompt: str) -> bytes:
    if not settings.minimax_api_key:
        raise RuntimeError("MINIMAX_API_KEY not configured")

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.minimax.io/v1/image_generation",
            headers={"Authorization": f"Bearer {settings.minimax_api_key}", "Content-Type": "application/json"},
            json={"model": "image-01", "prompt": prompt, "aspect_ratio": "1:1", "response_format": "url"}
        )
        if resp.status_code != 200:
            raise RuntimeError(f"MiniMax error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        base_resp = data.get("base_resp", {})
        status_code = base_resp.get("status_code", 0)
        if status_code != 0:
            raise RuntimeError(f"MiniMax API error: {base_resp.get('status_msg', 'unknown')}")

        urls = data.get("data", {}).get("image_urls", [])
        if not urls:
            raise RuntimeError("No image URL in MiniMax response")

        img_resp = await client.get(urls[0])
        img_resp.raise_for_status()
        return img_resp.content


async def _openrouter_http(prompt: str, key_choice: str = "primary") -> bytes:
    api_key, key_label = _get_openrouter_key(key_choice)
    if not api_key:
        raise RuntimeError(f"OpenRouter {key_label} API key not configured")

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "google/gemini-2.0-flash",
                "messages": [{"role": "user", "content": prompt}],
                "modalities": ["image"]
            }
        )
        if resp.status_code != 200:
            raise RuntimeError(f"OpenRouter error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        choices = data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            images = message.get("images", [])
            for img in images:
                if isinstance(img, dict):
                    url = img.get("image_url", {}).get("url", "")
                    if url.startswith("data:image"):
                        return base64.b64decode(url.split(",")[1])
                    if url:
                        img_resp = await client.get(url)
                        img_resp.raise_for_status()
                        return img_resp.content

    raise RuntimeError("No image data from OpenRouter")


# ---------------------------------------------------------------------------
# Professional Renderer (renders to bytes, no file save)
# ---------------------------------------------------------------------------

def hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates_bold = [
        "C:/Windows/Fonts/Inter-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    candidates_regular = [
        "C:/Windows/Fonts/Inter-Regular.ttf", "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    candidates = candidates_bold if bold else candidates_regular
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def render_professional_post_to_bytes(
    bg_bytes: bytes,
    post: GeneratedPost,
    brand: BrandCore,
    layout_strategy: str,
    canvas_size: int = 1080,
) -> bytes:
    """Render final post with consistent brand elements, return JPEG bytes"""
    bg = Image.open(BytesIO(bg_bytes)).convert("RGBA")
    bg = bg.resize((canvas_size, canvas_size), Image.LANCZOS)

    primary_rgb = hex_to_rgb(brand.primary_color)
    accent_rgb = hex_to_rgb(brand.accent_color)
    white = hex_to_rgb(brand.secondary_color)

    # TOP BRAND BAR - slightly taller for safety
    top_bar_h = int(canvas_size * 0.10)
    top_bar = Image.new("RGBA", (canvas_size, top_bar_h), (*primary_rgb, 240))
    bg.paste(top_bar, (0, 0), mask=top_bar)

    draw = ImageDraw.Draw(bg)

    # Company name - reduced font size
    brand_font = get_font(int(canvas_size * 0.030), bold=True)
    brand_x = int(canvas_size * 0.05)
    brand_y = int(top_bar_h * 0.30)
    draw.text((brand_x, brand_y), brand.company_name.upper(), font=brand_font, fill=white)

    # Tagline
    if brand.tagline:
        tag_font = get_font(int(canvas_size * 0.016))
        tag_w = draw.textlength(brand.tagline, font=tag_font)
        draw.text(
            (canvas_size - tag_w - int(canvas_size * 0.05), brand_y + 4),
            brand.tagline, font=tag_font, fill=(*white, 200)
        )

    # BOTTOM FOOTER - slightly taller for safety
    footer_h = int(canvas_size * 0.07)
    footer_y = canvas_size - footer_h
    footer_bg = Image.new("RGBA", (canvas_size, footer_h), (*primary_rgb, 230))
    bg.paste(footer_bg, (0, footer_y), mask=footer_bg)

    footer_font = get_font(int(canvas_size * 0.020), bold=True)
    footer_w = draw.textlength(brand.website_url, font=footer_font)
    draw.text(
        ((canvas_size - footer_w) // 2, footer_y + int(footer_h * 0.30)),
        brand.website_url, font=footer_font, fill=white
    )

    # CONTENT ZONE - more padding from edges
    content_top = top_bar_h + int(canvas_size * 0.05)
    content_bottom = footer_y - int(canvas_size * 0.05)
    content_height = content_bottom - content_top
    pad_x = int(canvas_size * 0.06)
    max_text_width = canvas_size - pad_x * 2

    # Semi-transparent overlay
    overlay = Image.new("RGBA", (canvas_size, content_height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    if layout_strategy in ["hero_centered", "announcement"]:
        for y in range(content_height):
            alpha = int(100 * (1 - y / content_height * 0.5))
            overlay_draw.line([(0, y), (canvas_size, y)], fill=(0, 0, 0, alpha))
    else:
        overlay_draw.rectangle([(0, 0), (canvas_size, content_height)], fill=(0, 0, 0, 120))

    bg.paste(overlay, (0, content_top), mask=overlay)

    # RENDER CONTENT - with strict bounds enforcement
    text_y = content_top + int(canvas_size * 0.04)
    line_height = int(canvas_size * 0.038)

    def fit_text(text: str, font, max_w: int, min_size: int = int(canvas_size * 0.03)) -> tuple:
        """Returns (font, lines) with text that fits within max_w"""
        size = int(canvas_size * 0.055)
        while size >= min_size:
            f = get_font(size, bold=True)
            if draw.textlength(text, font=f) <= max_w:
                return f, wrap(text, width=999)
            size -= 2
        # Fallback: wrap aggressively
        f = get_font(min_size, bold=True)
        return f, wrap(text, width=20)

    def truncate_to_fit(text: str, font, max_w: int) -> str:
        """Truncate text with ellipsis if it exceeds max_w"""
        w = draw.textlength(text, font=font)
        if w <= max_w:
            return text
        # Binary search for max chars
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if draw.textlength(text[:mid] + "...", font=font) <= max_w:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo] + "..."

    if layout_strategy == "hero_centered":
        headline_font, _ = fit_text(post.headline, None, max_text_width)
        headline_w = draw.textlength(post.headline, font=headline_font)
        headline_x = max(pad_x, (canvas_size - headline_w) // 2)
        draw.text((headline_x, text_y), post.headline, font=headline_font, fill=white)
        text_y += int(canvas_size * 0.09)

        support_font = get_font(int(canvas_size * 0.026))
        wrapped = wrap(post.supporting_text, width=28)
        for line in wrapped[:2]:
            line = truncate_to_fit(line, support_font, max_text_width)
            line_w = draw.textlength(line, font=support_font)
            line_x = max(pad_x, (canvas_size - line_w) // 2)
            draw.text((line_x, text_y), line, font=support_font, fill=(*white, 220))
            text_y += line_height

    elif layout_strategy == "feature_list":
        headline_font, _ = fit_text(post.headline, None, max_text_width)
        draw.text((pad_x, text_y), post.headline, font=headline_font, fill=white)
        text_y += int(canvas_size * 0.07)

        bullet_font = get_font(int(canvas_size * 0.024))
        features = post.features if post.features else [post.supporting_text[:50]]
        for i, feature in enumerate(features[:4]):
            bullet_text = f"• {feature}"
            bullet_text = truncate_to_fit(bullet_text, bullet_font, max_text_width)
            draw.text((pad_x, text_y), bullet_text, font=bullet_font, fill=(*white, 220))
            text_y += line_height

    elif layout_strategy == "stats_dense":
        headline_font, _ = fit_text(post.headline, None, max_text_width)
        draw.text((pad_x, text_y), post.headline, font=headline_font, fill=white)
        text_y += int(canvas_size * 0.07)

        if post.stats:
            stat_font = get_font(int(canvas_size * 0.038), bold=True)
            stat_desc_font = get_font(int(canvas_size * 0.016))
            col_width = (canvas_size - pad_x * 2) // 2
            stats_items = list(post.stats.items())[:4]
            for i, (key, value) in enumerate(stats_items):
                col = i % 2
                row = i // 2
                stat_x = pad_x + (col * col_width)
                stat_y = text_y + (row * int(canvas_size * 0.09))
                value_text = truncate_to_fit(str(value), stat_font, col_width - int(canvas_size * 0.02))
                key_text = truncate_to_fit(key.replace('_', ' ').title(), stat_desc_font, col_width - int(canvas_size * 0.02))
                draw.text((stat_x, stat_y), value_text, font=stat_font, fill=accent_rgb)
                draw.text((stat_x, stat_y + int(canvas_size * 0.032)), key_text, font=stat_desc_font, fill=(*white, 200))
            text_y += int(canvas_size * 0.19)
    else:
        # Standard layout - left-aligned, strict bounds
        headline_font, _ = fit_text(post.headline, None, max_text_width)
        wrapped_headline = wrap(post.headline, width=25)
        for line in wrapped_headline[:2]:
            line = truncate_to_fit(line, headline_font, max_text_width)
            draw.text((pad_x, text_y), line, font=headline_font, fill=white)
            text_y += int(canvas_size * 0.065)

        support_font = get_font(int(canvas_size * 0.024))
        wrapped = wrap(post.supporting_text, width=30)
        for line in wrapped[:2]:
            line = truncate_to_fit(line, support_font, max_text_width)
            draw.text((pad_x, text_y), line, font=support_font, fill=(*white, 220))
            text_y += line_height

    # CTA BUTTON - always constrained to content bounds
    cta_font = get_font(int(canvas_size * 0.022), bold=True)
    cta_text = truncate_to_fit(post.cta, cta_font, max_text_width - int(canvas_size * 0.06))
    cta_w = int(draw.textlength(cta_text, font=cta_font)) + int(canvas_size * 0.05)
    cta_h = int(canvas_size * 0.050)

    cta_x = pad_x
    cta_y = content_bottom - cta_h - int(canvas_size * 0.03)

    if layout_strategy == "hero_centered":
        cta_x = max(pad_x, (canvas_size - cta_w) // 2)

    # Ensure CTA button doesn't overflow right edge
    if cta_x + cta_w > canvas_size - pad_x:
        cta_x = canvas_size - pad_x - cta_w

    cta_rect = [cta_x, cta_y, cta_x + cta_w, cta_y + cta_h]
    draw.rounded_rectangle(cta_rect, radius=int(cta_h * 0.4), fill=accent_rgb)
    draw.text(
        (cta_x + int(canvas_size * 0.025), cta_y + int(cta_h * 0.2)),
        cta_text, font=cta_font, fill=white
    )

    final = bg.convert("RGB")
    output = BytesIO()
    final.save(output, "JPEG", quality=92)
    return output.getvalue()


# ---------------------------------------------------------------------------
# Main Generation Pipeline
# ---------------------------------------------------------------------------

async def run_campaign(brand: BrandCore, goal: CampaignGoal, image_provider: str, key_choice: str) -> ListType[tuple]:
    """Full campaign generation. Returns list of (GeneratedPost, key_used) tuples"""
    logger.info("Starting social post generation for %s", brand.company_name)

    # Step 1: Research
    context = await research_company_context(brand, goal)

    # Step 2: Generate post concepts
    concepts = await generate_post_concepts(brand, goal, context, goal.number_of_posts)

    # Step 3: Enrich posts
    enriched_posts = []
    for concept in concepts:
        enriched = await enrich_post_content(concept, brand, goal)
        enriched_posts.append(enriched)

    # Step 4: Design visual strategy
    posts_with_visuals = []
    for post in enriched_posts:
        layout = await determine_layout_strategy(post, brand)
        bible = await create_visual_bible(post, layout, brand, goal)
        bg_prompt = await generate_background_prompt(post, bible, layout, brand)

        posts_with_visuals.append({
            **post,
            "layout_strategy": layout.get('layout_strategy'),
            "bible": bible,
            "background_prompt": bg_prompt
        })

    # Step 5: Generate images
    generated_posts = []
    for i, post_data in enumerate(posts_with_visuals, 1):
        try:
            logger.info("Generating image for post %d: %s", i, post_data.get('headline')[:40])
            image_bytes, key_used = await generate_image_with_provider(image_provider, post_data['background_prompt'], key_choice)

            generated_post = GeneratedPost(
                id=i,
                content_type=post_data.get('content_type'),
                headline=post_data.get('headline'),
                supporting_text=post_data.get('supporting_text'),
                cta=post_data.get('cta'),
                visual_description=post_data.get('visual_theme', ''),
                mood=post_data.get('bible', {}).get('mood', ''),
                layout_strategy=post_data.get('layout_strategy', 'standard'),
                background_prompt=post_data['background_prompt'],
                features=post_data.get('features', []),
                stats=post_data.get('stats', {}),
                quote=post_data.get('quote', ''),
                background_image_bytes=image_bytes
            )
            generated_posts.append((generated_post, key_used))
            logger.info("Generated post %d: %s", i, post_data.get('headline')[:40])

        except Exception as e:
            logger.error("Failed to generate post %d: %s", i, e)
            continue

    return generated_posts


async def process_and_upload_posts(
    posts: ListType[tuple],
    brand: BrandCore,
    campaign_id: str
) -> ListType[dict]:
    """Render posts and upload directly to Supabase - NO local storage"""
    rendered_posts = []

    for post, key_used in posts:
        if not post.background_image_bytes:
            continue

        try:
            # Generate unique filename
            unique_id = uuid.uuid4().hex[:8]
            safe_name = re.sub(r'[^a-zA-Z0-9]', '_', post.headline.lower())[:30]
            filename = f"{post.id:02d}_{post.content_type}_{safe_name}_{unique_id}.jpg"

            # Render with text overlays
            rendered_bytes = render_professional_post_to_bytes(
                post.background_image_bytes,
                post,
                brand,
                post.layout_strategy
            )

            # Upload directly to Supabase
            public_url = await upload_bytes_to_supabase(rendered_bytes, campaign_id, filename)

            if public_url:
                post.final_url = public_url
                rendered_posts.append({
                    "id": post.id,
                    "content_type": post.content_type,
                    "headline": post.headline,
                    "supporting_text": post.supporting_text,
                    "cta": post.cta,
                    "visual_description": post.visual_description,
                    "mood": post.mood,
                    "layout_strategy": post.layout_strategy,
                    "final_url": public_url,  # This is the Supabase download URL
                    "key_used": key_used,
                })
                logger.info("Uploaded to Supabase: %s", filename)
            else:
                logger.error("Failed to upload post %d to Supabase", post.id)

        except Exception as e:
            logger.error("Failed to process post %d: %s", post.id, e)
            continue

    return rendered_posts


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/social-posts", response_model=SocialPostResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_social_post_campaign(
    request: SocialPostCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Generate social media posts. All images saved to Supabase only."""

    # Create campaign record in database
    campaign = SocialPostCampaign(
        company_name=request.brand.company_name,
        industry=request.brand.industry,
        primary_color=request.brand.primary_color,
        secondary_color=request.brand.secondary_color,
        accent_color=request.brand.accent_color,
        font_style=request.brand.font_style,
        brand_tone=request.brand.brand_tone,
        visual_style=request.brand.visual_style,
        tagline=request.brand.tagline,
        website_url=request.brand.website_url or f"WWW.{request.brand.company_name.upper().replace(' ', '')}.COM",
        target_audience=request.brand.target_audience,
        key_products=request.brand.key_products,
        brand_values=request.brand.brand_values,
        objective=request.campaign.objective,
        key_messages=request.campaign.key_messages or ["Brand awareness"],
        campaign_tone=request.campaign.campaign_tone,
        target_platform=request.campaign.target_platform,
        number_of_posts=request.campaign.number_of_posts,
        image_provider=request.image_provider,
        key_used=request.key_choice,
        status="processing",
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    # Run generation in background
    background_tasks.add_task(run_social_post_campaign_background, campaign.id, request, db)

    return SocialPostResponse(
        campaign_id=campaign.id,
        status="processing",
        message=f"Campaign started for {campaign.company_name}. Generating {campaign.number_of_posts} posts..."
    )


async def run_social_post_campaign_background(campaign_id: str, request: SocialPostCreateRequest, db: Session):
    """Background task to run social post generation - uploads to Supabase only"""
    campaign = db.query(SocialPostCampaign).filter(SocialPostCampaign.id == campaign_id).first()
    if not campaign:
        logger.error("Campaign %s not found", campaign_id)
        return

    try:
        brand = BrandCore(
            company_name=request.brand.company_name,
            industry=request.brand.industry,
            primary_color=request.brand.primary_color,
            secondary_color=request.brand.secondary_color,
            accent_color=request.brand.accent_color,
            font_style=request.brand.font_style,
            brand_tone=request.brand.brand_tone,
            visual_style=request.brand.visual_style,
            tagline=request.brand.tagline,
            website_url=campaign.website_url,
            target_audience=request.brand.target_audience,
            key_products=request.brand.key_products,
            brand_values=request.brand.brand_values,
        )

        campaign_goal = CampaignGoal(
            objective=request.campaign.objective,
            key_messages=request.campaign.key_messages or ["Brand awareness"],
            campaign_tone=request.campaign.campaign_tone,
            target_platform=request.campaign.target_platform,
            number_of_posts=request.campaign.number_of_posts,
        )

        # Generate posts
        generated_posts = await run_campaign(brand, campaign_goal, request.image_provider, request.key_choice)

        # Process and upload to Supabase (NO local save)
        if generated_posts:
            rendered = await process_and_upload_posts(generated_posts, brand, campaign_id)
            campaign.posts_json = rendered

            # Also populate individual post URL columns for easy access
            for i, post_data in enumerate(rendered, 1):
                if i == 1:
                    campaign.post_1_url = post_data.get("final_url")
                elif i == 2:
                    campaign.post_2_url = post_data.get("final_url")
                elif i == 3:
                    campaign.post_3_url = post_data.get("final_url")
                elif i == 4:
                    campaign.post_4_url = post_data.get("final_url")
                elif i == 5:
                    campaign.post_5_url = post_data.get("final_url")
                elif i == 6:
                    campaign.post_6_url = post_data.get("final_url")
                elif i == 7:
                    campaign.post_7_url = post_data.get("final_url")
                elif i == 8:
                    campaign.post_8_url = post_data.get("final_url")
                elif i == 9:
                    campaign.post_9_url = post_data.get("final_url")
                elif i == 10:
                    campaign.post_10_url = post_data.get("final_url")
                elif i == 11:
                    campaign.post_11_url = post_data.get("final_url")
                elif i == 12:
                    campaign.post_12_url = post_data.get("final_url")
                elif i == 13:
                    campaign.post_13_url = post_data.get("final_url")
                elif i == 14:
                    campaign.post_14_url = post_data.get("final_url")
                elif i == 15:
                    campaign.post_15_url = post_data.get("final_url")
                elif i == 16:
                    campaign.post_16_url = post_data.get("final_url")
                elif i == 17:
                    campaign.post_17_url = post_data.get("final_url")
                elif i == 18:
                    campaign.post_18_url = post_data.get("final_url")
                elif i == 19:
                    campaign.post_19_url = post_data.get("final_url")
                elif i == 20:
                    campaign.post_20_url = post_data.get("final_url")

        campaign.status = "completed"
        campaign.completed_at = datetime.now()
        db.commit()
        logger.info("Social post campaign %s completed: %d posts", campaign_id, len(generated_posts))

    except Exception as e:
        logger.error("Social post campaign %s failed: %s", campaign_id, e)
        campaign.status = "failed"
        campaign.error_message = str(e)
        db.commit()


@router.get("/social-posts/{campaign_id}")
async def get_social_post_campaign(campaign_id: str, db: Session = Depends(get_db)) -> dict:
    """Get campaign status and results"""
    campaign = db.query(SocialPostCampaign).filter(SocialPostCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {
        "id": campaign.id,
        "company_name": campaign.company_name,
        "status": campaign.status,
        "posts": campaign.posts_json or [],
        "image_provider": campaign.image_provider,
        "key_used": campaign.key_used,
        "error_message": campaign.error_message,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
    }


@router.get("/social-posts")
async def list_social_post_campaigns(db: Session = Depends(get_db)) -> list[dict]:
    """List all social post campaigns"""
    campaigns = db.query(SocialPostCampaign).order_by(SocialPostCampaign.created_at.desc()).limit(50).all()
    return [
        {
            "id": c.id,
            "company_name": c.company_name,
            "status": c.status,
            "number_of_posts": c.number_of_posts,
            "posts_count": len(c.posts_json) if c.posts_json else 0,
            "posts_json": c.posts_json or [],
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        }
        for c in campaigns
    ]