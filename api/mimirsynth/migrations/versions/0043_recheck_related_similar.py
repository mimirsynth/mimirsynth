"""recheck the related verdict of pending proposals: a proposal mostly new against a current fact is no longer «similar»

Revision ID: 0043
Revises: 0042
"""
from alembic import op
import sqlalchemy as sa


revision = '0043'
down_revision = '0042'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # an empty verdict is «never checked»: the review queue checks those again the next time a curator opens it
    op.execute(sa.text("UPDATE proposals SET related_verdict = '' WHERE status = 'pending'"))


def downgrade() -> None:
    pass  # the verdicts are recomputed on demand; nothing to restore
