"""ai_usage, ai_prices and brains.ai_budget: AI consumption per brain, with an optional budget (#132)

Revision ID: 0031
Revises: 0030
"""
from alembic import op
import sqlalchemy as sa


revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "ai_usage" not in tables:
        op.create_table(
            "ai_usage",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("day", sa.Date(), nullable=False),
            sa.Column("brain_id", sa.Integer(), nullable=False, server_default="0"),  # 0: not on behalf of a brain (engine tests, model change)
            sa.Column("kind", sa.String(16), nullable=False),     # llm | embedding | decision
            sa.Column("model", sa.String(255), nullable=False),
            sa.Column("purpose", sa.String(32), nullable=False),  # extraction | decider | recall | documents | index | …
            sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("errors_429", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("errors_5xx", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("errors_other", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("completion_tokens", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("estimated_calls", sa.Integer(), nullable=False, server_default="0"),  # calls whose tokens were estimated (no `usage`)
            sa.Column("peak_rpm", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("day", "brain_id", "kind", "model", "purpose", name="uq_ai_usage_key"),
        )
        op.create_index("ix_ai_usage_brain_day", "ai_usage", ["brain_id", "day"])
    if "ai_prices" not in tables:
        op.create_table(
            "ai_prices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("model", sa.String(255), nullable=False),
            sa.Column("price_in", sa.Float(), nullable=False, server_default="0"),   # per million input tokens
            sa.Column("price_out", sa.Float(), nullable=False, server_default="0"),  # per million output tokens
            sa.UniqueConstraint("kind", "model", name="uq_ai_prices_key"),
        )
    if "ai_budget" not in {c["name"] for c in insp.get_columns("brains")}:
        op.add_column("brains", sa.Column("ai_budget", sa.JSON(), nullable=True))  # {limit, unit: tokens | cost, pause}


def downgrade() -> None:
    with op.batch_alter_table("brains", schema=None) as batch_op:
        batch_op.drop_column("ai_budget")
    op.drop_table("ai_prices")
    op.drop_index("ix_ai_usage_brain_day", table_name="ai_usage")
    op.drop_table("ai_usage")
