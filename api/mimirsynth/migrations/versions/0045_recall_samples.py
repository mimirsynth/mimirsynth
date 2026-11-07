"""recall_samples and brains.replay: an opt-in sample of real recalls to replay against another configuration (#291)

Revision ID: 0045
Revises: 0044
"""
from alembic import op
import sqlalchemy as sa


revision = '0045'
down_revision = '0044'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "replay" not in {c["name"] for c in insp.get_columns("brains")}:
        op.add_column("brains", sa.Column("replay", sa.JSON(), nullable=True))
    if "recall_samples" not in set(insp.get_table_names()):
        op.create_table(
            "recall_samples",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("via", sa.String(8), nullable=False, server_default="http"),
            sa.Column("query", sa.Text(), nullable=False),
            sa.Column("params", sa.JSON(), nullable=True),
            sa.Column("items", sa.JSON(), nullable=True),
            sa.Column("masked", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_recall_samples_brain_id", "recall_samples", ["brain_id"])
        op.create_index("ix_recall_samples_created_at", "recall_samples", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_recall_samples_created_at", table_name="recall_samples")
    op.drop_index("ix_recall_samples_brain_id", table_name="recall_samples")
    op.drop_table("recall_samples")
    op.drop_column("brains", "replay")
