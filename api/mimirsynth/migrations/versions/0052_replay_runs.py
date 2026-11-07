"""replay_runs: shadow replays of the recall sample with a candidate configuration (#291)

Revision ID: 0052
Revises: 0051
"""
from alembic import op
import sqlalchemy as sa


revision = '0052'
down_revision = '0051'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "replay_runs" not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "replay_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
            sa.Column("params", sa.JSON(), nullable=True),
            sa.Column("size", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("summary", sa.JSON(), nullable=True),
            sa.Column("results", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_replay_runs_brain_id", "replay_runs", ["brain_id"])


def downgrade() -> None:
    op.drop_index("ix_replay_runs_brain_id", table_name="replay_runs")
    op.drop_table("replay_runs")
