"""Usuarios propios: asistente de primer arranque, invitaciones, contraseña, bloqueo, administración y recuperación."""
import re

import pytest
from fastapi.testclient import TestClient

from test_control import client  # noqa: F401

from mimirsynth import auth, mail, ratelimit
from mimirsynth.config import settings
from mimirsynth.main import app
from mimirsynth.models import User
from mimirsynth.store import _factory

PW = "correct-horse-battery-1"


@pytest.fixture()
def local(monkeypatch):
    """Instancia con autenticación real y sin administradores (primer arranque)."""
    from sqlalchemy import update
    monkeypatch.setattr(settings, "auth_mode", "local")
    ratelimit.reset()
    with _factory()() as db:  # los administradores de otras pruebas no cuentan aquí
        db.execute(update(User).where(User.sub.is_distinct_from("local-admin")).values(is_admin=False))
        db.commit()
        auth.ensure_setup_token(db)
    yield


def _provider(slug="oidc", **kw):
    """Crea (o reemplaza) un proveedor OIDC de pruebas directamente en la base de datos."""
    from mimirsynth.models import OidcProvider
    with _factory()() as db:
        db.query(OidcProvider).filter(OidcProvider.slug == slug).delete()
        db.add(OidcProvider(slug=slug, name=kw.pop("name", slug.upper()), issuer="https://id.example.com", client_id="cid", **kw)); db.commit()
        return db.query(OidcProvider).filter(OidcProvider.slug == slug).one()


def _admin(c):
    r = c.post("/api/auth/setup", json={"code": auth._SETUP_TOKEN, "email": f"root@example.com", "name": "Root", "password": PW})
    assert r.status_code == 200, r.text


def _token(link: str) -> str:
    return re.search(r"/acceso/(.+)$", link).group(1)


def test_setup_then_invite_login_lockout_and_admin_guards(client, local, monkeypatch):  # noqa: F811
    assert client.get("/api/auth/options").json()["setup"] is True
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/auth/setup", json={"code": "mal", "email": "a@b.co", "name": "A", "password": PW}).status_code == 403
    assert client.post("/api/auth/setup", json={"code": auth._SETUP_TOKEN, "email": "a@b.co", "name": "A", "password": "corta"}).status_code == 422
    _admin(client)
    assert client.get("/api/me").json()["is_admin"] is True
    assert client.get("/api/auth/options").json()["setup"] is False
    assert client.post("/api/auth/setup", json={"code": "x", "email": "z@z.co", "name": "Z", "password": PW}).status_code == 409

    # invitación por enlace
    r = client.post("/api/admin/users", json={"email": "ana@example.com", "name": "Ana", "mode": "invite"})
    assert r.status_code == 201 and r.json()["status"] == "invited" and r.json()["emailed"] is False
    tok = _token(r.json()["link"])
    ana = TestClient(app)
    assert ana.get(f"/api/auth/token/{tok}").json()["email"] == "ana@example.com"
    assert ana.post("/api/auth/accept", json={"token": tok, "password": "ana@example"}).status_code == 422  # contiene el email
    assert ana.post("/api/auth/accept", json={"token": tok, "password": PW + "x"}).status_code == 200
    assert ana.get("/api/auth/token/" + tok).status_code == 404  # un solo uso
    assert ana.get("/api/me").json()["email"] == "ana@example.com"
    assert ana.get("/api/admin/users").status_code == 403  # no es administradora

    # bloqueo tras intentos fallidos, y desbloqueo por el administrador
    bad = TestClient(app)
    for _ in range(settings.login_max_attempts):
        assert bad.post("/api/auth/login", json={"email": "ana@example.com", "password": "incorrecta-12345"}).status_code == 401
    assert bad.post("/api/auth/login", json={"email": "ana@example.com", "password": PW + "x"}).status_code == 401
    uid = [u for u in client.get("/api/admin/users").json()["items"] if u["email"] == "ana@example.com"][0]["id"]
    assert client.post(f"/api/admin/users/{uid}/unlock").status_code == 200
    assert bad.post("/api/auth/login", json={"email": "ana@example.com", "password": PW + "x"}).status_code == 200

    # roles y pertenencias
    client.post("/api/brains", json={"slug": "equipo-u", "name": "Equipo U"})
    assert client.put(f"/api/admin/users/{uid}/memberships", json={"slug": "equipo-u", "role": "curator"}).status_code == 200
    assert client.get(f"/api/admin/users/{uid}").json()["memberships"][0]["role"] == "curator"
    assert client.patch(f"/api/admin/users/{uid}", json={"is_admin": True}).json()["is_admin"] is True
    # protecciones: ni uno mismo ni el último administrador
    me = client.get("/api/me").json()["id"]
    assert client.patch(f"/api/admin/users/{me}", json={"is_admin": False}).status_code == 409
    assert client.delete(f"/api/admin/users/{me}").status_code == 409
    assert client.patch(f"/api/admin/users/{uid}", json={"is_admin": False}).status_code == 200

    # deshabilitar corta la sesión; eliminar anonimiza y libera el email
    assert client.patch(f"/api/admin/users/{uid}", json={"status": "disabled"}).status_code == 200
    assert bad.get("/api/me").status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"email": "ana@example.com", "password": PW + "x"}).status_code == 401
    assert client.delete(f"/api/admin/users/{uid}").status_code == 200
    assert all(u["email"] != "ana@example.com" for u in client.get("/api/admin/users").json()["items"])
    assert client.post("/api/admin/users", json={"email": "ana@example.com", "mode": "invite"}).status_code == 201  # puede volver a invitarse


def test_temp_password_forced_change_and_forgot_by_mail(client, local, monkeypatch):  # noqa: F811
    _admin(client)
    r = client.post("/api/admin/users", json={"email": "luis@example.com", "name": "Luis", "mode": "password", "password": "temporal-2026-xyz"})
    assert r.status_code == 201
    luis = TestClient(app)
    assert luis.post("/api/auth/login", json={"email": "luis@example.com", "password": "temporal-2026-xyz"}).json()["must_change_password"] is True
    assert luis.post("/api/me/password", json={"current": "mala", "new": PW + "y"}).status_code == 403
    assert luis.post("/api/me/password", json={"current": "temporal-2026-xyz", "new": PW + "y"}).status_code == 200
    assert luis.get("/api/me").json()["must_change_password"] is False  # la sesión actual sigue valiendo

    # recuperación: sin SMTP no se envía nada; con SMTP llega el enlace
    sent = []
    assert luis.post("/api/auth/forgot", json={"email": "luis@example.com"}).json() == {"ok": True}
    monkeypatch.setattr(mail, "configured", lambda: True)
    monkeypatch.setattr(mail, "try_send", lambda to, subject, body: sent.append((to, body)) or True)
    assert luis.post("/api/auth/forgot", json={"email": "luis@example.com"}).json() == {"ok": True}
    assert luis.post("/api/auth/forgot", json={"email": "nadie@example.com"}).json() == {"ok": True}  # misma respuesta
    assert len(sent) == 1 and sent[0][0] == "luis@example.com"
    tok = _token(re.search(r"https?://\S+/acceso/\S+", sent[0][1]).group(0))
    fresh = TestClient(app)
    assert fresh.post("/api/auth/accept", json={"token": tok, "password": "otra-clave-distinta-9"}).status_code == 200
    assert TestClient(app).post("/api/auth/login", json={"email": "luis@example.com", "password": "otra-clave-distinta-9"}).status_code == 200
    assert luis.get("/api/me").status_code == 401  # restablecer cierra las demás sesiones


def test_oidc_only_for_invited(client, local, monkeypatch):  # noqa: F811
    """Un email que nadie ha invitado no obtiene cuenta aunque el proveedor lo conozca."""
    import asyncio
    from types import SimpleNamespace

    class FakeOidc:
        async def authorize_access_token(self, request):
            return {"userinfo": {"sub": "sub-1", "email": "intruso@example.com", "email_verified": True, "name": "X"}}
    monkeypatch.setattr(auth, "_oidc", lambda p: FakeOidc())
    _provider()
    _admin(client)
    r = client.get("/api/auth/callback", follow_redirects=False)
    assert r.status_code == 307 and "auth_error=not_invited" in r.headers["location"]
    client.post("/api/admin/users", json={"email": "invitada@example.com", "mode": "invite"})

    class FakeOk(FakeOidc):
        async def authorize_access_token(self, request):
            return {"userinfo": {"sub": "sub-2", "email": "invitada@example.com", "email_verified": True, "name": "Inv"}}
    monkeypatch.setattr(auth, "_oidc", lambda p: FakeOk())
    c2 = TestClient(app)
    r = c2.get("/api/auth/callback", follow_redirects=False)
    assert r.headers["location"] == "/" and c2.get("/api/me").json()["email"] == "invitada@example.com"


def _code(secret):
    from mimirsynth import totp
    import time
    return totp._code(secret, int(time.time() // totp.STEP))


def test_totp_rfc_vector_and_replay():
    from mimirsynth import totp
    import base64
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    assert totp._code(secret, 59 // 30) == "287082"  # vector de la RFC 6238 (los 6 últimos dígitos de 94287082)
    assert totp.verify(secret, "287082", now=59) == 1
    assert totp.verify(secret, "287082", last_step=1, now=59) is None  # un código no se reutiliza
    assert totp.verify(secret, "12345", now=59) is None


def test_two_factor_enrol_login_recovery_required_and_reset(client, local):  # noqa: F811
    from mimirsynth import mfa, passwords
    from mimirsynth.models import RecoveryCode
    _admin(client)
    assert passwords.check_policy("abcdefghijklmnop") == "es una secuencia (abcdef, 123456…)"
    # alta
    assert client.post("/api/me/2fa/begin", json={"password": "mal"}).status_code == 403
    r = client.post("/api/me/2fa/begin", json={"password": PW}); assert r.status_code == 200, r.text
    secret = r.json()["secret"]; assert "<svg" in r.json()["svg"] and r.json()["uri"].startswith("otpauth://totp/")
    assert client.post("/api/me/2fa/enable", json={"code": "000000"}).status_code == 422
    r = client.post("/api/me/2fa/enable", json={"code": _code(secret)}); assert r.status_code == 200, r.text
    codes = r.json()["recovery_codes"]; assert len(codes) == 10
    assert client.get("/api/me/2fa").json() == {"enabled": True, "recovery_left": 10, "required": False, "has_password": True}

    # login en dos pasos
    ratelimit.reset()
    c2 = TestClient(app)
    r = c2.post("/api/auth/login", json={"email": "root@example.com", "password": PW}); assert r.json() == {"ok": True, "mfa": True, "methods": ["totp"]}
    assert c2.get("/api/me").status_code == 401  # aún sin sesión
    assert c2.post("/api/auth/mfa", json={"code": "123456"}).status_code == 401
    import time
    from mimirsynth import totp
    nxt = totp._code(secret, int(time.time() // totp.STEP) + 1)  # el intervalo actual ya se usó al activar
    assert c2.post("/api/auth/mfa", json={"code": nxt}).status_code == 200
    assert c2.get("/api/me").json()["totp_enabled"] is True
    # código de recuperación: sirve una vez
    c3 = TestClient(app)
    c3.post("/api/auth/login", json={"email": "root@example.com", "password": PW})
    assert c3.post("/api/auth/mfa", json={"code": codes[0]}).status_code == 200
    c4 = TestClient(app)
    c4.post("/api/auth/login", json={"email": "root@example.com", "password": PW})
    assert c4.post("/api/auth/mfa", json={"code": codes[0]}).status_code == 401
    assert client.get("/api/me/2fa").json()["recovery_left"] == 9
    # sin permiso previo no hay segundo paso
    assert TestClient(app).post("/api/auth/mfa", json={"code": nxt}).status_code == 401

    # exigir a todos: quien no lo tenga solo puede llegar a «Mi cuenta»
    client.put("/api/settings/require_2fa", json={"value": "yes"})
    r = client.post("/api/admin/users", json={"email": "bea@example.com", "name": "Bea", "mode": "invite"})
    bea = TestClient(app)
    bea.post("/api/auth/accept", json={"token": _token(r.json()["link"]), "password": PW + "y"})
    assert bea.get("/api/me").json()["must_setup_2fa"] is True
    assert bea.get("/api/brains").status_code == 403
    assert bea.get("/api/me/2fa").status_code == 200
    s = bea.post("/api/me/2fa/begin", json={"password": PW + "y"}).json()["secret"]
    assert bea.post("/api/me/2fa/enable", json={"code": _code(s)}).status_code == 200
    assert bea.get("/api/brains").status_code == 200
    assert client.post("/api/me/2fa/disable", json={"password": PW, "code": codes[1]}).status_code == 409  # exigido
    client.put("/api/settings/require_2fa", json={"value": "no"})

    # el administrador lo quita a quien perdió el móvil
    uid = [u["id"] for u in client.get("/api/admin/users").json()["items"] if u["email"] == "bea@example.com"][0]
    assert client.post(f"/api/admin/users/{uid}/mfa/reset").status_code == 200
    assert bea.get("/api/me").status_code == 401
    with _factory()() as db:
        u = db.query(User).filter_by(email="bea@example.com").one()
        assert not u.totp_enabled and not db.query(RecoveryCode).filter_by(user_id=u.id).count()
    # desactivar con contraseña y código
    assert client.post("/api/me/2fa/disable", json={"password": PW, "code": codes[1]}).status_code == 200
    assert client.get("/api/me/2fa").json()["enabled"] is False


def test_bootstrap_ignores_invalid_entries(monkeypatch):
    from sqlalchemy import select
    from mimirsynth import main as m
    from mimirsynth.models import Brain
    with _factory()() as db:
        db.query(Brain).delete(); db.commit()
    monkeypatch.setattr(settings, "bootstrap_graphs", '# comentario "slug:Nombre,otro", docs:Docs, mal slug')
    m._bootstrap()
    with _factory()() as db:
        assert [b.slug for b in db.scalars(select(Brain))] == ["docs"]
        db.query(Brain).delete(); db.commit()


def test_oidc_resolution_autoprovision_and_groups(client, local, monkeypatch):  # noqa: F811
    from sqlalchemy import select
    from mimirsynth import appsettings
    from mimirsynth.models import Brain, Membership
    sets = {"admin_emails": ""}
    monkeypatch.setattr(appsettings, "get", lambda k: sets[k])
    p = _provider()
    with _factory()() as db:
        p = db.merge(p)
        db.add(Brain(slug="grp", name="Grp", graph_name="grp-g")); db.commit()
        info = {"sub": "s1", "email": "nueva@corp.example", "email_verified": True, "name": "Nueva", "groups": ["curadores", "admins"]}
        assert auth.resolve_oidc_user(db, info, p) == (None, "not_invited")  # sin alta automática solo entran invitados
        p.auto_provision, p.allowed_domains = True, "corp.example, otra.example"
        assert auth.resolve_oidc_user(db, {**info, "email": "x@evil.example", "sub": "s2"}, p) == (None, "not_invited")  # dominio no permitido
        assert auth.resolve_oidc_user(db, {**info, "email_verified": False, "sub": "s3"}, p) == (None, "not_invited")  # sin verificar, nunca se da de alta
        p.trust_unverified_email = True
        assert auth.resolve_oidc_user(db, {**info, "email_verified": False, "sub": "s3"}, p) == (None, "not_invited")  # ni confiando en emails sin verificar
        u, why = auth.resolve_oidc_user(db, info, p)
        assert u and not why and u.status == "active" and not u.is_admin and not u.password_hash
        assert auth.resolve_oidc_user(db, info, p)[0].id == u.id  # la segunda vez entra por su identidad vinculada

        p.admin_group, p.group_roles = "admins", "curadores=grp:curator, lectores=grp:reader, curadores=grp:owner, x=nope:reader"
        auth.apply_groups(db, u, info, p)
        assert u.is_admin
        assert db.scalar(select(Membership.role).where(Membership.user_id == u.id, Membership.brain_id == db.scalar(select(Brain.id).where(Brain.slug == "grp")))) == "curator"
        auth.apply_groups(db, u, {**info, "groups": ["curadores", "lectores", "admins"]}, p)  # un rol menor del mismo brain no rebaja el mayor
        assert db.scalar(select(Membership.role).where(Membership.user_id == u.id)) == "curator"
        u.status = "disabled"; db.commit()
        assert auth.resolve_oidc_user(db, info, p) == (None, "disabled")


def test_oidc_providers_are_independent_and_listed(client, local, monkeypatch):  # noqa: F811
    """Cada proveedor trae su política: la misma persona externa en otro proveedor es otra identidad, y los desactivados no se ofrecen."""
    from mimirsynth.models import OidcProvider
    a, b = _provider("alfa", name="Alfa", auto_provision=True, allowed_domains="corp.example"), _provider("beta", name="Beta")
    c = TestClient(app)
    opts = c.get("/api/auth/options").json()
    assert {x["slug"] for x in opts["providers"]} >= {"alfa", "beta"} and opts["oidc"]
    with _factory()() as db:
        a, b = db.merge(a), db.merge(b)
        info = {"sub": "same", "email": "p@corp.example", "email_verified": True, "name": "P"}
        u, _ = auth.resolve_oidc_user(db, info, a)
        assert u  # alfa da de alta por dominio
        assert auth.resolve_oidc_user(db, {**info, "sub": "same-b", "email": "q@corp.example"}, b) == (None, "not_invited")  # beta no
        db.query(OidcProvider).filter(OidcProvider.slug == "beta").update({"enabled": False}); db.commit()
    assert "beta" not in {x["slug"] for x in c.get("/api/auth/options").json()["providers"]}
    assert c.get("/api/auth/login/beta", follow_redirects=False).status_code == 404
    assert c.get("/api/auth/login/no-existe", follow_redirects=False).status_code == 404


def test_oidc_provider_admin_api(client, local, monkeypatch):  # noqa: F811
    """CRUD de proveedores: solo el administrador, el secreto no vuelve, el emisor se comprueba y no se deja a nadie sin acceso."""
    from mimirsynth import settings_admin
    from mimirsynth.models import Identity, OidcProvider
    monkeypatch.setattr("mimirsynth.oidc_providers.discover", lambda issuer: {"authorization_endpoint": "x", "token_endpoint": "y", "issuer": issuer})
    _admin(client)
    body = {"slug": "pocket", "name": "PocketID", "issuer": "https://id.example.com", "client_id": "cid", "client_secret": "s3cr3t", "group_roles": "a=docs:reader"}
    assert client.post("/api/oidc-providers", json={**body, "slug": "Mal Slug"}).status_code == 422
    assert client.post("/api/oidc-providers", json={**body, "client_secret": ""}).status_code == 422
    r = client.post("/api/oidc-providers", json=body)
    assert r.status_code == 201 and r.json()["secret_set"] is True and "s3cr3t" not in r.text
    assert r.json()["redirect_uri"].endswith("/api/auth/callback/pocket")
    assert client.post("/api/oidc-providers", json=body).status_code == 409
    with _factory()() as db:
        assert "s3cr3t" not in db.query(OidcProvider).filter_by(slug="pocket").one().client_secret  # sellado
    r = client.put("/api/oidc-providers/pocket", json={**body, "name": "Pocket", "client_secret": None, "slug": None})
    assert r.status_code == 200 and r.json()["name"] == "Pocket" and r.json()["secret_set"] is True  # sin secreto nuevo se conserva
    assert [x["slug"] for x in client.get("/api/oidc-providers").json()].count("pocket") == 1
    # borrar no deja a nadie sin forma de entrar
    with _factory()() as db:
        uid = db.query(User).filter_by(email="root@example.com").one().id
        solo = User(email="solo@example.com", name="Solo", status="active"); db.add(solo); db.flush()
        db.add(Identity(user_id=solo.id, provider="pocket", sub="x", email="solo@example.com")); db.commit()
    r = client.delete("/api/oidc-providers/pocket")
    assert r.status_code == 409 and "solo@example.com" in r.text
    with _factory()() as db:
        db.query(User).filter_by(email="solo@example.com").update({"password_hash": "algo"}); db.commit()
    assert client.delete("/api/oidc-providers/pocket").status_code == 200
    with _factory()() as db:
        assert db.query(Identity).filter_by(provider="pocket").count() == 0
    # no administradores
    anon = TestClient(app)
    assert anon.get("/api/oidc-providers").status_code in (401, 403)


def test_migration_imports_legacy_oidc_config(tmp_path, monkeypatch):
    """La migración 0016 convierte la configuración OIDC única (Ajustes + entorno) en el proveedor «oidc» y limpia los ajustes antiguos."""
    import json
    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    from mimirsynth import secretbox
    monkeypatch.setattr(settings, "oidc_issuer", "https://env.example.com")
    monkeypatch.setattr(settings, "oidc_client_id", "env-cid")
    monkeypatch.setattr(settings, "oidc_client_secret", "env-secret")
    eng = sa.create_engine(f"sqlite:///{tmp_path}/m.db")
    cfg = Config(); cfg.set_main_option("script_location", str(Path(auth.__file__).parent / "migrations"))
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0015")
        conn.execute(sa.text("INSERT INTO app_settings (key, value, updated_at) VALUES ('oidc_client_id', :v, CURRENT_TIMESTAMP), ('oidc_auto_provision', :y, CURRENT_TIMESTAMP), ('oidc_client_secret', :s, CURRENT_TIMESTAMP)"),
                     {"v": json.dumps({"v": "ui-cid"}), "y": json.dumps({"v": "yes"}), "s": json.dumps({"v": secretbox.seal("ui-secret")})})
        command.upgrade(cfg, "0016")
        row = conn.execute(sa.text("SELECT slug, name, issuer, client_id, client_secret, auto_provision, enabled FROM oidc_providers")).one()
        assert (row.slug, row.issuer, row.client_id, bool(row.auto_provision), bool(row.enabled)) == ("oidc", "https://env.example.com", "ui-cid", True, True)  # lo de Ajustes manda sobre el entorno
        assert secretbox.unseal(row.client_secret) == "ui-secret"
        assert conn.execute(sa.text("SELECT count(*) FROM app_settings WHERE key LIKE 'oidc%'")).scalar() == 0


def test_group_roles_are_revoked_but_manual_ones_never(client, local, monkeypatch):  # noqa: F811
    """Al dejar el grupo se retira lo que el grupo concedió (y se restaura el rol anterior); lo puesto a mano no se toca; sin campo de grupos no se retira nada."""
    from sqlalchemy import select
    from mimirsynth import appsettings, userlib
    from mimirsynth.models import Brain, Membership, RoleGrant
    monkeypatch.setattr(appsettings, "get", lambda k: "")
    p = _provider("rev", admin_group="admins", group_roles="curadores=b1:curator, lectores=b2:reader, curadores=b3:curator")
    with _factory()() as db:
        p = db.merge(p)
        b1, b2, b3 = (Brain(slug=s_, name=s_, graph_name=s_ + "-g") for s_ in ("b1", "b2", "b3"))
        db.add_all([b1, b2, b3]); db.flush()
        boss = User(email="boss@example.com", name="Boss", is_admin=True, status="active")
        u = User(email="p@example.com", name="P", status="active")
        db.add_all([boss, u]); db.flush()
        db.add(Membership(user_id=u.id, brain_id=b2.id, role="reader"))  # manual: ya era lector
        db.add(Membership(user_id=u.id, brain_id=b3.id, role="contributor"))  # manual, menor: el grupo lo sube
        db.commit()
        role = lambda b: db.scalar(select(Membership.role).where(Membership.user_id == u.id, Membership.brain_id == b.id))
        auth.apply_groups(db, u, {"groups": ["admins", "curadores", "lectores"]}, p)
        assert u.is_admin and role(b1) == "curator" and role(b2) == "reader" and role(b3) == "curator"
        assert db.query(RoleGrant).filter_by(user_id=u.id).count() == 3  # admin + b1 + b3 (b2 no: ya lo tenía)
        auth.apply_groups(db, u, {"groups": ["admins", "curadores", "lectores"]}, p)  # idempotente
        assert db.query(RoleGrant).filter_by(user_id=u.id).count() == 3
        auth.apply_groups(db, u, {}, p)  # el proveedor no envía grupos: no se retira nada
        assert u.is_admin and role(b1) == "curator"
        auth.apply_groups(db, u, {"groups": []}, p)  # ya no está en ningún grupo
        assert not u.is_admin  # y se le cierran las sesiones abiertas
        assert role(b1) is None  # la concedió el grupo: fuera
        assert role(b3) == "contributor"  # lo subió el grupo: vuelve al que tenía
        assert role(b2) == "reader"  # era manual: intacto
        assert db.query(RoleGrant).filter_by(user_id=u.id).count() == 0
        # un administrador cambia a mano lo que dio el grupo: el grupo ya no lo retira
        auth.apply_groups(db, u, {"groups": ["curadores"]}, p)
        assert role(b1) == "curator"
        userlib.forget_grants(db, u.id, b1.id); m = db.scalar(select(Membership).where(Membership.user_id == u.id, Membership.brain_id == b1.id)); m.role = "admin"; db.commit()
        auth.apply_groups(db, u, {"groups": []}, p)
        assert role(b1) == "admin"
        # nunca se deja la instancia sin administradores
        db.query(User).update({"is_admin": False}); db.commit()
        auth.apply_groups(db, u, {"groups": ["admins"]}, p)
        assert u.is_admin and userlib.admin_count(db) == 1
        auth.apply_groups(db, u, {"groups": []}, p)
        assert u.is_admin  # es el último administrador: se conserva


def test_identity_linking_and_unlinking(client, local, monkeypatch):  # noqa: F811
    """Vincular añade la identidad a la sesión actual (sin abrir otra), no se puede robar la de otra persona y siempre queda una forma de entrar."""
    from mimirsynth.models import Identity
    _provider("pk", name="Pk"); _provider("gh", name="Gh")
    _admin(client)
    me = client.get("/api/me/identities").json()
    assert me["identities"] == [] and {x["slug"] for x in me["available"]} >= {"pk", "gh"} and me["can_unlink"] is True  # tiene contraseña

    class FakeIdp:
        sub = "ext-1"
        async def authorize_redirect(self, request, uri): return __import__("fastapi").responses.RedirectResponse("http://idp.example/auth")
        async def authorize_access_token(self, request): return {"userinfo": {"sub": self.sub, "email": "root@example.com"}}
    idp = FakeIdp()
    monkeypatch.setattr(auth, "_oidc", lambda p: idp)
    assert client.get("/api/me/identities/link/pk", follow_redirects=False).status_code == 307
    r = client.get("/api/auth/callback/pk", follow_redirects=False)
    assert r.headers["location"].endswith("linked=1")
    ids = client.get("/api/me/identities").json()
    assert [i["provider"] for i in ids["identities"]] == ["pk"] and "pk" not in {x["slug"] for x in ids["available"]}
    assert client.get("/api/me/identities/link/pk").status_code == 409  # ya vinculado
    # otra persona intenta vincular la misma identidad externa
    other = TestClient(app)
    with _factory()() as db:
        o = User(email="otra@example.com", name="Otra", status="active", password_hash=passwords_hash()); db.add(o); db.commit()
    assert other.post("/api/auth/login", json={"email": "otra@example.com", "password": PW}).status_code == 200
    other.get("/api/me/identities/link/pk", follow_redirects=False)
    assert other.get("/api/auth/callback/pk", follow_redirects=False).headers["location"].endswith("link_error=taken")
    # sin intención de vincular, el callback es un inicio de sesión normal (y no vincula)
    # desvincular: con contraseña se puede; sin contraseña y sin otra identidad, no
    iid = ids["identities"][0]["id"]
    with _factory()() as db:
        db.query(User).filter_by(email="root@example.com").update({"password_hash": ""}); db.commit()
    r = client.delete(f"/api/me/identities/{iid}")
    assert r.status_code == 409 and client.get("/api/me/identities").json()["can_unlink"] is False
    with _factory()() as db:
        from mimirsynth import passwords
        db.query(User).filter_by(email="root@example.com").update({"password_hash": passwords.hash_password(PW)}); db.commit()
    assert client.delete(f"/api/me/identities/{iid}").status_code == 200
    assert client.delete(f"/api/me/identities/{iid}").status_code == 404
    with _factory()() as db:
        assert db.query(Identity).filter_by(provider="pk").count() == 0


def passwords_hash():
    from mimirsynth import passwords
    return passwords.hash_password(PW)


def test_ratelimit_is_persistent_and_sliding(client):  # noqa: F811
    """Los intentos viven en la base de datos (los ve otro proceso y sobreviven al reinicio) y salen de la ventana con el tiempo."""
    from datetime import datetime, timedelta, timezone
    from mimirsynth.models import RateHit
    ratelimit.reset()
    assert [ratelimit.allow("k1", 3, 600) for _ in range(5)] == [True, True, True, False, False]
    ratelimit._HITS.clear()  # «otro proceso» o reinicio: la memoria no cuenta, la base de datos sí
    assert ratelimit.allow("k1", 3, 600) is False
    assert ratelimit.allow("k2", 3, 600) is True  # otra clave, otro cubo
    with _factory()() as db:  # envejecer los intentos de k1 más allá de la ventana
        db.query(RateHit).filter(RateHit.key == "k1").update({"at": datetime.now(timezone.utc) - timedelta(seconds=601)}); db.commit()
    assert ratelimit.allow("k1", 3, 600) is True
    with _factory()() as db:
        assert db.query(RateHit).filter(RateHit.key == "k1").count() == 1  # los caducados se borran


def test_ratelimit_falls_back_to_memory_when_db_fails(client, monkeypatch):  # noqa: F811
    """Si la base de datos no responde no se deja el acceso sin protección: manda el contador en memoria."""
    ratelimit.reset()
    monkeypatch.setattr(ratelimit, "_allow_db", lambda *a: (_ for _ in ()).throw(RuntimeError("caída")))
    assert [ratelimit.allow("k3", 2, 600) for _ in range(3)] == [True, True, False]
    ratelimit.reset()


def _brain(db, slug):
    from mimirsynth.models import Brain
    b = db.query(Brain).filter_by(slug=slug).one_or_none()
    if not b:
        b = Brain(slug=slug, name=slug, graph_name=f"{slug}-g"); db.add(b); db.commit()
    return b


def test_oidc_default_roles_once_on_autoprovision(client, local, monkeypatch):  # noqa: F811
    """El acceso inicial se da una vez al dar de alta a alguien solo, queda auditado, se suma a los grupos y no vuelve si se quita."""
    from mimirsynth import appsettings
    from mimirsynth.models import Audit, Membership, OidcProvider
    monkeypatch.setattr(appsettings, "get", lambda k: {"admin_emails": ""}[k])
    with _factory()() as db:
        docs, ops = _brain(db, "ini-docs").id, _brain(db, "ini-ops").id
    _provider("ini", auto_provision=True, allowed_domains="ini.example", group_roles="curadores=ini-docs:curator",
              default_roles="ini-docs:reader, ini-ops:contributor, borrado:reader, ini-ops:curator")  # un brain borrado o un rol mayor se ignoran
    roles = lambda db, uid: {m.brain_id: m.role for m in db.query(Membership).filter_by(user_id=uid)}  # noqa: E731
    with _factory()() as db:
        p = db.query(OidcProvider).filter_by(slug="ini").one()
        info = {"sub": "ini-1", "email": "nuevo@ini.example", "email_verified": True, "name": "Nuevo", "groups": ["curadores"]}
        u, why = auth.resolve_oidc_user(db, info, p)
        assert u and not why and roles(db, u.id) == {docs: "reader", ops: "contributor"}
        acts = db.query(Audit).filter_by(user_id=u.id, action="member.set").all()
        assert sorted(a.detail["role"] for a in acts) == ["contributor", "reader"] and {a.detail["via"] for a in acts} == {"oidc-default:ini"}
        auth.apply_groups(db, u, info, p)
        assert roles(db, u.id) == {docs: "curator", ops: "contributor"}  # el grupo da un rol mayor: gana el mayor
        db.query(Membership).filter_by(user_id=u.id, brain_id=ops).delete(); db.commit()  # un administrador lo quita a mano
        assert auth.resolve_oidc_user(db, info, p)[0].id == u.id
        auth.apply_groups(db, u, info, p)
        assert roles(db, u.id) == {docs: "curator"}  # un login posterior no lo repone
        db.add(User(email="invitada@ini.example", name="Invitada", status="invited")); db.commit()
        v, _ = auth.resolve_oidc_user(db, {**info, "sub": "ini-2", "email": "invitada@ini.example", "groups": []}, p)
        assert v and v.status == "active" and roles(db, v.id) == {}  # una invitación trae sus propios roles: no recibe el acceso inicial


def test_oidc_default_roles_are_validated(client, local, monkeypatch):  # noqa: F811
    """Al guardar el proveedor solo se admiten brain:rol con brains que existen y roles reader o contributor."""
    monkeypatch.setattr("mimirsynth.oidc_providers.discover", lambda issuer: {"authorization_endpoint": "x", "token_endpoint": "y", "issuer": issuer})
    _admin(client)
    with _factory()() as db:
        _brain(db, "ini-docs"); _brain(db, "ini-ops")
    body = {"slug": "inival", "name": "Ini", "issuer": "https://id.example.com", "client_id": "cid", "client_secret": "s"}
    for bad in ("ini-docs", "ini-docs:curator", "ini-docs:owner", "nope:reader", ":reader", "ini-docs:reader, ini-docs:contributor"):
        r = client.post("/api/oidc-providers", json={**body, "default_roles": bad})
        assert r.status_code == 422 and "acceso inicial" in r.json()["detail"], bad
    r = client.post("/api/oidc-providers", json={**body, "default_roles": " ini-docs:reader ,ini-ops : contributor "})
    assert r.status_code == 201 and r.json()["default_roles"] == "ini-docs:reader, ini-ops:contributor"


def test_oidc_unverified_email_never_takes_an_active_account(client, local, monkeypatch):  # noqa: F811
    """Con «aceptar emails sin verificar» se vinculan invitaciones, pero una cuenta activa solo con email verificado o desde Mi cuenta."""
    from mimirsynth import appsettings
    from mimirsynth.models import Identity, OidcProvider
    monkeypatch.setattr(appsettings, "get", lambda k: {"admin_emails": ""}[k])
    _provider("unv", trust_unverified_email=True)
    with _factory()() as db:
        p = db.query(OidcProvider).filter_by(slug="unv").one()
        db.add(User(email="activa@unv.example", name="Activa", status="active", password_hash="x", is_admin=True))
        db.add(User(email="invitada@unv.example", name="Invitada", status="invited")); db.commit()
        info = {"sub": "unv-1", "email": "activa@unv.example", "email_verified": False}
        assert auth.resolve_oidc_user(db, info, p) == (None, "link_required")
        assert auth.resolve_oidc_user(db, {k: v for k, v in info.items() if k != "email_verified"}, p) == (None, "link_required")  # sin el campo, igual
        assert db.query(Identity).filter_by(provider="unv").count() == 0
        u, _ = auth.resolve_oidc_user(db, {**info, "sub": "unv-2", "email": "invitada@unv.example"}, p)
        assert u and u.status == "active"  # la invitación aún no tiene credenciales: se vincula
        u, _ = auth.resolve_oidc_user(db, {**info, "email_verified": True}, p)
        assert u and u.email == "activa@unv.example"  # con el email verificado, como siempre
