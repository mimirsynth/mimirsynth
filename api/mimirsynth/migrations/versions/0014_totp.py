"""two-factor (TOTP) and recovery codes

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa


revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    have = {c["name"] for c in insp.get_columns("users")}
    cols = [
        ("totp_secret", sa.Column("totp_secret", sa.Text(), nullable=False, server_default="")),
        ("totp_enabled", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("totp_last_step", sa.Column("totp_last_step", sa.Integer(), nullable=False, server_default="0")),
    ]
    for name, col in cols:
        if name not in have:
            op.add_column("users", col)
    if not insp.has_table("recovery_codes"):
        op.create_table(
            "recovery_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("code_hash", sa.String(64), nullable=False, index=True),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("recovery_codes")
    for c in ("totp_last_step", "totp_enabled", "totp_secret"):
        op.drop_column("users", c)
