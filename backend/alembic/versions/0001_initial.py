"""initial campaigns table

Revision ID: 0001
Revises:
Create Date: 2026-06-05

Generic SQLAlchemy types so the same migration works on SQLite and Postgres.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("topic", sa.String(length=500), nullable=False),
        sa.Column("voice", sa.String(length=100), nullable=False, server_default="en-US-GuyNeural"),
        sa.Column("scene_count", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("aspect_ratio", sa.String(length=10), nullable=False, server_default="9:16"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending", index=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("voiceover_full", sa.Text(), nullable=True),
        sa.Column("script_json", sa.JSON(), nullable=True),
        sa.Column("scenes_with_assets", sa.JSON(), nullable=True),
        sa.Column("video_path", sa.String(length=1000), nullable=True),
        sa.Column("video_url", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("campaigns")
