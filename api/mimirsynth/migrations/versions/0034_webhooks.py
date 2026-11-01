"""webhooks and webhook_events: incoming webhooks that turn external events into proposals (#122)

Revision ID: 0034
Revises: 0033
"""
from alembic import op
import sqlalchemy as sa


revision = '0034'
down_revision = '0033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "webhooks" not in tables:
        op.create_table(
            "webhooks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("key", sa.String(32), nullable=False, unique=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("template", sa.String(32), nullable=False),
            sa.Column("config", sa.JSON(), nullable=False),
            sa.Column("secret_enc", sa.Text(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("auto_approve", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("daily_cap", sa.Integer(), nullable=False, server_default="200"),
            sa.Column("per_minute", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("day", sa.Date(), nullable=True),
            sa.Column("day_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("received", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rejected", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.String(300), nullable=False, server_default=""),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "webhook_events" not in tables:
        op.create_table(
            "webhook_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("webhook_id", sa.Integer(), sa.ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("fingerprint", sa.String(200), nullable=False, server_default=""),
            sa.Column("kind", sa.String(12), nullable=False),
            sa.Column("outcome", sa.String(16), nullable=False),
            sa.Column("title", sa.String(300), nullable=False, server_default=""),
            sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("first_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("proposal_id", sa.Integer(), nullable=True),
            sa.Column("resolution_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_webhook_events_open", "webhook_events", ["webhook_id", "fingerprint", "resolved_at"])


def downgrade() -> None:
    op.drop_index("ix_webhook_events_open", table_name="webhook_events")
    op.drop_table("webhook_events")
    op.drop_table("webhooks")
