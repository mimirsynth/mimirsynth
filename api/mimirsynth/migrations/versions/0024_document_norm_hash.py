"""documents.norm_hash con índice: la huella del texto con la que se detectan duplicados (#117)

Revision ID: 0024
Revises: 0023
"""
from alembic import op
import sqlalchemy as sa


revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "norm_hash" not in {c["name"] for c in insp.get_columns("documents")}:
        op.add_column("documents", sa.Column("norm_hash", sa.String(64), nullable=True))
    if "ix_documents_norm_hash" not in {i["name"] for i in insp.get_indexes("documents")}:
        op.create_index("ix_documents_norm_hash", "documents", ["norm_hash"])


def downgrade() -> None:
    op.drop_index("ix_documents_norm_hash", table_name="documents")
    with op.batch_alter_table("documents", schema=None) as batch_op:  # batch: SQLite no admite DROP COLUMN en versiones antiguas
        batch_op.drop_column("norm_hash")
