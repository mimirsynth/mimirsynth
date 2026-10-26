"""brain_grants: federación entre brains (lectura con concesión explícita)

Revision ID: 0019
Revises: 0018
"""
import sqlalchemy as sa
from alembic import op

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("brain_grants"):
        return
    op.create_table(
        "brain_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", sa.String(8), nullable=False, server_default="both"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source_brain_id", "target_brain_id"),
    )
    op.create_index("ix_brain_grants_target", "brain_grants", ["target_brain_id"])


def downgrade() -> None:
    op.drop_table("brain_grants")
