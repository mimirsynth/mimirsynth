"""conflict_dismissals: groups of possible contradictions marked as «not a contradiction»

Revision ID: 0028
Revises: 0027
"""
from alembic import op
import sqlalchemy as sa


revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "conflict_dismissals" not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "conflict_dismissals",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_uuid", sa.String(64), nullable=False),
            sa.Column("source", sa.String(255), nullable=False, server_default=""),
            sa.Column("relation", sa.String(128), nullable=False),
            sa.Column("target_type", sa.String(255), nullable=False, server_default="Entity"),
            sa.Column("facts", sa.JSON(), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_conflict_dismissals_brain_id", "conflict_dismissals", ["brain_id"])


def downgrade() -> None:
    op.drop_index("ix_conflict_dismissals_brain_id", table_name="conflict_dismissals")
    op.drop_table("conflict_dismissals")
