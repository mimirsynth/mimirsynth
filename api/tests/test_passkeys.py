"""Llaves de acceso (WebAuthn): alta, entrada sin contraseña, segundo factor, baja y protecciones. Con un autenticador de software."""
import base64
import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from test_control import client  # noqa: F401
from test_users import PW, _admin, local  # noqa: F401

from mimirsynth import passwords
from mimirsynth.main import app
from mimirsynth.models import Passkey, User
from mimirsynth.store import _factory

ORIGIN, RP = "http://testserver", "testserver"


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_passkeys(client):  # noqa: F811
    """La base de pruebas se comparte entre ficheros: cada prueba parte sin llaves ni cuenta de Luis."""
    with _factory()() as db:
        db.query(Passkey).delete(); db.query(User).filter(User.email == "luis@example.com").delete(); db.commit()
    yield
    with _factory()() as db:                                                                              # y sin restos para los demás ficheros
        db.query(Passkey).delete(); db.query(User).filter(User.email == "luis@example.com").delete(); db.commit()


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class Authenticator:
    """Autenticador de software (ES256, atestación «none»): lo mínimo para ejercitar el servidor como lo haría un navegador."""
    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cid = os.urandom(32)
        self.count = 0

    def _cose(self) -> bytes:
        n = self.key.public_key().public_numbers()
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, "big"), -3: n.y.to_bytes(32, "big")})

    def create(self, options: dict, origin=ORIGIN, rp=RP) -> dict:
        cd = json.dumps({"type": "webauthn.create", "challenge": options["challenge"], "origin": origin, "crossOrigin": False}).encode()
        auth = hashlib.sha256(rp.encode()).digest() + bytes([0x45]) + struct.pack(">I", self.count) + bytes(16) + struct.pack(">H", len(self.cid)) + self.cid + self._cose()
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth})
        return {"id": b64(self.cid), "rawId": b64(self.cid), "type": "public-key", "response": {"clientDataJSON": b64(cd), "attestationObject": b64(att), "transports": ["internal"]}}

    def get(self, options: dict, origin=ORIGIN, rp=RP, flags=0x05, count=None) -> dict:
        self.count = self.count + 1 if count is None else count
        cd = json.dumps({"type": "webauthn.get", "challenge": options["challenge"], "origin": origin, "crossOrigin": False}).encode()
        auth = hashlib.sha256(rp.encode()).digest() + bytes([flags]) + struct.pack(">I", self.count)
        sig = self.key.sign(auth + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": b64(self.cid), "rawId": b64(self.cid), "type": "public-key",
                "response": {"clientDataJSON": b64(cd), "authenticatorData": b64(auth), "signature": b64(sig), "userHandle": b64(b"ms-1")}}


def _register(c, auth: Authenticator, name="Llave", password=PW):
    opts = c.post("/api/me/passkeys/begin", json={"password": password})
    assert opts.status_code == 200, opts.text
    r = c.post("/api/me/passkeys/finish", json={"credential": auth.create(opts.json()), "name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _login_with(auth: Authenticator, **kw):
    c = TestClient(app)
    opts = c.post("/api/auth/passkey/options").json()
    return c, c.post("/api/auth/passkey/login", json={"credential": auth.get(opts, **kw)})


def test_register_and_passwordless_login(client, local):  # noqa: F811
    _admin(client)
    assert client.post("/api/me/passkeys/begin", json={"password": "mal"}).status_code == 403   # añadir un acceso pide la contraseña
    a = Authenticator()
    p = _register(client, a, "Portátil")
    assert [x["name"] for x in client.get("/api/me/passkeys").json()] == ["Portátil"]
    assert client.post("/api/me/passkeys/finish", json={"credential": a.create({"challenge": "x"})}).status_code == 400  # sin reto vigente
    c, r = _login_with(a)
    assert r.status_code == 200, r.text
    me = c.get("/api/me").json()
    assert me["email"] == "root@example.com"
    assert client.get("/api/me/passkeys").json()[0]["last_used_at"] and p["id"]


def test_login_rejections(client, local):  # noqa: F811
    _admin(client)
    a = Authenticator(); _register(client, a)
    anon = TestClient(app)
    opts = anon.post("/api/auth/passkey/options").json()
    assert anon.post("/api/auth/passkey/login", json={"credential": a.get(opts, origin="https://evil.example")}).status_code == 401   # otro origen
    assert anon.post("/api/auth/passkey/login", json={"credential": a.get(opts)}).status_code == 400                                  # el reto era de un solo uso
    for kw in ({"rp": "otro.example"}, {"flags": 0x01}):                                                                                # otro dominio / sin verificación de usuario
        opts = anon.post("/api/auth/passkey/options").json()
        assert anon.post("/api/auth/passkey/login", json={"credential": a.get(opts, **kw)}).status_code == 401
    opts = anon.post("/api/auth/passkey/options").json()
    assert anon.post("/api/auth/passkey/login", json={"credential": Authenticator().get(opts)}).status_code == 401                    # llave desconocida
    assert _login_with(a, count=50)[1].status_code == 200
    opts = anon.post("/api/auth/passkey/options").json()
    assert anon.post("/api/auth/passkey/login", json={"credential": a.get(opts, count=3)}).status_code == 401                          # contador que retrocede (llave clonada)
    with _factory()() as db:                                                                                                            # cuenta deshabilitada
        db.query(User).filter(User.email == "root@example.com").update({"status": "disabled"}); db.commit()
    assert _login_with(a, count=60)[1].status_code == 401
    with _factory()() as db:
        db.query(User).filter(User.email == "root@example.com").update({"status": "active"}); db.commit()


def test_second_factor_after_password(client, local):  # noqa: F811
    _admin(client)
    a = Authenticator(); _register(client, a)
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "root@example.com", "password": PW}).json()
    assert r["mfa"] is True and r["methods"] == ["passkey"] and c.get("/api/me").status_code == 401      # la contraseña sola ya no abre sesión
    opts = c.post("/api/auth/passkey/mfa/options").json()
    assert [x["id"] for x in opts["allowCredentials"]] == [b64(a.cid)]
    other = Authenticator()                                                                                # la llave de otra persona no vale
    with _factory()() as db:
        db.add(User(email="luis@example.com", name="Luis", password_hash=passwords.hash_password(PW), status="active")); db.commit()
    assert c.post("/api/auth/passkey/mfa", json={"credential": other.get(opts)}).status_code in (400, 401)
    opts = c.post("/api/auth/passkey/mfa/options").json()
    assert c.post("/api/auth/passkey/mfa", json={"credential": a.get(opts)}).status_code == 200
    assert c.get("/api/me").json()["email"] == "root@example.com"
    assert TestClient(app).post("/api/auth/passkey/mfa/options").status_code == 401                      # sin la contraseña previa no hay reto


def test_passkey_satisfies_required_2fa(client, local):  # noqa: F811
    _admin(client)
    a = Authenticator(); _register(client, a)
    pw_only = TestClient(app)
    with _factory()() as db:                                                                              # otra cuenta con contraseña y sin segundo factor
        db.add(User(email="luis@example.com", name="Luis", password_hash=passwords.hash_password(PW), status="active")); db.commit()
    assert pw_only.post("/api/auth/login", json={"email": "luis@example.com", "password": PW}).status_code == 200
    assert client.put("/api/settings/require_2fa", json={"value": "yes"}).status_code == 200
    try:
        assert pw_only.get("/api/me").json()["must_setup_2fa"] is True                                    # contraseña sola: se le exige configurarlo
        c, r = _login_with(a)
        assert r.status_code == 200 and c.get("/api/me").json()["must_setup_2fa"] is False                # con llave de acceso ya cumple
    finally:
        client.put("/api/settings/require_2fa", json={"value": "no"})


def test_remove_and_admin_reset(client, local):  # noqa: F811
    _admin(client)
    a, b = Authenticator(), Authenticator()
    pa, pb = _register(client, a, "A"), _register(client, b, "B")
    assert client.post(f"/api/me/passkeys/{pa['id']}/delete", json={"password": "mal"}).status_code == 403
    assert client.patch(f"/api/me/passkeys/{pa['id']}", json={"name": "Renombrada"}).json()["name"] == "Renombrada"
    assert client.post(f"/api/me/passkeys/{pa['id']}/delete", json={"password": PW}).status_code == 200
    assert client.post("/api/me/passkeys/9999/delete", json={"password": PW}).status_code == 404
    assert _login_with(a, count=5)[1].status_code == 401                                                  # la llave borrada ya no entra
    uid = client.get("/api/me").json()["id"]
    assert client.post(f"/api/admin/users/{uid}/mfa/reset").status_code == 200
    with _factory()() as db:
        assert db.query(Passkey).filter(Passkey.user_id == uid).count() == 0                              # el reinicio del administrador también quita las llaves
    assert pb["id"]


def test_cannot_remove_only_way_in(client, local):  # noqa: F811
    _admin(client)
    with _factory()() as db:                                                                              # cuenta sin contraseña ni proveedor: solo la llave
        u = db.query(User).filter(User.email == "root@example.com").one()
        a = Authenticator()
    _register(client, a)
    with _factory()() as db:
        u = db.query(User).filter(User.email == "root@example.com").one(); u.password_hash = ""; db.commit()
        pid = db.query(Passkey).filter(Passkey.user_id == u.id).one().id
    try:
        assert client.post(f"/api/me/passkeys/{pid}/delete", json={}).status_code == 409
    finally:
        with _factory()() as db:
            db.query(User).filter(User.email == "root@example.com").update({"password_hash": passwords.hash_password(PW)}); db.commit()
