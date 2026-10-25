"""role_grants: roles concedidos por grupo, para poder retirarlos

Los roles que ya existían se consideran manuales (nunca se retiran solos).

Revision ID: 0017
Revises: 0016
"""
import sqlalchemy as sa
from alembic import op

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("role_grants"):
        return
    op.create_table(
        "role_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("group", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=True),
        sa.Column("role", sa.String(16), nullable=False, server_default=""),
        sa.Column("previous_role", sa.String(16), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("role_grants")
