"""recheck the related verdict of pending proposals: a proposal that adds a word of content to a fact is no longer a duplicate of it

Revision ID: 0040
Revises: 0039
"""
from alembic import op
import sqlalchemy as sa


revision = '0040'
down_revision = '0039'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # an empty verdict is «never checked»: the review queue checks those again the next time a curator opens it
    op.execute(sa.text("UPDATE proposals SET related_verdict = '' WHERE status = 'pending'"))


def downgrade() -> None:
    pass  # the verdicts are recomputed on demand; nothing to restore
