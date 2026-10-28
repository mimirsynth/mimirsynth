"""oidc_providers.default_roles: acceso inicial de quien se da de alta solo

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa


revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("oidc_providers")}
    if "default_roles" not in have:
        op.add_column("oidc_providers", sa.Column("default_roles", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("oidc_providers", schema=None) as batch_op:  # batch: SQLite no admite DROP COLUMN en versiones antiguas
        batch_op.drop_column("default_roles")
