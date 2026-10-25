"""rate_hits: limitador de peticiones persistente y compartido entre procesos

Revision ID: 0018
Revises: 0017
"""
import sqlalchemy as sa
from alembic import op

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("rate_hits"):
        return
    op.create_table(
        "rate_hits",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rate_hits_key_at", "rate_hits", ["key", "at"])


def downgrade() -> None:
    op.drop_table("rate_hits")
