"""retype_suggestions: «not an entity → fold into X» and decisions taken one by one (#467)

`fold_uuid`, `fold_name` and `fold_confidence` hold the entity the decider says a doubtful one belongs to; `op_id` is the vocabulary
change that folded it (undone from there); `alone` marks a suggestion a curator decided by itself, not in bulk: those measure how far
the decider's confidence can be trusted before bulk apply is allowed; `chosen_type` is the type a curator applied instead of the
proposed one, which counts as a miss of the decider.

Revision ID: 0062
Revises: 0061
"""
import sqlalchemy as sa
from alembic import op

revision = '0062'
down_revision = '0061'
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("retype_suggestions")}
    with op.batch_alter_table("retype_suggestions") as t:
        if "fold_uuid" not in have:
            t.add_column(sa.Column("fold_uuid", sa.String(64), nullable=False, server_default=""))
        if "fold_name" not in have:
            t.add_column(sa.Column("fold_name", sa.String(500), nullable=False, server_default=""))
        if "fold_confidence" not in have:
            t.add_column(sa.Column("fold_confidence", sa.Float(), nullable=True))
        if "op_id" not in have:
            t.add_column(sa.Column("op_id", sa.Integer(), nullable=True))
        if "alone" not in have:
            t.add_column(sa.Column("alone", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "chosen_type" not in have:
            t.add_column(sa.Column("chosen_type", sa.String(64), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("retype_suggestions") as t:
        for c in ("chosen_type", "alone", "op_id", "fold_confidence", "fold_name", "fold_uuid"):
            t.drop_column(c)
