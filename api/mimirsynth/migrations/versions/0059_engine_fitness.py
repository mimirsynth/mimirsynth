"""llm_engines.fitness, decision_engines.fitness: the last full check of a model, kept (#424)

The periodic health check is a cheap ping again; the full check of #420 (the structured output ingestion needs, or the decider's letter
with logprobs) runs on Test, Add and Edit, in the setup wizard, when the engine in use changes and at most once a day. Its result is kept
on the engine and shown in Administration. Empty until the first check after this version.

Revision ID: 0059
Revises: 0058
"""
import sqlalchemy as sa
from alembic import op

revision = '0059'
down_revision = '0058'
branch_labels = None
depends_on = None

TABLES = ("llm_engines", "decision_engines")


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for table in TABLES:
        if "fitness" not in {c["name"] for c in insp.get_columns(table)}:
            op.add_column(table, sa.Column("fitness", sa.JSON(), nullable=True))


def downgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("fitness")
