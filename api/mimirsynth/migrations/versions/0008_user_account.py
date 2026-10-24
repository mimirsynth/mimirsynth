"""user account fields (display name, avatar, session epoch)

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None

COLS = [
    ("display_name", sa.Column("display_name", sa.String(length=80), nullable=False, server_default="")),
    ("picture_url", sa.Column("picture_url", sa.Text(), nullable=False, server_default="")),
    ("avatar_ref", sa.Column("avatar_ref", sa.Text(), nullable=False, server_default="")),
    ("avatar_at", sa.Column("avatar_at", sa.DateTime(timezone=True), nullable=True)),
    ("session_epoch", sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="0")),
]


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    with op.batch_alter_table("users") as b:
        for name, col in COLS:
            if name not in have:
                b.add_column(col)


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        for name, _ in COLS:
            b.drop_column(name)
