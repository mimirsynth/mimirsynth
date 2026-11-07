"""health_runs: one measurement of a brain's memory health per day (#292)

Revision ID: 0044
Revises: 0043
"""
from alembic import op
import sqlalchemy as sa


revision = '0044'
down_revision = '0043'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "health_runs" not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "health_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("day", sa.Date(), nullable=False),
            sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
            sa.Column("reason", sa.String(16), nullable=False, server_default="daily"),
            sa.Column("metrics", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("job_id", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("brain_id", "day", name="uq_health_runs_day"),
        )
        op.create_index("ix_health_runs_brain_id", "health_runs", ["brain_id"])


def downgrade() -> None:
    op.drop_index("ix_health_runs_brain_id", table_name="health_runs")
    op.drop_table("health_runs")
