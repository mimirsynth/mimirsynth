"""fact_recalls and fact_archive: when each fact was last recalled, and the facts archived because nobody recalls them (#297)

Revision ID: 0053
Revises: 0052
"""
from alembic import op
import sqlalchemy as sa


revision = '0053'
down_revision = '0052'
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = set(sa.inspect(op.get_bind()).get_table_names())
    if "fact_recalls" not in have:
        op.create_table(
            "fact_recalls",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("fact_uuid", sa.String(64), nullable=False),
            sa.Column("first_recalled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_recalled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint("brain_id", "fact_uuid", name="uq_fact_recalls_fact"),
        )
        op.create_index("ix_fact_recalls_brain_id", "fact_recalls", ["brain_id"])
    if "fact_archive" not in have:
        op.create_table(
            "fact_archive",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("fact_uuid", sa.String(64), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("proposal_id", sa.Integer(), nullable=True),
            sa.Column("reason", sa.String(300), nullable=False, server_default=""),
            sa.UniqueConstraint("brain_id", "fact_uuid", name="uq_fact_archive_fact"),
        )
        op.create_index("ix_fact_archive_brain_id", "fact_archive", ["brain_id"])


def downgrade() -> None:
    op.drop_index("ix_fact_archive_brain_id", table_name="fact_archive")
    op.drop_table("fact_archive")
    op.drop_index("ix_fact_recalls_brain_id", table_name="fact_recalls")
    op.drop_table("fact_recalls")
