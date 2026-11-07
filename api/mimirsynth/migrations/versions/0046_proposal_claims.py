"""proposals.claims: structured claims compared with what the brain knows when sent, and what approving them applied (#295)

Revision ID: 0046
Revises: 0045
"""
from alembic import op
import sqlalchemy as sa


revision = '0046'
down_revision = '0045'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "claims" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("proposals")}:
        op.add_column("proposals", sa.Column("claims", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("proposals", "claims")
