"""brains.ocr_vision: a brain reads scanned pages with the vision model of an LLM engine instead of Tesseract (#135)

Revision ID: 0054
Revises: 0053
"""
import sqlalchemy as sa
from alembic import op

revision = '0054'
down_revision = '0053'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "ocr_vision" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("brains")}:
        op.add_column("brains", sa.Column("ocr_vision", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("brains") as batch_op:
        batch_op.drop_column("ocr_vision")
