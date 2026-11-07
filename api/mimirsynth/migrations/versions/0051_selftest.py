"""proposals.selftest: whether an ingested proposal's facts come back to a control question (#296)

Revision ID: 0051
Revises: 0050
"""
from alembic import op
import sqlalchemy as sa


revision = '0051'
down_revision = '0050'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "selftest" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("proposals")}:
        op.add_column("proposals", sa.Column("selftest", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("proposals", "selftest")
