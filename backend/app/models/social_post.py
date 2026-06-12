"""SQLAlchemy model for social post campaigns."""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class SocialPostCampaign(Base):
    __tablename__ = "social_post_campaigns"

    id = Column(String(36), primary_key=True, default=_new_uuid)

    # Brand information
    company_name = Column(String(200), nullable=False, index=True)
    industry = Column(String(200), nullable=True)
    primary_color = Column(String(7), nullable=True)
    secondary_color = Column(String(7), nullable=True)
    accent_color = Column(String(7), nullable=True)
    font_style = Column(String(50), nullable=True)
    brand_tone = Column(String(100), nullable=True)
    visual_style = Column(String(200), nullable=True)
    tagline = Column(String(200), nullable=True)
    website_url = Column(String(200), nullable=True)
    target_audience = Column(String(500), nullable=True)
    key_products = Column(JSON, nullable=True)
    brand_values = Column(JSON, nullable=True)

    # Campaign goals
    objective = Column(String(100), nullable=True)
    key_messages = Column(JSON, nullable=True)
    campaign_tone = Column(String(100), nullable=True)
    target_platform = Column(String(50), nullable=True)
    number_of_posts = Column(Integer, nullable=True, default=8)

    # Image provider
    image_provider = Column(String(20), nullable=True, default="minimax")
    key_used = Column(String(20), nullable=True)  # "primary" or "secondary"

    # Status
    status = Column(String(50), nullable=False, default="pending", index=True)
    error_message = Column(Text, nullable=True)

    # Generated posts data - individual URLs for easy access
    post_1_url = Column(String(500), nullable=True)
    post_2_url = Column(String(500), nullable=True)
    post_3_url = Column(String(500), nullable=True)
    post_4_url = Column(String(500), nullable=True)
    post_5_url = Column(String(500), nullable=True)
    post_6_url = Column(String(500), nullable=True)
    post_7_url = Column(String(500), nullable=True)
    post_8_url = Column(String(500), nullable=True)
    post_9_url = Column(String(500), nullable=True)
    post_10_url = Column(String(500), nullable=True)
    post_11_url = Column(String(500), nullable=True)
    post_12_url = Column(String(500), nullable=True)
    post_13_url = Column(String(500), nullable=True)
    post_14_url = Column(String(500), nullable=True)
    post_15_url = Column(String(500), nullable=True)
    post_16_url = Column(String(500), nullable=True)
    post_17_url = Column(String(500), nullable=True)
    post_18_url = Column(String(500), nullable=True)
    post_19_url = Column(String(500), nullable=True)
    post_20_url = Column(String(500), nullable=True)

    # Full posts JSON (for reference)
    posts_json = Column(JSON, nullable=True)

    # Output directory (local storage path)
    output_directory = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)