"""recheck the related verdict of pending proposals: «duplicate» now needs the proposal to say little more than the fact

Revision ID: 0039
Revises: 0038
"""
from alembic import op
import sqlalchemy as sa


revision = '0039'
down_revision = '0038'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # an empty verdict is «never checked»: the review queue checks those again the next time a curator opens it
    op.execute(sa.text("UPDATE proposals SET related_verdict = '' WHERE status = 'pending'"))


def downgrade() -> None:
    pass  # the verdicts are recomputed on demand; nothing to restore
