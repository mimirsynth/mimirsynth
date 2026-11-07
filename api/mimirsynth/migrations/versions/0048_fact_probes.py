"""fact_probes and verifier_configs: verifiable facts (#293)

Revision ID: 0048
Revises: 0047
"""
from alembic import op
import sqlalchemy as sa


revision = '0048'
down_revision = '0047'
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = set(sa.inspect(op.get_bind()).get_table_names())
    if "fact_probes" not in have:
        op.create_table(
            "fact_probes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("fact_uuid", sa.String(64), nullable=False),
            sa.Column("verifier", sa.String(64), nullable=False),
            sa.Column("params", sa.JSON(), nullable=True),
            sa.Column("state", sa.String(16), nullable=True),
            sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("brain_id", "fact_uuid", name="uq_fact_probes_fact"),
        )
        op.create_index("ix_fact_probes_brain_id", "fact_probes", ["brain_id"])
    if "verifier_configs" not in have:
        op.create_table(
            "verifier_configs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("verifier", sa.String(64), nullable=False),
            sa.Column("values", sa.JSON(), nullable=True),
            sa.UniqueConstraint("brain_id", "verifier", name="uq_verifier_configs"),
        )
        op.create_index("ix_verifier_configs_brain_id", "verifier_configs", ["brain_id"])


def downgrade() -> None:
    op.drop_index("ix_verifier_configs_brain_id", table_name="verifier_configs")
    op.drop_table("verifier_configs")
    op.drop_index("ix_fact_probes_brain_id", table_name="fact_probes")
    op.drop_table("fact_probes")
