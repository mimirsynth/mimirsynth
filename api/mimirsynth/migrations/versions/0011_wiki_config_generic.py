"""wiki sources: generic adapter config (settings + sealed secrets)

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not sa.inspect(conn).has_table("doc_sources"):
        return
    rows = conn.execute(sa.text("select id, config from doc_sources where kind = 'wiki'")).fetchall()
    import json
    for rid, cfg in rows:
        cfg = json.loads(cfg) if isinstance(cfg, str) else dict(cfg or {})
        if "settings" in cfg or "base_url" not in cfg:
            continue
        new = {"adapter": cfg.get("adapter", "outline"), "settings": {"base_url": cfg["base_url"]},
               "secrets": {"api_key": cfg["api_key_enc"]} if cfg.get("api_key_enc") else {}, "collection_ids": cfg.get("collection_ids", [])}
        conn.execute(sa.text("update doc_sources set config = :c where id = :i").bindparams(sa.bindparam("c", type_=sa.JSON)), {"c": new, "i": rid})


def downgrade() -> None:
    pass
