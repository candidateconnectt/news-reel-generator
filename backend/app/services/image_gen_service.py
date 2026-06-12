"""Image Generation Service — brand-consistent, agency-grade AI image generation.

Layered architecture:
  Topic → CreativeBrief → VisualBible → PromptBuilder → Image

  Every image inherits:
    - BrandContext : company identity (colors, tone, industry, visual style)
    - CreativeBrief     : campaign goal, audience, angle, tone, theme
    - VisualBible       : locked visual DNA (lighting, environment, camera, palette)
    - ContentTemplate   : layout rules for specific content types
    - NegativePrompts   : quality gates to suppress hallucination

 Two workflows:
    1. Post  — single brand-consistent image (1:1 or 4:5)
    2. Reel  — storyboard of N scenes, ALL sharing ONE Visual Bible

  Provider priority: MiniMax > DeepSeek > OpenAI DALL-E 3 > Ideogram.
  Set IMAGE_PROVIDER=minimax|deepseek|openai|ideogram in .env to override."""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Negative Prompts — quality gates applied to every image generation request
# ---------------------------------------------------------------------------

NEGATIVE_PROMPTS = (
    "blurry, low quality, distorted text, watermark, cartoon, anime style, "
    "cluttered layout, poor composition, random colors, low resolution, "
    "ugly typography, handwriting, misspelled text, fade, overexposed, "
    "underexposed, noisy, pixelated, amateur, stock photo look"
)


# ---------------------------------------------------------------------------
# Brand Context — extended with full visual system fields
# ---------------------------------------------------------------------------

@dataclass
class BrandContext:
    # Identity
    company_name: str = ""
    industry: str = ""
    # Colors
    primary_color: str = "#0057FF"
    secondary_color: str = "#FFFFFF"
    accent_color: str = "#FF6B35"
    # Typography
    font_style: str = "Inter"
    # Tone & style
    tone: str = "Professional"
    visual_style: str = "Modern SaaS"
    logo_url: str = ""
    # ── New visual system fields ──────────────────────────────────────────
    photography_style: str = "Commercial Photography"
    lighting_style: str = "Bright Natural Light"
    composition_style: str = "Clean Minimal Layout"
    icon_style: str = "Flat Vector"
    design_quality: str = "Agency Grade"
    # Optional: if a Visual Bible is pre-generated for this brand, store it here
    _visual_bible: VisualBible | None = field(default=None, repr=False)

    # ── Derived strings ────────────────────────────────────────────────────

    def style_string(self) -> str:
        parts = [
            self.visual_style,
            f"colors {self.primary_color} and {self.secondary_color}",
            f"{self.tone.lower()} tone",
        ]
        if self.industry:
            parts.insert(0, f"{self.industry} context")
        return ", ".join(filter(None, parts))

    def brand_dna(self) -> str:
        return (
            f"brand colors {self.primary_color}/{self.secondary_color}, "
            f"{self.visual_style}, {self.tone.lower()} tone"
        )

    def color_palette_list(self) -> list[str]:
        """Returns brand colors as a list for Visual Bible construction."""
        return [c for c in [self.primary_color, self.secondary_color, self.accent_color] if c]

    def to_dict(self) -> dict[str, Any]:
        return {
            "company": self.company_name,
            "industry": self.industry,
            "primaryColor": self.primary_color,
            "secondaryColor": self.secondary_color,
            "accentColor": self.accent_color,
            "fontStyle": self.font_style,
            "tone": self.tone,
            "visualStyle": self.visual_style,
            "photographyStyle": self.photography_style,
            "lightingStyle": self.lighting_style,
            "compositionStyle": self.composition_style,
            "iconStyle": self.icon_style,
            "designQuality": self.design_quality,
        }


# ---------------------------------------------------------------------------
# Creative Brief — campaign-level structured brief before prompt generation
# ---------------------------------------------------------------------------

@dataclass
class CreativeBrief:
    """Structured brief that guides every prompt for a given campaign.

    Bridges the gap between a raw topic/headline and the actual image prompt.
    All fields are optional — missing fields fall back to brand defaults.
    """

    objective: str = ""           # e.g. "Recruitment", "Product Launch", "Awareness"
    audience: str = ""           # e.g. "Software Engineers", "Commuters", "Parents"
    marketing_angle: str = ""    # e.g. "Career Growth", "Save Time", "Safety First"
    tone: str = ""               # e.g. "Professional", "Playful", "Urgent"
    visual_theme: str = ""       # e.g. "Modern SaaS", "Premium Finance", "Health & Wellness"
    content_type: str = ""       # e.g. "Hiring", "Promotion", "Event", "Announcement", "Achievement"

    def is_empty(self) -> bool:
        return not any([self.objective, self.audience, self.marketing_angle,
                        self.tone, self.visual_theme, self.content_type])

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "audience": self.audience,
            "marketing_angle": self.marketing_angle,
            "tone": self.tone,
            "visual_theme": self.visual_theme,
            "content_type": self.content_type,
        }


# ---------------------------------------------------------------------------
# Visual Bible — locked visual DNA reused across every asset for a brand
# ---------------------------------------------------------------------------

@dataclass
class VisualBible:
    """The single source of visual truth for a brand or campaign.

    Generated once from BrandContext + CreativeBrief, then reused verbatim
    across all posts and all reel scenes. Guarantees lighting, palette,
    environment, camera style, and mood stay identical within a campaign.
    """

    environment: str = "Modern SaaS Office"
    lighting: str = "Bright Natural Light"
    camera_style: str = "Commercial Photography"
    composition: str = "Clean Minimal Layout"
    palette: list[str] = field(default_factory=list)   # hex color list
    mood: str = "Professional and Trustworthy"
    quality: str = "Agency Grade"
    # Visual Bible can carry a reference to the Creative Brief it was built from
    brief: CreativeBrief | None = None

    def lighting_string(self) -> str:
        return f"lighting: {self.lighting}, mood: {self.mood}"

    def camera_string(self) -> str:
        return f"{self.camera_style}, {self.composition}"

    def palette_string(self) -> str:
        if not self.palette:
            return ""
        return "color palette: " + ", ".join(self.palette)

    def environment_string(self) -> str:
        return f"environment: {self.environment}"

    def full_visual_dna(self) -> str:
        """One condensed string of all visual DNA for prompt injection."""
        parts = [
            self.environment_string(),
            self.lighting_string(),
            self.camera_string(),
            self.palette_string(),
            f"quality: {self.quality}",
        ]
        return ". ".join(filter(None, parts))

    @classmethod
    def from_brand(cls, brand: BrandContext, brief: CreativeBrief | None = None) -> VisualBible:
        """Generate a Visual Bible from brand identity and optional creative brief."""
        # Resolve values — brief overrides brand, brand fills the rest
        tone = (brief.tone or brand.tone or "Professional").lower()
        theme = brief.visual_theme or brand.visual_style if not brief else brand.visual_style

        # Map tone to lighting/mood
        lighting_map = {
            "professional": "Bright Natural Light",
            "playful": "Warm Soft Ambient Light",
            "urgent": "High Contrast Dramatic Light",
            "luxury": "Low Key Elegant Lighting",
            "minimal": "Diffused Neutral Light",
        }
        mood_map = {
            "professional": "Professional and Trustworthy",
            "playful": "Friendly and Energetic",
            "urgent": "Bold and Urgent",
            "luxury": "Sophisticated and Premium",
            "minimal": "Calm and Focused",
        }
        lighting = lighting_map.get(tone, "Bright Natural Light")
        mood = mood_map.get(tone, "Professional and Trustworthy")

        return cls(
            environment=f"clean {theme} setting",
            lighting=lighting,
            camera_style=brand.photography_style,
            composition=brand.composition_style,
            palette=brand.color_palette_list(),
            mood=mood,
            quality=brand.design_quality,
            brief=brief,
        )


# ---------------------------------------------------------------------------
# Content Templates — reusable layout rules per content type
# ---------------------------------------------------------------------------

@dataclass
class ContentTemplate:
    """Layout and visual direction rules for a specific content type.

    Templates give each content type (Hiring, Promotion, Event, etc.) a
    consistent visual direction so posts of the same type feel related
    even when generated in different campaigns.
    """

    content_type: str                           # "hiring" | "promotion" | "event" | ...
    visual_direction: str = ""                # e.g. "icon-forward", "photo-centric"
    layout_rules: str = ""                     # e.g. "centered composition", "left-weighted"
    cta_placement: str = "bottom center"      # where to position CTA in post
    # Composition hints baked into every prompt for this type
    composition_hint: str = ""

    def apply(self, base_prompt: str) -> str:
        parts = [base_prompt]
        if self.visual_direction:
            parts.append(f"visual direction: {self.visual_direction}")
        if self.layout_rules:
            parts.append(f"layout: {self.layout_rules}")
        if self.composition_hint:
            parts.append(f"composition: {self.composition_hint}")
        return ". ".join(parts)


# Predefined template registry — extend here to add new content types
CONTENT_TEMPLATES: dict[str, ContentTemplate] = {
    "hiring": ContentTemplate(
        content_type="hiring",
        visual_direction="professional, clean, icon-forward with subtle geometric accents",
        layout_rules="centered layout with generous whitespace, headline dominant",
        cta_placement="bottom center",
        composition_hint="single focal point, employee or team imagery implied, brand colors prominent",
    ),
    "promotion": ContentTemplate(
        content_type="promotion",
        visual_direction="bold, energetic, offer-forward",
        layout_rules="off-center composition, headline in upper half, CTA in lower third",
        cta_placement="lower third",
        composition_hint="dynamic angle, sense of movement or reward, bright accent color pop",
    ),
    "event": ContentTemplate(
        content_type="event",
        visual_direction="vibrant, gathering-focused, communal",
        layout_rules="central focal point, surrounding negative space for text overlay",
        cta_placement="bottom center",
        composition_hint="crowd or event imagery implied, warm lighting, inclusive framing",
    ),
    "announcement": ContentTemplate(
        content_type="announcement",
        visual_direction="authoritative, clean, milestone-forward",
        layout_rules="centered, symmetrical, headline dominant over supporting visual",
        cta_placement="bottom center",
        composition_hint="single bold element, celebration or achievement implied, brand colors",
    ),
    "achievement": ContentTemplate(
        content_type="achievement",
        visual_direction="triumphant, premium, milestone-focused",
        layout_rules="centered with subtle background texture, headline prominent",
        cta_placement="bottom center",
        composition_hint="trophy or achievement symbol implied, gold or accent highlight, confident composition",
    ),
    "product launch": ContentTemplate(
        content_type="product launch",
        visual_direction="sleek, futuristic, product-forward",
        layout_rules="product as hero, minimal surrounding, headline above product",
        cta_placement="lower third",
        composition_hint="studio lighting on product, clean backdrop, high contrast, tech aesthetic",
    ),
    "case study": ContentTemplate(
        content_type="case study",
        visual_direction="data-forward, credible, professional",
        layout_rules="left-weighted layout, chart or graph element implied, headline left-aligned",
        cta_placement="bottom right",
        composition_hint="infographic elements implied, clean data visualization aesthetic, trust-building",
    ),
    "general": ContentTemplate(
        content_type="general",
        visual_direction="clean, professional, brand-forward",
        layout_rules="centered composition with balanced whitespace",
        cta_placement="bottom center",
        composition_hint="single clean focal point, brand colors dominant, modern aesthetic",
    ),
}


def get_template(content_type: str) -> ContentTemplate:
    """Return template for content type, falling back to 'general'."""
    return CONTENT_TEMPLATES.get(content_type.lower(), CONTENT_TEMPLATES["general"])


# ---------------------------------------------------------------------------
# Campaign Visual Context — campaign-level consistency for reel scenes
# ---------------------------------------------------------------------------

@dataclass
class CampaignVisualContext:
    """Holds the Visual Bible at campaign level so all reel scenes share
    identical visual DNA. Created once per campaign/reel generation run.

    Usage:
        ctx = CampaignVisualContext(brand=brand, brief=brief)
        bible = ctx.visual_bible   # reuse for every scene
    """

    brand: BrandContext
    brief: CreativeBrief | None = None
    visual_bible: VisualBible = field(init=False)

    def __post_init__(self):
        # Build Visual Bible once from brand + brief; reuse across all scenes
        self.visual_bible = VisualBible.from_brand(self.brand, self.brief)

    def scene_prompt(
        self,
        scene: ReelScene,
        template: ContentTemplate | None = None,
        negative_prompts: str = NEGATIVE_PROMPTS,
    ) -> str:
        """Build a prompt for a single reel scene that inherits campaign visual DNA."""
        parts = [
            scene.narration,
            self.visual_bible.full_visual_dna(),
            f"vertical9:16 reel format",
            f"consistent with campaign visual style — same lighting, same palette, same mood",
            f"no text, no readable words, no typography",
            f"negative: {negative_prompts}",
        ]
        if template:
            parts.append(template.apply(""))
        return ". ".join(filter(None, parts))


# ---------------------------------------------------------------------------
# Asset Memory — lightweight in-memory store of generated assets per brand
# ---------------------------------------------------------------------------

@dataclass
class BrandAssetMemory:
    """Tracks generated image URLs per brand to avoid near-duplicate reuse.

    Lightweight in-memory store. Not persisted — reset on server restart.
    For production, replace with a database table keyed on brand+campaign.
    """

    brand_name: str
    generated_urls: list[str] = field(default_factory=list)
    generated_prompts: list[str] = field(default_factory=list)

    def add(self, url: str, prompt: str) -> None:
        self.generated_urls.append(url)
        self.generated_prompts.append(prompt)

    def is_similar(self, prompt: str, threshold: float = 0.75) -> bool:
        """Crude similarity check — returns True if any stored prompt shares
        more than `threshold` fraction of words with the new prompt.
        For production, replace with embedding-based similarity."""
        if not self.generated_prompts:
            return False
        new_words = set(prompt.lower().split())
        for stored in self.generated_prompts:
            stored_words = set(stored.lower().split())
            if not stored_words:
                continue
            overlap = len(new_words & stored_words)
            jaccard = overlap / len(new_words | stored_words)
            if jaccard > threshold:
                return True
        return False


# In-memory asset store — key is brand name (lowercase)
_ASSET_MEMORY: dict[str, BrandAssetMemory] = {}


def get_asset_memory(brand: BrandContext) -> BrandAssetMemory:
    key = brand.company_name.lower().strip()
    if key not in _ASSET_MEMORY:
        _ASSET_MEMORY[key] = BrandAssetMemory(brand_name=brand.company_name)
    return _ASSET_MEMORY[key]


# ---------------------------------------------------------------------------
# Prompt Builder — structured assembly of all prompt layers
# ---------------------------------------------------------------------------

class PromptBuilder:
    """Assembles image prompts from layered components instead of raw concat.

    Construction flow:
      BrandContext + CreativeBrief
        → VisualBible (resolved once)
        → PromptBuilder (assemble per-request)

    Prompt layers (in order):
      1. Scene / content description
      2. Visual Bible visual DNA
      3. Content template rules
      4. Brand style string
      5. Format & quality instructions
      6. Negative prompts
      7. NO text / typography instruction
    """

    def __init__(
        self,
        brand: BrandContext,
        brief: CreativeBrief | None = None,
        template: ContentTemplate | None = None,
        negative_prompts: str = NEGATIVE_PROMPTS,
    ):
        self.brand = brand
        self.brief = brief or CreativeBrief()
        self.template = template or get_template(self.brief.content_type)
        self.negative_prompts = negative_prompts
        # Resolve Visual Bible once per builder instance
        self._visual_bible = VisualBible.from_brand(brand, self.brief)

    # ── Core build ─────────────────────────────────────────────────────────

    def build_post_prompt(
        self,
        headline: str,
        supporting_text: str = "",
        cta: str = "",
        design_direction: str = "",
        is_reel: bool = False,
    ) -> str:
        """Build a structured post/reel image prompt.

        Text fields (headline, supporting_text, cta) are NOT included in the
        image prompt — they are stored separately and rendered programmatically.
        The image prompt generates only the branded background/visual.
        """
        ratio = "vertical 9:16 reel format" if is_reel else "square social media post (1:1)"

        parts = [
            # 1. Content direction from brief/template
            self._content_direction(),
            # 2. Visual Bible DNA
            self._visual_bible.full_visual_dna(),
            # 3. Template rules
            self._template_rules(),
            # 4. Brand style
            self.brand.style_string(),
            # 5. Format & quality
            ratio,
            "premium agency quality, professional composition, high detail",
            # 6. Negative prompts
            f"negative: {self.negative_prompts}",
            # 7. No text — critical anti-hallucination gate
            "no text, no readable words, no typography, no logos, no watermarks, no letters",
        ]
        return ". ".join(filter(None, parts))

    def build_reel_scene_prompt(self, scene: ReelScene) -> str:
        """Build a reel scene prompt that inherits campaign Visual Bible."""
        parts = [
            scene.narration,
            self._visual_bible.full_visual_dna(),
            "consistent cinematography across all scenes, same lighting, same mood",
            "professional vertical reel footage style, 9:16",
            f"negative: {self.negative_prompts}",
            "no text, no readable words, no typography",
        ]
        return ". ".join(filter(None, parts))

    # ── Layer helpers ──────────────────────────────────────────────────────

    def _content_direction(self) -> str:
        parts = []
        if self.brief.objective:
            parts.append(f"campaign objective: {self.brief.objective}")
        if self.brief.audience:
            parts.append(f"target audience: {self.brief.audience}")
        if self.brief.marketing_angle:
            parts.append(f"marketing angle: {self.brief.marketing_angle}")
        return ". ".join(parts)

    def _template_rules(self) -> str:
        parts = []
        if self.template.visual_direction:
            parts.append(f"visual direction: {self.template.visual_direction}")
        if self.template.layout_rules:
            parts.append(f"layout: {self.template.layout_rules}")
        if self.template.composition_hint:
            parts.append(f"composition: {self.template.composition_hint}")
        return ". ".join(parts)

    # ── Accessors ───────────────────────────────────────────────────────────

    @property
    def visual_bible(self) -> VisualBible:
        return self._visual_bible


# ---------------------------------------------------------------------------
# Prompt builders (legacy dataclass interface — now delegates to PromptBuilder)
# ---------------------------------------------------------------------------

@dataclass
class PostPrompt:
    """Legacy dataclass interface — retained for backwards compatibility.

    Internally delegates to PromptBuilder so all layered improvements apply
    even when using the old dataclass API.
    """

    headline: str
    supporting_text: str = ""
    cta: str = ""
    design_direction: str = ""
    brand: BrandContext = field(default_factory=BrandContext)
    brief: CreativeBrief | None = None
    is_reel: bool = False

    def build(self) -> str:
        builder = PromptBuilder(brand=self.brand, brief=self.brief)
        return builder.build_post_prompt(
            headline=self.headline,
            supporting_text=self.supporting_text,
            cta=self.cta,
            design_direction=self.design_direction,
            is_reel=self.is_reel,
        )


@dataclass
class ReelScene:
    scene_number: int
    narration: str
    image_prompt: str = ""


@dataclass
class ReelStoryboard:
    """Legacy dataclass interface — retained for backwards compatibility.

    Internally delegates to PromptBuilder with campaign-level Visual Bible
    so all reel scenes share consistent visual DNA.
    """

    hook: str
    body: str
    cta: str
    scenes: list[ReelScene] = field(default_factory=list)
    brand: BrandContext = field(default_factory=BrandContext)
    brief: CreativeBrief | None = None

    def __post_init__(self):
        # Build campaign visual context once — reuse for all scenes
        self._ctx = CampaignVisualContext(brand=self.brand, brief=self.brief)

    def scene_prompt(self, scene: ReelScene) -> str:
        return self._ctx.scene_prompt(scene)

    def all_prompts(self) -> list[tuple[int, str]]:
        return [(s.scene_number, self.scene_prompt(s)) for s in self.scenes]


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class GeneratedImage:
    url: str
    revised_prompt: str | None = None
    provider: str = ""
    # ── New fields — text stored separately for programmatic rendering ──────
    headline: str = ""
    supporting_text: str = ""
    cta: str = ""
    brand_colors: list[str] = field(default_factory=list)
    visual_bible: VisualBible | None = None


# ---------------------------------------------------------------------------
# Provider enum
# ---------------------------------------------------------------------------

class ImageProvider(Enum):
    MINIMAX = "minimax"
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    IDEOGRAM = "ideogram"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ImageGenService:
    def __init__(self, provider: str | None = None):
        raw = (provider or os.environ.get("IMAGE_PROVIDER", "minimax") or "minimax").lower()
        try:
            self.provider = ImageProvider(raw)
        except ValueError:
            self.provider = ImageProvider.OPENAI

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
        brief: CreativeBrief | None = None,
    ) -> GeneratedImage:
        """Generate a brand-consistent post image.

        Args:
            brand: Brand identity and visual system.
            headline: Campaign headline (NOT included in image prompt).
            supporting_text: Body copy (NOT included in image prompt).
            cta: Call-to-action text (NOT included in image prompt).
            design_direction: Optional free-text design guidance.
            is_reel: True for 9:16 vertical reel format.
            brief: Optional Creative Brief for campaign-level guidance.

        Returns:
            GeneratedImage with url + text fields separated for programmatic
            rendering (e.g. via Pillow or FFmpeg captions).
        """
        builder = PromptBuilder(brand=brand, brief=brief)
        prompt = builder.build_post_prompt(
            headline=headline,
            supporting_text=supporting_text,
            cta=cta,
            design_direction=design_direction,
            is_reel=is_reel,
        )
        logger.info("[%s] post prompt: %s", self.provider.value, prompt[:120])

        # Check asset memory for near-duplicate
        memory = get_asset_memory(brand)
        if memory.is_similar(prompt):
            logger.warning("[%s] similar prompt detected for brand %s — consider revising", self.provider.value, brand.company_name)

        if self.provider == ImageProvider.MINIMAX:
            result = await self._minimax(prompt, is_reel)
        elif self.provider == ImageProvider.DEEPSEEK:
            result = await self._deepseek(prompt, is_reel)
        elif self.provider == ImageProvider.IDEOGRAM:
            result = await self._ideogram(prompt, is_reel)
        else:
            result = await self._openai_dalle(prompt, is_reel)

        # Enrich result with separated text fields
        result.headline = headline
        result.supporting_text = supporting_text
        result.cta = cta
        result.brand_colors = brand.color_palette_list()
        result.visual_bible = builder.visual_bible

        # Record in asset memory
        memory.add(result.url, prompt)

        return result

    async def generate_reel_scenes(
        self,
        brand: BrandContext,
        hook: str,
        body: str,
        cta: str,
        scenes: list[ReelScene],
        brief: CreativeBrief | None = None,
    ) -> list[GeneratedImage]:
        """Generate a storyboard of reel scenes sharing one Visual Bible.

        All scenes inherit the same Visual Bible (lighting, palette,
        environment, camera style) — only the narration changes per scene.
        """
        # Build campaign-level visual context once
        ctx = CampaignVisualContext(brand=brand, brief=brief)
        logger.info(
            "[%s] generating %d reel scenes with campaign Visual Bible",
            self.provider.value,
            len(scenes),
        )
        logger.info("[%s] Visual Bible: %s", self.provider.value, ctx.visual_bible.full_visual_dna()[:100])

        tasks = []
        for scene in scenes:
            prompt = ctx.scene_prompt(scene)
            logger.info("[%s] scene %d prompt: %s", self.provider.value, scene.scene_number, prompt[:100])
            if self.provider == ImageProvider.MINIMAX:
                tasks.append(self._minimax(prompt, True))
            elif self.provider == ImageProvider.DEEPSEEK:
                tasks.append(self._deepseek(prompt, True))
            elif self.provider == ImageProvider.IDEOGRAM:
                tasks.append(self._ideogram(prompt, True))
            else:
                tasks.append(self._openai_dalle(prompt, True))

        results: list[GeneratedImage] = []
        errors: list[Exception] = []
        for task in asyncio.as_completed(tasks):
            try:
                result = await task
                result.headline = hook
                result.supporting_text = body
                result.cta = cta
                result.brand_colors = brand.color_palette_list()
                result.visual_bible = ctx.visual_bible
                results.append(result)
            except Exception as exc:
                errors.append(exc)

        if errors:
            logger.error("[%s] %d/%d scenes failed", self.provider.value, len(errors), len(scenes))
            raise errors[0]

        # Record in asset memory
        memory = get_asset_memory(brand)
        for r in results:
            memory.add(r.url, "")

        return results

    # ------------------------------------------------------------------ #
    # MiniMax
    # ------------------------------------------------------------------ #

    async def _minimax(self, prompt: str, is_reel: bool) -> GeneratedImage:
        key = settings.minimax_api_key.strip() if settings.minimax_api_key else ""
        if not key:
            raise RuntimeError("MINIMAX_API_KEY not set at https://platform.minimax.com")
        size = "3:4" if is_reel else "1:1"
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://api.minimax.io/v1/image_generation",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "image-01", "prompt": prompt, "aspect_ratio": size, "response_format": "url"},
            )
        data = r.json()
        base = data.get("base_resp", {})
        status_code = base.get("status_code", 0)
        if status_code != 0:
            msg = base.get("status_msg", "unknown error")
            logger.error("MiniMax API error %s: %s", status_code, msg)
            raise RuntimeError(f"MiniMax error {status_code}: {msg}")
        image_urls: list[str] = data.get("data", {}).get("image_urls", [])
        if not image_urls:
            raise RuntimeError(f"MiniMax returned no images: {data}")
        return GeneratedImage(
            url=image_urls[0],
            revised_prompt=None,
            provider="minimax",
        )

    # ------------------------------------------------------------------ #
    # DeepSeek Vision
    # ------------------------------------------------------------------ #

    async def _deepseek(self, prompt: str, is_reel: bool) -> GeneratedImage:
        key = settings.deepseek_api_key.strip() if settings.deepseek_api_key else ""
        if not key:
            raise RuntimeError("DEEPSEEK_API_KEY not set at https://platform.deepseek.com")
        size = "1024x1792" if is_reel else "1024x1024"
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://api.deepseek.com/v1/images/generations",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "deepseek-image-01", "prompt": prompt, "size": size, "n": 1},
            )
        if r.status_code >= 400:
            logger.error("DeepSeek %s: %s", r.status_code, r.text[:300])
            raise RuntimeError(f"DeepSeek API {r.status_code}: {r.text[:200]}")
        data = r.json()
        items: list[dict] = data.get("data", [])
        if not items:
            raise RuntimeError(f"DeepSeek returned no images: {data}")
        return GeneratedImage(
            url=items[0].get("url", ""),
            revised_prompt=items[0].get("revised_prompt"),
            provider="deepseek",
        )

    # ------------------------------------------------------------------ #
    # OpenAI DALL-E 3
    # ------------------------------------------------------------------ #

    async def _openai_dalle(self, prompt: str, is_reel: bool) -> GeneratedImage:
        key = settings.openai_api_key.strip() if settings.openai_api_key else ""
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set at https://platform.openai.com")
        size = "1024x1792" if is_reel else "1024x1024"
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "dall-e-3", "prompt": prompt, "size": size, "quality": "standard", "n": 1},
            )
        if r.status_code >= 400:
            logger.error("DALL-E %s: %s", r.status_code, r.text[:300])
            raise RuntimeError(f"DALL-E API {r.status_code}: {r.text[:200]}")
        data = r.json()
        items: list[dict] = data.get("data", [])
        if not items:
            raise RuntimeError(f"DALL-E returned no images: {data}")
        return GeneratedImage(
            url=items[0].get("url", ""),
            revised_prompt=items[0].get("revised_prompt", prompt),
            provider="dall-e-3",
        )

    # ------------------------------------------------------------------ #
    # Ideogram (free, reliable)
    # ------------------------------------------------------------------ #

    async def _ideogram(self, prompt: str, is_reel: bool) -> GeneratedImage:
        key = settings.ideogram_api_key.strip() if settings.ideogram_api_key else ""
        if not key:
            raise RuntimeError("IDEOGRAM_API_KEY not set at https://ideogram.ai/api")
        size = "1344x2392" if is_reel else "1024x1024"
        style = "REALISTIC" if "office" in prompt.lower() or "professional" in prompt.lower() else "DESIGN"
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://api.ideogram.ai/v1/image_generation",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "prompt": prompt,
                    "aspect_ratio": "3:4" if is_reel else "1:1",
                    "style": style,
                    "resolution": "1344x2392" if is_reel else "1024x1024",
                },
            )
        if r.status_code >= 400:
            logger.error("Ideogram %s: %s", r.status_code, r.text[:300])
            raise RuntimeError(f"Ideogram API {r.status_code}: {r.text[:200]}")
        data = r.json()
        items: list[dict] = data.get("data", [])
        if not items:
            raise RuntimeError(f"Ideogram returned no images: {data}")
        return GeneratedImage(
            url=items[0].get("url", ""),
            revised_prompt=items[0].get("revised_prompt"),
            provider="ideogram",
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_svc: ImageGenService | None = None


def get_image_service() -> ImageGenService:
    global _svc
    if _svc is None:
        _svc = ImageGenService()
    return _svc
