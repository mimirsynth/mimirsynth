"""consultas de referencia por brain y sus ejecuciones (#115)

Revision ID: 0024
Revises: 0023
"""
from alembic import op
import sqlalchemy as sa


revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = set(sa.inspect(op.get_bind()).get_table_names())
    if "ref_queries" not in have:
        op.create_table(
            "ref_queries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("query", sa.Text(), nullable=False),
            sa.Column("expect", sa.JSON(), nullable=False),
            sa.Column("avoid", sa.JSON(), nullable=False),
            sa.Column("docs", sa.Boolean(), nullable=True),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_ref_queries_brain_id", "ref_queries", ["brain_id"])
    if "ref_runs" not in have:
        op.create_table(
            "ref_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
            sa.Column("reason", sa.String(32), nullable=False, server_default="manual"),
            sa.Column("params", sa.JSON(), nullable=False),
            sa.Column("summary", sa.JSON(), nullable=True),
            sa.Column("results", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("job_id", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_ref_runs_brain_id", "ref_runs", ["brain_id"])


def downgrade() -> None:
    op.drop_index("ix_ref_runs_brain_id", table_name="ref_runs")
    op.drop_table("ref_runs")
    op.drop_index("ix_ref_queries_brain_id", table_name="ref_queries")
    op.drop_table("ref_queries")
