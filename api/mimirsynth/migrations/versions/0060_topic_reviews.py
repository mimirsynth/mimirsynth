"""topic_reviews: the topic reviews a curator asks for from an entity page (#454)

Each row is one LLM review of everything known about one entity: the state it wrote, the actions that passed validation (each with its
decision and the correction or proposal it became), what was discarded and why, and what did not fit in the calls allowed.

Revision ID: 0060
Revises: 0059
"""
import sqlalchemy as sa
from alembic import op

revision = '0060'
down_revision = '0059'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "topic_reviews" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "topic_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_uuid", sa.String(64), nullable=False),
        sa.Column("name", sa.String(500), nullable=False, server_default=""),
        sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
        sa.Column("prompt_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("state", sa.Text(), nullable=False, server_default=""),
        sa.Column("items", sa.JSON(), nullable=True),
        sa.Column("actions", sa.JSON(), nullable=True),
        sa.Column("discarded", sa.JSON(), nullable=True),
        sa.Column("left_out", sa.JSON(), nullable=True),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_topic_reviews_brain_id", "topic_reviews", ["brain_id"])
    op.create_index("ix_topic_reviews_entity_uuid", "topic_reviews", ["entity_uuid"])
    op.create_index("ix_topic_reviews_status", "topic_reviews", ["status"])


def downgrade() -> None:
    op.drop_table("topic_reviews")
