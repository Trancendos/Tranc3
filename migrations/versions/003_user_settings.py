"""Add user_settings table for encrypted per-user secrets

Revision ID: 003_user_settings
Revises: 002_platform_services
Create Date: 2026-06-05
"""

import sqlalchemy as sa
from alembic import op

revision = "003_user_settings"
down_revision = "002_platform_services"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_settings_username", "user_settings", ["username"])
    op.create_index(
        "ix_user_settings_username_key",
        "user_settings",
        ["username", "key"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_user_settings_username_key", "user_settings")
    op.drop_index("ix_user_settings_username", "user_settings")
    op.drop_table("user_settings")
