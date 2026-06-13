"""Platform services tables — Observatory, DevOcity, ChronosSphere

Revision ID: 002_platform_services
Revises: 001_initial
Create Date: 2026-05-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "002_platform_services"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade():
    # ── The Observatory — persistent audit event log ──────────────────────────
    op.create_table(
        "observatory_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("service", sa.String(64), nullable=True),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("target", sa.String(255), nullable=True),
        sa.Column("severity", sa.String(20), nullable=True, server_default="info"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_observatory_events_event_type", "observatory_events", ["event_type"])
    op.create_index("ix_observatory_events_service", "observatory_events", ["service"])
    op.create_index("ix_observatory_events_created_at", "observatory_events", ["created_at"])
    op.create_index("ix_observatory_events_severity", "observatory_events", ["severity"])

    # ── DevOcity — developer accounts and API keys ────────────────────────────
    op.create_table(
        "developer_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "developer_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),  # trx_XXXXXXXX
        sa.Column("key_hash", sa.String(64), nullable=False),  # SHA-256, never plain
        sa.Column("scopes", postgresql.ARRAY(sa.String(32)), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["developer_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_developer_api_keys_hash", "developer_api_keys", ["key_hash"])
    op.create_index("ix_developer_api_keys_account", "developer_api_keys", ["account_id"])

    # ── ChronosSphere — persistent scheduled tasks ────────────────────────────
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("schedule_type", sa.String(20), nullable=False),
        sa.Column("schedule_value", sa.String(120), nullable=False),
        sa.Column("workflow_id", sa.String(255), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── The Citadel — deploy history ──────────────────────────────────────────
    op.create_table(
        "deploy_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("triggered_by", sa.String(120), nullable=True),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("completed_at", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deploy_records_target", "deploy_records", ["target"])
    op.create_index("ix_deploy_records_status", "deploy_records", ["status"])


def downgrade():
    op.drop_table("deploy_records")
    op.drop_table("scheduled_tasks")
    op.drop_index("ix_developer_api_keys_account", "developer_api_keys")
    op.drop_index("ix_developer_api_keys_hash", "developer_api_keys")
    op.drop_table("developer_api_keys")
    op.drop_table("developer_accounts")
    op.drop_index("ix_observatory_events_severity", "observatory_events")
    op.drop_index("ix_observatory_events_created_at", "observatory_events")
    op.drop_index("ix_observatory_events_service", "observatory_events")
    op.drop_index("ix_observatory_events_event_type", "observatory_events")
    op.drop_table("observatory_events")
