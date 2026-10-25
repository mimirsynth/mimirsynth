"""users.locale: idioma elegido por cada persona

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa


revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    if "locale" not in have:
        op.add_column("users", sa.Column("locale", sa.String(5), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("users", "locale")
