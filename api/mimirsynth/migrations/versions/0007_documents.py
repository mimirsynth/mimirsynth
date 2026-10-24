"""documents and doc_sources

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("doc_sources"):
        op.create_table('doc_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('brain_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('sync_interval', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='idle'),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['brain_id'], ['brains.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('brain_id', 'name'))
        op.create_index('ix_doc_sources_brain_id', 'doc_sources', ['brain_id'])
    if not insp.has_table("documents"):
        op.create_table('documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('brain_id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.String(length=500), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('filename', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('url', sa.Text(), nullable=False, server_default=''),
        sa.Column('mime', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('size', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('sha256', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('storage_ref', sa.Text(), nullable=False, server_default=''),
        sa.Column('text_ref', sa.Text(), nullable=False, server_default=''),
        sa.Column('source_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='pending'),
        sa.Column('error', sa.Text(), nullable=False, server_default=''),
        sa.Column('chunks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('meta', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['brain_id'], ['brains.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['doc_sources.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', 'external_id'))
        op.create_index('ix_documents_brain_id', 'documents', ['brain_id'])
        op.create_index('ix_documents_source_id', 'documents', ['source_id'])
        op.create_index('ix_documents_status', 'documents', ['status'])


def downgrade() -> None:
    op.drop_table('documents')
    op.drop_table('doc_sources')
