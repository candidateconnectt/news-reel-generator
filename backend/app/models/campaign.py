"""SQLAlchemy model for the campaigns table.

UUIDs are stored as 36-char strings (with dashes). This is portable across
SQLite and Postgres and avoids cross-dialect quirks with the Uuid type on
SQLite. On Postgres, the column could be promoted to a native UUID via a
follow-up migration, but for the MVP a string is fine.
"""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String(36), primary_key=True, default=_new_uuid)

    # Input
    topic = Column(String(500), nullable=False)
    voice = Column(String(100), nullable=False, default="en-US-GuyNeural")
    scene_count = Column(Integer, nullable=False, default=5)
    aspect_ratio = Column(String(10), nullable=False, default="9:16")

    # State machine: pending → processing → ready_to_render → rendering → completed / failed
    status = Column(String(50), nullable=False, default="pending", index=True)
    error_message = Column(Text, nullable=True)

    # Populated when Make.com calls POST /campaigns/{id}/script
    title = Column(String(500), nullable=True)
    voiceover_full = Column(Text, nullable=True)
    script_json = Column(JSON, nullable=True)
    scenes_with_assets = Column(JSON, nullable=True)

    # Populated by the render worker
    video_path = Column(String(1000), nullable=True)
    video_url = Column(String(1000), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
