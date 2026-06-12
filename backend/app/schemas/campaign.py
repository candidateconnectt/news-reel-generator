"""Pydantic schemas for request/response payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CampaignCreate(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500)
    voice: str = Field(default="en-US-GuyNeural", max_length=100)
    scene_count: int = Field(default=5, ge=1, le=20)
    aspect_ratio: str = Field(default="9:16", max_length=10)
    # Campaign mode: "reel_video" (Pexels clips, default), "reel_image" (AI-generated scenes), "post" (single image)
    campaign_type: str = Field(default="reel_video", pattern="^(reel_video|reel_image|post)$")
    # Brand context for AI image generation — inherit from brand settings
    brand_context: dict[str, Any] | None = Field(
        default=None,
        description="Brand identity: company, industry, colors, font, tone, visual_style",
    )


class CampaignScriptCallback(BaseModel):
    """Payload Make.com POSTs to /api/campaigns/{id}/script."""

    title: str
    voiceover_full: str
    scenes: list[dict[str, Any]]  # [{narration, search_term, video_url}, ...]


class CampaignFailCallback(BaseModel):
    """Payload Make.com POSTs to /api/campaigns/{id}/fail on any module error."""

    reason: str
    module: str | None = None


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topic: str
    voice: str
    scene_count: int
    aspect_ratio: str
    campaign_type: str
    status: str
    error_message: str | None = None
    title: str | None = None
    video_url: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    brand_context: dict[str, Any] | None = None
    generated_images: list[dict[str, Any]] | None = None
    image_prompts: list[dict[str, Any]] | None = None


class ImageGenRequest(BaseModel):
    """Request body for AI image generation on a campaign."""

    # For post: headline + supporting text + CTA + design direction
    headline: str = Field(..., min_length=1, max_length=200)
    supporting_text: str = Field(default="", max_length=300)
    cta: str = Field(default="", max_length=100)
    design_direction: str = Field(default="", max_length=500)
    # Override brand context (merge with campaign's brand_context)
    brand_context_override: dict[str, Any] | None = Field(default=None)


class ReelSceneImageRequest(BaseModel):
    """Request body for reel scene image generation."""

    scenes: list[dict[str, str]] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="List of scenes: [{scene_index: int, narration: str}, ...]",
    )
    brand_context_override: dict[str, Any] | None = Field(default=None)


class ImageGenResponse(BaseModel):
    """Response for a single generated image."""

    url: str
    revised_prompt: str | None = None
    provider: str
    scene_index: int | None = None


class ReelImageGenResponse(BaseModel):
    """Response for reel scene image generation."""

    scenes: list[ImageGenResponse]
    provider: str
    total: int
