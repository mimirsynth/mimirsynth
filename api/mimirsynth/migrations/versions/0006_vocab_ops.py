"""vocab ops

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("vocab_ops"):
        return
    op.create_table('vocab_ops',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('brain_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('summary', sa.String(length=300), nullable=False, server_default=''),
    sa.Column('detail', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False, server_default='applied'),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['brain_id'], ['brains.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_vocab_ops_brain_id', 'vocab_ops', ['brain_id'])


def downgrade() -> None:
    op.drop_index('ix_vocab_ops_brain_id', table_name='vocab_ops')
    op.drop_table('vocab_ops')
