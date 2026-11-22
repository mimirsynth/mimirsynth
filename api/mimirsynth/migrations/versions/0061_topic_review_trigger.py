"""topic_reviews.trigger and .anchors: a review queued by a retirement fact (#455)

`trigger` says who asked for the review: a curator (`manual`) or an ingested fact saying the entity was retired or replaced
(`retirement`); `anchors` holds those facts as they were when the review was queued.

Revision ID: 0061
Revises: 0060
"""
import sqlalchemy as sa
from alembic import op

revision = '0061'
down_revision = '0060'
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("topic_reviews")}
    with op.batch_alter_table("topic_reviews") as t:
        if "trigger" not in have:
            t.add_column(sa.Column("trigger", sa.String(16), nullable=False, server_default="manual"))
        if "anchors" not in have:
            t.add_column(sa.Column("anchors", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("topic_reviews") as t:
        t.drop_column("anchors")
        t.drop_column("trigger")
