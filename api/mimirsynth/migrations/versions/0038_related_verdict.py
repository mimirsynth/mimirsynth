"""related_verdict on proposals: whether the brain already knows something nearly the same, for the review queue's order and batch

Revision ID: 0038
Revises: 0037
"""
from alembic import op
import sqlalchemy as sa


revision = '0038'
down_revision = '0037'
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("proposals")}
    if "related_verdict" not in cols:
        with op.batch_alter_table("proposals") as b:
            b.add_column(sa.Column("related_verdict", sa.String(16), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("proposals") as b:
        b.drop_column("related_verdict")
