"""fact_confirmations: when a person last confirmed that a fact is still true (#114)

Revision ID: 0032
Revises: 0031
"""
from alembic import op
import sqlalchemy as sa


revision = '0032'
down_revision = '0031'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "fact_confirmations" not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "fact_confirmations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("fact_uuid", sa.String(64), nullable=False),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.UniqueConstraint("brain_id", "fact_uuid", name="uq_fact_confirmations_fact"),
        )
        op.create_index("ix_fact_confirmations_brain_id", "fact_confirmations", ["brain_id"])


def downgrade() -> None:
    op.drop_index("ix_fact_confirmations_brain_id", table_name="fact_confirmations")
    op.drop_table("fact_confirmations")
