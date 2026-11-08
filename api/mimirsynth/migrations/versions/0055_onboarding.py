"""onboarding_states and recall_logs.token_id: the getting-started checklist on the home screen (#363)

recall_logs.token_id tells a recall made by an agent (through an API token) from a question asked in Ask (a session). The checklist
keeps, per person, when each step was first seen done and whether its card was closed.

Revision ID: 0055
Revises: 0054
"""
import sqlalchemy as sa
from alembic import op

revision = '0055'
down_revision = '0054'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "token_id" not in {c["name"] for c in insp.get_columns("recall_logs")}:
        op.add_column("recall_logs", sa.Column("token_id", sa.Integer(), nullable=True))
    if "onboarding_states" not in set(insp.get_table_names()):
        op.create_table(
            "onboarding_states",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("done", sa.JSON(), nullable=True),
            sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("onboarding_states")
    with op.batch_alter_table("recall_logs") as batch_op:
        batch_op.drop_column("token_id")
