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
    monkeypatch.setattr(auth, "_oidc", lambda: FakeOidc())
    _admin(client)
    r = client.get("/api/auth/callback", follow_redirects=False)
    assert r.status_code == 307 and "auth_error=not_invited" in r.headers["location"]
    client.post("/api/admin/users", json={"email": "invitada@example.com", "mode": "invite"})

    class FakeOk(FakeOidc):
        async def authorize_access_token(self, request):
            return {"userinfo": {"sub": "sub-2", "email": "invitada@example.com", "email_verified": True, "name": "Inv"}}
    monkeypatch.setattr(auth, "_oidc", lambda: FakeOk())
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
    r = c2.post("/api/auth/login", json={"email": "root@example.com", "password": PW}); assert r.json() == {"ok": True, "mfa": True}
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
