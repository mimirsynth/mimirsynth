"""api_tokens.news_seen_at: desde cuándo cuenta `whats_new` del MCP cuando el agente no da fecha (#108)

Revision ID: 0026
Revises: 0025
"""
from alembic import op
import sqlalchemy as sa


revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "news_seen_at" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("api_tokens")}:
        op.add_column("api_tokens", sa.Column("news_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("api_tokens", schema=None) as batch_op:  # batch: SQLite no admite DROP COLUMN en versiones antiguas
        batch_op.drop_column("news_seen_at")
