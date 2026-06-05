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
    status: str
    error_message: str | None = None
    title: str | None = None
    video_url: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
