"""digest_subscriptions, and the hour, weekday and time zone of each person's periodic summary (#128)

Revision ID: 0035
Revises: 0034
"""
from alembic import op
import sqlalchemy as sa


revision = '0035'
down_revision = '0034'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("users")}
    with op.batch_alter_table("users") as b:
        if "digest_hour" not in cols:
            b.add_column(sa.Column("digest_hour", sa.Integer(), nullable=False, server_default="8"))
        if "digest_weekday" not in cols:
            b.add_column(sa.Column("digest_weekday", sa.Integer(), nullable=False, server_default="0"))
        if "timezone" not in cols:
            b.add_column(sa.Column("timezone", sa.String(64), nullable=False, server_default=""))
    if "digest_subscriptions" not in set(insp.get_table_names()):
        op.create_table(
            "digest_subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("brain_id", sa.Integer(), sa.ForeignKey("brains.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("frequency", sa.String(8), nullable=False),
            sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_counts", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "brain_id"),
        )


def downgrade() -> None:
    op.drop_table("digest_subscriptions")
    with op.batch_alter_table("users") as b:
        b.drop_column("timezone")
        b.drop_column("digest_weekday")
        b.drop_column("digest_hour")
