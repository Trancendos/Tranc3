"""Complete schema migration

Revision ID: 002_complete
Revises: 001_initial
Create Date: 2025-05-09

This migration covers ALL tables in the schema including those
missing from 001_initial (api_keys, feedback, evolution_events,
quantum_sessions, system_metrics).

Uses cross-dialect compatible types (CHAR(36) for UUIDs, JSON
instead of JSONB/ARRAY) so it works with both PostgreSQL and SQLite.
"""
from alembic import op
import sqlalchemy as sa

revision = '002_complete'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade():
    # ── api_keys (missing from 001_initial) ──
    op.create_table('api_keys',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('key_hash', sa.String(255), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('tier', sa.String(20), nullable=True),
        sa.Column('rate_limit', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('usage_count', sa.BigInteger(), nullable=True),
        sa.Column('permissions', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash'),
    )

    # ── feedback (missing from 001_initial) ──
    op.create_table('feedback',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('message_id', sa.String(36), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('categories', sa.JSON(), nullable=True),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('processed', sa.Boolean(), nullable=True),
        sa.Column('evolution_applied', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── evolution_events (missing from 001_initial) ──
    op.create_table('evolution_events',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('generation', sa.Integer(), nullable=False),
        sa.Column('fitness_score', sa.Float(), nullable=False),
        sa.Column('mutation_rate', sa.Float(), nullable=False),
        sa.Column('population_size', sa.Integer(), nullable=False),
        sa.Column('improvements', sa.JSON(), nullable=True),
        sa.Column('applied_at', sa.DateTime(), nullable=True),
        sa.Column('model_version', sa.String(50), nullable=False),
        sa.Column('metrics_before', sa.JSON(), nullable=True),
        sa.Column('metrics_after', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── quantum_sessions (missing from 001_initial) ──
    op.create_table('quantum_sessions',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('request_id', sa.String(64), nullable=False),
        sa.Column('num_qubits', sa.Integer(), nullable=False),
        sa.Column('circuit_type', sa.String(50), nullable=False),
        sa.Column('phi_score', sa.Float(), nullable=True),
        sa.Column('execution_time_ms', sa.Float(), nullable=False),
        sa.Column('shots', sa.Integer(), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('circuit_data', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── system_metrics (missing from 001_initial) ──
    op.create_table('system_metrics',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('metric_name', sa.String(100), nullable=False),
        sa.Column('metric_value', sa.Float(), nullable=False),
        sa.Column('labels', sa.JSON(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── Add missing columns to users table ──
    # metadata column (renamed from metadata_ to avoid SQLAlchemy reserved word)
    try:
        op.add_column('users', sa.Column('metadata', sa.JSON(), nullable=True))
    except Exception:
        pass  # Column may already exist

    # ── Add missing columns to messages table ──
    try:
        op.add_column('messages', sa.Column('advanced_metrics', sa.JSON(), nullable=True))
    except Exception:
        pass

    try:
        op.add_column('messages', sa.Column('embedding', sa.JSON(), nullable=True))
    except Exception:
        pass

    # ── Add missing columns to conversations table ──
    try:
        op.add_column('conversations', sa.Column('metadata', sa.JSON(), nullable=True))
    except Exception:
        pass

    # ── Create indexes ──
    try:
        op.create_index('ix_system_metrics_name_time', 'system_metrics', ['metric_name', 'recorded_at'])
    except Exception:
        pass


def downgrade():
    op.drop_table('system_metrics')
    op.drop_table('quantum_sessions')
    op.drop_table('evolution_events')
    op.drop_table('feedback')
    op.drop_table('api_keys')
