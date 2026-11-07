"""proposals.origin and api_tokens.max_trust: ranking by source trust (#298)

Revision ID: 0049
Revises: 0048
"""
from alembic import op
import sqlalchemy as sa


revision = '0049'
down_revision = '0048'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "origin" not in {c["name"] for c in insp.get_columns("proposals")}:
        op.add_column("proposals", sa.Column("origin", sa.String(8), nullable=False, server_default=""))
    if "max_trust" not in {c["name"] for c in insp.get_columns("api_tokens")}:
        op.add_column("api_tokens", sa.Column("max_trust", sa.String(8), nullable=False, server_default="agent"))


def downgrade() -> None:
    op.drop_column("api_tokens", "max_trust")
    op.drop_column("proposals", "origin")
