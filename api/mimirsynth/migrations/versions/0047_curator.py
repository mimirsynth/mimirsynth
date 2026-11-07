"""the scheduled curator (#300): curator_runs, brains.curator and proposals.category

Revision ID: 0047
Revises: 0046
"""
from alembic import op
import sqlalchemy as sa


revision = '0047'
down_revision = '0046'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "curator" not in {c["name"] for c in insp.get_columns("brains")}:
        op.add_column("brains", sa.Column("curator", sa.JSON(), nullable=True))
    if "category" not in {c["name"] for c in insp.get_columns("proposals")}:
        op.add_column("proposals", sa.Column("category", sa.String(32), nullable=False, server_default=""))
    if "curator_runs" not in set(insp.get_table_names()):
        op.create_table(
            "curator_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("day", sa.Date(), nullable=False),
            sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
            sa.Column("reason", sa.String(16), nullable=False, server_default="daily"),
            sa.Column("findings", sa.JSON(), nullable=True),
            sa.Column("proposals", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("job_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("brain_id", "day", name="uq_curator_runs_day"),
        )
        op.create_index("ix_curator_runs_brain_id", "curator_runs", ["brain_id"])


def downgrade() -> None:
    op.drop_index("ix_curator_runs_brain_id", table_name="curator_runs")
    op.drop_table("curator_runs")
    op.drop_column("proposals", "category")
    op.drop_column("brains", "curator")
