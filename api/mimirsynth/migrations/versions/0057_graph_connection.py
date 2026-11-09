"""graph_connection: the graph database saved from Administration → Graph (#358)

One row at most. Until an administrator saves a connection there is none, and the instance keeps using what it used before: the
environment variables or, without them, the bundled FalkorDB.

Revision ID: 0057
Revises: 0056
"""
import sqlalchemy as sa
from alembic import op

revision = '0057'
down_revision = '0056'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "graph_connection" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "graph_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("backend", sa.String(16), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(255), nullable=False, server_default=""),
        sa.Column("password_enc", sa.Text(), nullable=False, server_default=""),
        sa.Column("tls", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("database", sa.String(255), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("graph_connection")
