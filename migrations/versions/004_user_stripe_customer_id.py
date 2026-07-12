"""Add stripe_customer_id to users for secure billing-portal linkage

Revision ID: 004_user_stripe_customer_id
Revises: 003_user_settings
Create Date: 2026-07-12

Persists the durable internal-user -> Stripe customer (cus_...) link so the
billing portal can resolve the caller's customer id server-side instead of
accepting it from the request (closes the BOLA on POST /billing/portal).
"""

import sqlalchemy as sa
from alembic import op

revision = "004_user_stripe_customer_id"
down_revision = "003_user_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
    )
    # Unique so one Stripe customer maps to at most one user; indexed for the
    # portal's reverse lookup by customer id.
    op.create_index(
        "ix_users_stripe_customer_id",
        "users",
        ["stripe_customer_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_users_stripe_customer_id", "users")
    op.drop_column("users", "stripe_customer_id")
