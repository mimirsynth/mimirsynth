"""recall_logs, recall_ratings and brains.recall_query_text: ratings of what the recall returns (#110)

Revision ID: 0033
Revises: 0032
"""
from alembic import op
import sqlalchemy as sa


revision = '0033'
down_revision = '0032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "recall_logs" not in tables:
        op.create_table(
            "recall_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("rid", sa.String(32), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("query_hash", sa.String(64), nullable=False),
            sa.Column("query_len", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("query_text", sa.Text(), nullable=True),  # only if the brain keeps it, and only for a short time
            sa.Column("items", sa.JSON(), nullable=False),      # [{kind, id, sim, origin, text}] what it returned
        )
        op.create_index("ix_recall_logs_brain_created", "recall_logs", ["brain_id", "created_at"])
    if "recall_ratings" not in tables:
        op.create_table(
            "recall_ratings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("log_id", sa.Integer(), sa.ForeignKey("recall_logs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(8), nullable=False),     # fact | chunk | doc
            sa.Column("item_id", sa.String(80), nullable=False),
            sa.Column("similarity", sa.Float(), nullable=True),
            sa.Column("rating", sa.String(12), nullable=False),  # useful | irrelevant | incorrect
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("proposal_id", sa.Integer(), nullable=True),  # the correction an «incorrect» fact opened
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("log_id", "kind", "item_id", "user_id", name="uq_recall_ratings_item"),
        )
        op.create_index("ix_recall_ratings_brain_created", "recall_ratings", ["brain_id", "created_at"])
    if "recall_query_text" not in {c["name"] for c in insp.get_columns("brains")}:
        op.add_column("brains", sa.Column("recall_query_text", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("brains", schema=None) as batch_op:
        batch_op.drop_column("recall_query_text")
    op.drop_index("ix_recall_ratings_brain_created", table_name="recall_ratings")
    op.drop_table("recall_ratings")
    op.drop_index("ix_recall_logs_brain_created", table_name="recall_logs")
    op.drop_table("recall_logs")
