"""recheck the related verdict of pending proposals: «mismo» and its forms no longer count as words of content

Revision ID: 0042
Revises: 0041
"""
from alembic import op
import sqlalchemy as sa


revision = '0042'
down_revision = '0041'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # an empty verdict is «never checked»: the review queue checks those again the next time a curator opens it
    op.execute(sa.text("UPDATE proposals SET related_verdict = '' WHERE status = 'pending'"))


def downgrade() -> None:
    pass  # the verdicts are recomputed on demand; nothing to restore
