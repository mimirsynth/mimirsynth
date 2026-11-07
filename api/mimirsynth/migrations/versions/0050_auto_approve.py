"""brains.auto_approve: auto-approval tiers per category of proposals (#299)

Revision ID: 0050
Revises: 0049
"""
from alembic import op
import sqlalchemy as sa


revision = '0050'
down_revision = '0049'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "auto_approve" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("brains")}:
        op.add_column("brains", sa.Column("auto_approve", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("brains", "auto_approve")
