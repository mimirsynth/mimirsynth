"""api_tokens: expiry, fine scopes and rotation (#133)

Revision ID: 0029
Revises: 0028
"""
from alembic import op
import sqlalchemy as sa


revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None
COLUMNS = (
    ("expires_at", sa.DateTime(timezone=True)),      # empty: never expires (every token made before this migration)
    ("scopes", sa.JSON()),                            # empty: every scope (recall, documents, propose)
    ("replaced_by", sa.Integer()),                    # the token that took its place when it was rotated
    ("expiry_warned_at", sa.DateTime(timezone=True)),  # the notice that it expires soon was already sent
)


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("api_tokens")}
    for name, typ in COLUMNS:
        if name not in have:
            op.add_column("api_tokens", sa.Column(name, typ, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("api_tokens", schema=None) as batch_op:  # batch: SQLite no admite DROP COLUMN en versiones antiguas
        for name, _ in reversed(COLUMNS):
            batch_op.drop_column(name)
