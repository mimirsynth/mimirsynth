"""proposals.kind and proposals.correction: fact corrections proposed by agents (#109)

Revision ID: 0027
Revises: 0026
"""
from alembic import op
import sqlalchemy as sa


revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("proposals")}
    if "kind" not in have:
        op.add_column("proposals", sa.Column("kind", sa.String(16), nullable=False, server_default="memory"))
    if "correction" not in have:
        op.add_column("proposals", sa.Column("correction", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("proposals", schema=None) as batch_op:  # batch: older SQLite versions have no DROP COLUMN
        batch_op.drop_column("correction")
        batch_op.drop_column("kind")
