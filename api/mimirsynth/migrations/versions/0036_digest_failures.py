"""digest_failures and digest_retry_at on users: an email summary that keeps failing waits longer each time (#173)

Revision ID: 0036
Revises: 0035
"""
from alembic import op
import sqlalchemy as sa


revision = '0036'
down_revision = '0035'
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    with op.batch_alter_table("users") as b:
        if "digest_failures" not in cols:
            b.add_column(sa.Column("digest_failures", sa.Integer(), nullable=False, server_default="0"))
        if "digest_retry_at" not in cols:
            b.add_column(sa.Column("digest_retry_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_column("digest_retry_at")
        b.drop_column("digest_failures")
