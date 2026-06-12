"""Add image generation columns to campaigns.

Revision ID: add_image_gen
Revises:
Create Date: 2026-06-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "add_image_gen"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("campaign_type", sa.String(20), nullable=False, server_default="reel_video"))
    op.add_column("campaigns", sa.Column("brand_context", sa.JSON, nullable=True))
    op.add_column("campaigns", sa.Column("generated_images", sa.JSON, nullable=True))
    op.add_column("campaigns", sa.Column("image_prompts", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("campaigns", "image_prompts")
    op.drop_column("campaigns", "generated_images")
    op.drop_column("campaigns", "brand_context")
    op.drop_column("campaigns", "campaign_type")
