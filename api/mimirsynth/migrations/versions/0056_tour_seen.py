"""users.tour_seen_at: the guided tour of the interface on the first visit (#364)

Kept on the server, so a person who skipped or finished the tour does not see it again on another device. People who had already signed
in before this version know the interface: they are marked as having seen it, and can replay it from the help menu.

Revision ID: 0056
Revises: 0055
"""
import sqlalchemy as sa
from alembic import op

revision = '0056'
down_revision = '0055'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "tour_seen_at" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}:
        op.add_column("users", sa.Column("tour_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET tour_seen_at = CURRENT_TIMESTAMP WHERE tour_seen_at IS NULL AND last_login IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("tour_seen_at")
