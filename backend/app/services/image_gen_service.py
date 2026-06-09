"""Image Generation Service — brand-consistent AI image generation for posts and reels.

Supports both:
  - Single Post: 1 brand-consistent image per post
  - Reel: N scenes, ALL sharing the same visual world

Every image inherits: brand colors, visual style, typography, industry context,
tone of voice, and consistent composition/lighting across the reel.

Provider: MiniMax (primary) via MiniMax API.
Set IMAGE_PROVIDER=minimax or openai (DALL-E 3 fallback) via env var.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Brand Context
# ---------------------------------------------------------------------------

@dataclass
class BrandContext:
    """Brand DNA injected into every image prompt."""
    company_name: str = ""
    industry: str = ""
    primary_color: str = "#0057FF"
    secondary_color: str = "#FFFFFF"
    accent_color: str = "#FF6B35"
    font_style: str = "Inter"
    tone: str = "Professional"   # Professional / Casual / Bold / Minimal
    visual_style: str = "Modern SaaS"  # Modern SaaS / Corporate / Creative / Clean
    logo_url: str = ""

    def style_fragment(self) -> str:
        """Consistent visual language for every image in a brand."""
        style_parts = [
            self.visual_style,
            f"brand colors {self.primary_color} and {self.secondary_color}",
            f"{self.tone.lower()} tone",
        ]
        if self.industry:
            style_parts.insert(0, f"{self.industry} industry context")
        return ", ".join(filter(None, style_parts))

    def prompt_dna(self) -> str:
        """Short brand signature injected into every scene prompt (reels)."""
        return (
            f"brand colors {self.primary_color} and {self.secondary_color}, "
            f"{self.visual_style}, {self.tone.lower()} tone"
        )

    def to_yaml(self) -> dict[str, Any]:
        return {
            "company": self.company_name,
            "industry": self.industry,
            "primaryColor": self.primary_color,
            "secondaryColor": self.secondary_color,
            "accentColor": self.accent_color,
            "fontStyle": self.font_style,
            "tone": self.tone,
            "visualStyle": self.visual_style,
        }


# ---------------------------------------------------------------------------
# Prompt Structures
# ---------------------------------------------------------------------------

@dataclass
class PostPrompt:
    """Single post image prompt."""
    headline: str
    supporting_text: str = ""
    cta: str = ""
    design_direction: str = ""
    brand: BrandContext = field(default_factory=BrandContext)
    is_reel: bool = False

    def build(self) -> str:
        ratio = "vertical 9:16 reel" if self.is_reel else "square or landscape social media"
        elements = [
            self.headline,
            self.supporting_text,
            self.cta,
            self.design_direction,
            self.brand.style_fragment(),
            f"{ratio}, premium agency quality",
            "high resolution, professional composition",
        ]
        return ". ".join(filter(None, elements))


@dataclass
class ReelScene:
    """One scene in a storyboard."""
    scene_number: int
    narration: str
    image_prompt: str = ""


@dataclass
class ReelPrompt:
    """Full reel storyboard — all scenes share ONE visual world."""
    hook: str
    body: str
    cta: str
    scenes: list[ReelScene] = field(default_factory=list)
    brand: BrandContext = field(default_factory=BrandContext)

    def scene_prompt(self, scene: ReelScene) -> str:
        """Every scene MUST use the same visual DNA."""
        return (
            f"{scene.narration}. "
            f"{self.brand.prompt_dna()}, "
            "consistent cinematography, same lighting, same mood, "
            "professional reel footage style, vertical 9:16"
        )

    def all_prompts(self) -> list[tuple[int, str]]:
        return [(s.scene_number, self.scene_prompt(s)) for s in self.scenes]


# ---------------------------------------------------------------------------
# Generated Asset
# ---------------------------------------------------------------------------

@dataclass
class GeneratedImage:
    url: str
    revised_prompt: str | None = None
    provider: str = ""


# ---------------------------------------------------------------------------
# Image Generation Service
# ---------------------------------------------------------------------------

class ImageGenService:
    """Brand-consistent AI image generator.

    Usage:
        svc = ImageGenService()        # uses MiniMax
        svc = ImageGenService(provider="openai")  # DALL-E 3

        # Single post
        img = await svc.generate_post(brand=BrandContext(...), headline="We Are Hiring", ...)

        # Reel — all scenes concurrently
        imgs = await svc.generate_reel_scenes(brand=BrandContext(...), hook="...", body="...", cta="...", scenes=[ReelScene(...), ...])
    """

    def __init__(self, provider: str = "minimax"):
        self.provider = provider.lower()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def generate_post(
        self,
        brand: BrandContext,
        headline: str,
        supporting_text: str = "",
        cta: str = "",
        design_direction: str = "",
        is_reel: bool = False,
    ) -> GeneratedImage:
        """Generate a single brand-consistent post/reel image."""
        prompt = PostPrompt(
            headline=headline,
            supporting_text=supporting_text,
            cta=cta,
            design_direction=design_direction,
            brand=brand,
            is_reel=is_reel,
        ).build()

        logger.info("ImageGen [%s] post prompt (trunc): %s", self.provider, prompt[:80])

        if self.provider == "minimax":
            return await self._minimax(prompt, is_reel=is_reel)
        elif self.provider == "openai":
            return await self._dalle(prompt, is_reel=is_reel)
        else:
            return await self._dalle(prompt, is_reel=is_reel)

    async def generate_reel_scenes(
        self,
        brand: BrandContext,
        hook: str,
        body: str,
        cta: str,
        scenes: list[ReelScene],
    ) -> list[GeneratedImage]:
        """Generate ALL reel scenes concurrently — same visual world, consistent quality."""
        reel = ReelPrompt(
            hook=hook,
            body=body,
            cta=cta,
            scenes=scenes,
            brand=brand,
        )
        scene_prompts = reel.all_prompts()

        logger.info(
            "ImageGen [%s] generating %d reel scenes concurrently for hook='%s'",
            self.provider, len(scene_prompts), hook,
        )

        if self.provider == "minimax":
            tasks = [self._minimax(p, is_reel=True) for _, p in scene_prompts]
        else:
            tasks = [self._dalle(p, is_reel=True) for _, p in scene_prompts]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        generated = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Scene %d generation failed: %s", i, result)
                generated.append(GeneratedImage(url="", provider=self.provider))
            else:
                generated.append(result)

        return generated

    # ------------------------------------------------------------------ #
    # Provider: MiniMax
    # ------------------------------------------------------------------ #

    async def _minimax(self, prompt: str, is_reel: bool) -> GeneratedImage:
        """MiniMax image generation via platform.minimax.com API."""
        api_key = os.environ.get("MINIMAX_API_KEY", "") or os.environ.get("IMAGE_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "MINIMAX_API_KEY not set. "
                "Get yours at https://platform.minimax.com"
            )

        # Map ratio to MiniMax format
        size = "3:4" if is_reel else "1:1"

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://api.minimax.chat/v1/images/gen",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "image-01",
                    "prompt": prompt,
                    "aspect_ratio": size,
                    "response_format": "url",
                },
            )
            r.raise_for_status()
            data = r.json()

        items: list[dict] = data.get("data", [])
        if not items:
            raise RuntimeError(f"MiniMax returned no images: {data}")

        return GeneratedImage(
            url=items[0].get("url", ""),
            revised_prompt=items[0].get("revised_prompt"),
            provider="minimax",
        )

    # ------------------------------------------------------------------ #
    # Provider: OpenAI DALL-E 3
    # ------------------------------------------------------------------ #

    async def _dalle(self, prompt: str, is_reel: bool) -> GeneratedImage:
        """OpenAI DALL-E 3 via OpenAI API."""
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not set. "
                "Get yours at https://platform.openai.com"
            )

        # DALL-E 3 sizes: 1024x1024, 1792x1024, 1024x1792
        size = "1024x1792" if is_reel else "1024x1024"

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "size": size,
                    "quality": "standard",
                    "n": 1,
                },
            )
            r.raise_for_status()
            data = r.json()

        items: list[dict] = data.get("data", [])
        if not items:
            raise RuntimeError(f"DALL-E returned no images: {data}")

        return GeneratedImage(
            url=items[0].get("url", ""),
            revised_prompt=items[0].get("revised_prompt", prompt),
            provider="dall-e-3",
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_image_svc: ImageGenService | None = None


def get_image_service() -> ImageGenService:
    global _image_svc
    if _image_svc is None:
        provider = os.environ.get("IMAGE_PROVIDER", "minimax").lower()
        _image_svc = ImageGenService(provider=provider)
    return _image_svc
