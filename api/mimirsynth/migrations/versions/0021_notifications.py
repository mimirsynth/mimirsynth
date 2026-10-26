"""notificaciones: canales, avisos, envíos y lectura

Revision ID: 0021
Revises: 0020
"""
import sqlalchemy as sa
from alembic import op

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = set(sa.inspect(op.get_bind()).get_table_names())
    tz = sa.DateTime(timezone=True)
    if "notify_channels" not in have:
        op.create_table(
            "notify_channels",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(80), nullable=False, unique=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("config", sa.JSON(), nullable=False),
            sa.Column("secret", sa.Text(), nullable=False, server_default=""),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("min_severity", sa.String(8), nullable=False, server_default="warning"),
            sa.Column("events", sa.JSON(), nullable=False),
            sa.Column("created_at", tz, nullable=False, server_default=sa.func.now()),
        )
    if "notifications" not in have:
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("ts", tz, nullable=False, server_default=sa.func.now()),
            sa.Column("last_at", tz, nullable=False, server_default=sa.func.now()),
            sa.Column("event", sa.String(48), nullable=False),
            sa.Column("severity", sa.String(8), nullable=False, server_default="warning"),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="SET NULL"), nullable=True),
            sa.Column("key", sa.String(120), nullable=False, server_default=""),
            sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("resolved_at", tz, nullable=True),
        )
        op.create_index("ix_notifications_ts", "notifications", ["ts"])
        op.create_index("ix_notifications_event_key", "notifications", ["event", "key"])
    if "notify_deliveries" not in have:
        op.create_table(
            "notify_deliveries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("notification_id", sa.Integer(), sa.ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False),
            sa.Column("channel_id", sa.Integer(), sa.ForeignKey("notify_channels.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(8), nullable=False, server_default="alert"),
            sa.Column("status", sa.String(8), nullable=False, server_default="pending"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
            sa.Column("next_try_at", tz, nullable=False, server_default=sa.func.now()),
            sa.Column("sent_at", tz, nullable=True),
            sa.Column("created_at", tz, nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_notify_deliveries_notification_id", "notify_deliveries", ["notification_id"])
        op.create_index("ix_notify_deliveries_channel_id", "notify_deliveries", ["channel_id"])
    if "notify_reads" not in have:
        op.create_table(
            "notify_reads",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("last_id", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    for t in ("notify_reads", "notify_deliveries", "notifications", "notify_channels"):
        op.drop_table(t)
