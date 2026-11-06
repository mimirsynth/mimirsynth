"""recheck the related verdict of pending proposals: words are now compared without accents and by their stem, and numbers count

Revision ID: 0041
Revises: 0040
"""
from alembic import op
import sqlalchemy as sa


revision = '0041'
down_revision = '0040'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # an empty verdict is «never checked»: the review queue checks those again the next time a curator opens it
    op.execute(sa.text("UPDATE proposals SET related_verdict = '' WHERE status = 'pending'"))


def downgrade() -> None:
    pass  # the verdicts are recomputed on demand; nothing to restore
