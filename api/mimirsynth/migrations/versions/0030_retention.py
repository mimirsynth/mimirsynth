"""brains.retention and proposals.purged_at: per-brain retention periods (#137)

Revision ID: 0030
Revises: 0029
"""
from alembic import op
import sqlalchemy as sa


revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "retention" not in {c["name"] for c in insp.get_columns("brains")}:
        op.add_column("brains", sa.Column("retention", sa.JSON(), nullable=True))  # empty: the instance's periods
    if "purged_at" not in {c["name"] for c in insp.get_columns("proposals")}:
        op.add_column("proposals", sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("proposals", schema=None) as batch_op:  # batch: SQLite no admite DROP COLUMN en versiones antiguas
        batch_op.drop_column("purged_at")
    with op.batch_alter_table("brains", schema=None) as batch_op:
        batch_op.drop_column("retention")
