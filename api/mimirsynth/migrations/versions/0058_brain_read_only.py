"""brains.read_only: a graph adopted as a brain only to be read (#359)

An existing Graphiti graph can be adopted as a brain that MimirSynth reads but never writes: no proposals, no ingest, no curation and no
embedding model change touch it. Every brain before this version is a full one.

Revision ID: 0058
Revises: 0057
"""
import sqlalchemy as sa
from alembic import op

revision = '0058'
down_revision = '0057'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "read_only" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("brains")}:
        op.add_column("brains", sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("brains") as batch_op:
        batch_op.drop_column("read_only")
