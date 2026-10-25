"""oidc_providers: varios proveedores de identidad, cada uno con su política

Importa la configuración OIDC única anterior (Ajustes y variables de entorno) como el proveedor «oidc».

Revision ID: 0016
Revises: 0015
"""
import json

import sqlalchemy as sa
from alembic import op

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None

_KEYS = ("oidc_issuer", "oidc_client_id", "oidc_client_secret", "oidc_scopes", "oidc_trust_unverified_email", "oidc_auto_provision",
         "oidc_allowed_domains", "oidc_groups_claim", "oidc_admin_group", "oidc_group_roles")


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("oidc_providers"):
        op.create_table(
            "oidc_providers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("slug", sa.String(32), nullable=False, unique=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("issuer", sa.Text(), nullable=False, server_default=""),
            sa.Column("client_id", sa.Text(), nullable=False, server_default=""),
            sa.Column("client_secret", sa.Text(), nullable=False, server_default=""),
            sa.Column("scopes", sa.String(255), nullable=False, server_default="openid profile email"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("trust_unverified_email", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("auto_provision", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("allowed_domains", sa.Text(), nullable=False, server_default=""),
            sa.Column("groups_claim", sa.String(64), nullable=False, server_default="groups"),
            sa.Column("admin_group", sa.String(255), nullable=False, server_default=""),
            sa.Column("group_roles", sa.Text(), nullable=False, server_default=""),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    # Configuración anterior: lo guardado en Ajustes manda sobre el entorno.
    from mimirsynth.config import settings
    from mimirsynth.secretbox import seal
    saved: dict = {}
    if insp.has_table("app_settings"):
        for key, value in conn.execute(sa.text("SELECT key, value FROM app_settings WHERE key LIKE 'oidc\\_%' ESCAPE '\\'")):
            v = json.loads(value) if isinstance(value, str) else value
            saved[key] = (v or {}).get("v")
    cfg = {k: saved.get(k) if saved.get(k) is not None else getattr(settings, k) for k in _KEYS}
    if cfg["oidc_issuer"] and cfg["oidc_client_id"] and not conn.execute(sa.text("SELECT 1 FROM oidc_providers WHERE slug = 'oidc'")).first():
        secret = saved.get("oidc_client_secret") or seal(settings.oidc_client_secret)  # lo guardado ya está sellado
        conn.execute(sa.text(
            "INSERT INTO oidc_providers (slug, name, issuer, client_id, client_secret, scopes, enabled, trust_unverified_email, auto_provision, "
            "allowed_domains, groups_claim, admin_group, group_roles, position) VALUES ('oidc', 'OIDC', :issuer, :cid, :secret, :scopes, :en, :trust, :auto, "
            ":domains, :claim, :admin, :roles, 0)"),
            {"issuer": cfg["oidc_issuer"], "cid": cfg["oidc_client_id"], "secret": secret, "scopes": cfg["oidc_scopes"] or "openid profile email", "en": True,
             "trust": cfg["oidc_trust_unverified_email"] == "yes", "auto": cfg["oidc_auto_provision"] == "yes", "domains": cfg["oidc_allowed_domains"] or "",
             "claim": cfg["oidc_groups_claim"] or "groups", "admin": cfg["oidc_admin_group"] or "", "roles": cfg["oidc_group_roles"] or ""})
    if saved:
        conn.execute(sa.text("DELETE FROM app_settings WHERE key LIKE 'oidc\\_%' ESCAPE '\\'"))


def downgrade() -> None:
    op.drop_table("oidc_providers")
