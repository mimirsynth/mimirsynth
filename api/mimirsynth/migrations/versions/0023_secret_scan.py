"""detector de secretos: política por brain y hallazgos de cada propuesta (#116)

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa


revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    brains = {c["name"] for c in insp.get_columns("brains")}
    if "secret_mode" not in brains:
        op.add_column("brains", sa.Column("secret_mode", sa.String(8), nullable=False, server_default="mask"))
    if "secret_allow" not in brains:
        op.add_column("brains", sa.Column("secret_allow", sa.Text(), nullable=False, server_default=""))
    if "secret_findings" not in {c["name"] for c in insp.get_columns("proposals")}:
        op.add_column("proposals", sa.Column("secret_findings", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("proposals", schema=None) as batch_op:  # batch: SQLite no admite DROP COLUMN en versiones antiguas
        batch_op.drop_column("secret_findings")
    with op.batch_alter_table("brains", schema=None) as batch_op:
        batch_op.drop_column("secret_allow")
        batch_op.drop_column("secret_mode")
