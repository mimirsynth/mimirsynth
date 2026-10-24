"""vocab aliases

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("vocab_aliases"):
        return
    op.create_table('vocab_aliases',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('brain_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False, server_default='relation'),
    sa.Column('alias', sa.String(length=200), nullable=False),
    sa.Column('canonical', sa.String(length=200), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['brain_id'], ['brains.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('brain_id', 'kind', 'alias')
    )
    op.create_index('ix_vocab_aliases_brain_id', 'vocab_aliases', ['brain_id'])


def downgrade() -> None:
    op.drop_index('ix_vocab_aliases_brain_id', table_name='vocab_aliases')
    op.drop_table('vocab_aliases')
