"""local users: password, status, lockout, external identities, one-time user tokens

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa


revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    have = {c["name"] for c in insp.get_columns("users")}
    cols = [
        ("password_hash", sa.Column("password_hash", sa.Text(), nullable=False, server_default="")),
        ("status", sa.Column("status", sa.String(12), nullable=False, server_default="active")),
        ("must_change_password", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("failed_attempts", sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0")),
        ("locked_until", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True)),
        ("invited_by", sa.Column("invited_by", sa.Integer(), nullable=True)),
    ]
    for name, col in cols:
        if name not in have:
            op.add_column("users", col)
    if not insp.has_table("identities"):
        op.create_table(
            "identities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("provider", sa.String(32), nullable=False, server_default="oidc"),
            sa.Column("sub", sa.String(255), nullable=False),
            sa.Column("email", sa.String(255), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("provider", "sub"),
        )
    if not insp.has_table("user_tokens"):
        op.create_table(
            "user_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("purpose", sa.String(12), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True, index=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    # Los usuarios que ya entraron por OIDC conservan su identidad; los invitados que nunca entraron quedan como «invitado».
    conn.execute(sa.text("INSERT INTO identities (user_id, provider, sub, email) SELECT id, 'oidc', sub, COALESCE(email, '') FROM users WHERE sub IS NOT NULL AND sub <> 'local-admin'"))
    conn.execute(sa.text("UPDATE users SET status = 'invited' WHERE sub IS NULL AND password_hash = ''"))


def downgrade() -> None:
    op.drop_table("user_tokens")
    op.drop_table("identities")
    for c in ("invited_by", "locked_until", "failed_attempts", "must_change_password", "status", "password_hash"):
        op.drop_column("users", c)
