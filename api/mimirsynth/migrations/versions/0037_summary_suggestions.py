"""summary_suggestions: better summaries proposed for the entities whose summary is poor, for a curator to approve (#201)

Revision ID: 0037
Revises: 0036
"""
from alembic import op
import sqlalchemy as sa


revision = '0037'
down_revision = '0036'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "summary_suggestions" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "summary_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("entity_uuid", sa.String(64), nullable=False, index=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("facts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(16), nullable=False, server_default=""),
        sa.Column("current", sa.Text(), nullable=False, server_default=""),
        sa.Column("proposed", sa.Text(), nullable=False, server_default=""),
        sa.Column("applied", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending", index=True),
        sa.Column("secret_findings", sa.JSON(), nullable=True),
        sa.Column("edited_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("op_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("summary_suggestions")
