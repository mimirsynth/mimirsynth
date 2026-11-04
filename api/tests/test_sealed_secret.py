"""A database sealed under another MIMIRSYNTH_SESSION_SECRET (#193): the instance notices it, says so, and answers clearly instead of a 500."""
import logging
import time

import pytest
from fastapi.testclient import TestClient

from test_control import client  # noqa: F401
from test_users import PW, _admin, _code, local  # noqa: F401

from mimirsynth import ratelimit, sealcheck, secretbox
from mimirsynth.config import settings
from mimirsynth.main import app
from mimirsynth.models import LlmEngine
from mimirsynth.store import _factory

OTHER = "another-secret-than-the-one-that-sealed"
RIGHT = settings.session_secret


@pytest.fixture()
def right_secret_after():
    """Whatever a test does to the secret, the instance ends with the right one checked, so /api/health is clean for the next tests."""
    yield
    with _factory()() as db:
        assert sealcheck.check(db) == {}


def test_a_sealed_value_under_another_secret_raises_its_own_error(monkeypatch):
    token = secretbox.seal("sk-very-secret")
    assert secretbox.unseal(token) == "sk-very-secret" and secretbox.unseal("") == ""
    monkeypatch.setattr(settings, "session_secret", OTHER)
    with pytest.raises(secretbox.SealedSecretError) as e:
        secretbox.unseal(token)
    assert "sk-very-secret" not in str(e.value) and token not in str(e.value) and e.value.__cause__ is None


def test_the_canary_tells_the_right_secret_from_another(client, monkeypatch, caplog, right_secret_after):  # noqa: F811
    r = client.post("/api/llm-engines", json={"name": "sealed-llm", "base_url": "http://llm.invalid/v1", "model": "m", "api_key": "sk-canary-test"})
    assert r.status_code in (200, 201), r.text
    eid = r.json()["id"]
    with _factory()() as db:
        token = db.get(LlmEngine, eid).api_key_enc
    try:
        # the right secret: nothing to say, and no new field in the health check
        assert client.get("/api/settings/sealed").json() == {"ok": True, "unreadable": {}, "total": 0}
        assert "secrets" not in client.get("/api/health").json()

        monkeypatch.setattr(settings, "session_secret", OTHER)
        r = client.get("/api/settings/sealed")
        assert r.status_code == 200 and r.json()["ok"] is False and r.json()["unreadable"]["llm"] >= 1
        assert r.json()["total"] == sum(r.json()["unreadable"].values())
        assert token not in r.text and "sk-canary-test" not in r.text
        h = client.get("/api/health")
        assert h.json()["secrets"] == "unreadable" and "db" in h.json()  # the field is added; the check keeps its meaning

        # one clear line at start, without the value or its ciphertext
        with caplog.at_level(logging.ERROR, logger="mimirsynth"), _factory()() as db:
            sealcheck.at_start(db)
        assert "MIMIRSYNTH_SESSION_SECRET does not match" in caplog.text and "llm:" in caplog.text
        assert token not in caplog.text and "sk-canary-test" not in caplog.text

        # «Test» of the engine: a clear, translated 503, never a bare 500
        r = client.post(f"/api/llm-engines/{eid}/test")
        assert r.status_code == 503 and "MIMIRSYNTH_SESSION_SECRET" in r.json()["detail"] and token not in r.text
        r = client.post(f"/api/llm-engines/{eid}/test", headers={"Accept-Language": "en"})
        assert r.status_code == 503 and r.json()["detail"].startswith("A stored secret cannot be read")
        # the settings page still loads: whether a secret is set does not need to open it
        assert client.get("/api/settings").status_code == 200
    finally:
        monkeypatch.setattr(settings, "session_secret", RIGHT)
        client.delete(f"/api/llm-engines/{eid}")


def test_the_smtp_test_says_why_it_cannot_send(client, monkeypatch, right_secret_after):  # noqa: F811
    from mimirsynth import appsettings
    for k, v in (("smtp_host", "smtp.invalid"), ("smtp_from", "mimir@example.com")):
        assert client.put(f"/api/settings/{k}", json={"value": v}).status_code == 200
    assert client.put("/api/settings/secret/smtp_password", json={"value": "smtp-pass"}).status_code == 200
    try:
        monkeypatch.setattr(settings, "session_secret", OTHER)
        r = client.post("/api/settings/smtp/test", json={"to": "x@example.com"})
        assert r.status_code == 503 and "MIMIRSYNTH_SESSION_SECRET" in r.json()["detail"] and "smtp-pass" not in r.text
        assert client.get("/api/settings").json()["secrets"]["smtp_password"]["set"] is True
    finally:
        monkeypatch.setattr(settings, "session_secret", RIGHT)
        client.put("/api/settings/secret/smtp_password", json={"value": ""})
        for k in ("smtp_host", "smtp_from"):
            client.delete(f"/api/settings/{k}")
        appsettings.invalidate()


def test_the_notice_goes_once_every_secret_is_entered_again(monkeypatch, right_secret_after):
    """A lost secret: once the unreadable values are entered again (or removed), the canary is sealed again and the notice goes."""
    old = secretbox.seal("x")
    with _factory()() as db:
        monkeypatch.setattr(settings, "session_secret", OTHER)
        values = [("llm", old)]
        monkeypatch.setattr(sealcheck, "_sealed", lambda _db: iter(values))
        assert sealcheck.check(db) == {"llm": 1} and sealcheck.unreadable() == {"llm": 1}
        values[:] = [("llm", secretbox.seal("x"))]  # entered again under the secret the instance runs with
        assert sealcheck.check(db) == {} and sealcheck.unreadable() == {}
        values[:] = [("llm", old)]  # the canary now answers for this secret: nothing else is read
        assert sealcheck.check(db) == {}
        monkeypatch.undo()
        # back to the first secret, the canary (sealed under the other one) fails and the scan decides again
        monkeypatch.setattr(sealcheck, "_sealed", lambda _db: iter([("llm", old)]))
        assert sealcheck.check(db) == {}
        monkeypatch.undo()


def test_two_factor_with_an_unreadable_seed(client, local, monkeypatch, right_secret_after):  # noqa: F811
    from mimirsynth.models import User
    _admin(client)
    secret = client.post("/api/me/2fa/begin", json={"password": PW}).json()["secret"]
    codes = client.post("/api/me/2fa/enable", json={"code": _code(secret)}).json()["recovery_codes"]
    try:
        monkeypatch.setattr(settings, "session_secret", OTHER)
        ratelimit.reset()
        c2 = TestClient(app)
        assert c2.post("/api/auth/login", json={"email": "root@example.com", "password": PW}).json()["mfa"] is True
        from mimirsynth import totp
        r = c2.post("/api/auth/mfa", json={"code": totp._code(secret, int(time.time() // totp.STEP) + 1)})
        assert r.status_code == 503 and "código de recuperación" in r.json()["detail"] and secret not in r.text
        with _factory()() as db:
            assert db.query(User).filter_by(email="root@example.com").one().failed_attempts == 1  # still a failed attempt
        r = c2.post("/api/auth/mfa", json={"code": "000000"}, headers={"Accept-Language": "en"})
        assert r.status_code == 503 and "recovery code" in r.json()["detail"]
        assert c2.post("/api/auth/mfa", json={"code": codes[0]}).status_code == 200  # a recovery code is only hashed: it still works
        # the confirmations of a signed-in account (disable, new recovery codes) get the same 503, by design not counted as a failed
        # sign-in: they already need a session and the password
        for path in ("disable", "recovery"):
            r = c2.post(f"/api/me/2fa/{path}", json={"password": PW, "code": "000000"})
            assert r.status_code == 503 and "código de recuperación" in r.json()["detail"], (path, r.text)
        with _factory()() as db:
            u = db.query(User).filter_by(email="root@example.com").one()
            assert u.totp_enabled and u.failed_attempts == 0
        assert c2.post("/api/me/2fa/recovery", json={"password": PW, "code": codes[1]}).status_code == 200  # with a recovery code it works
        assert c2.get("/api/me").status_code == 200
    finally:
        monkeypatch.setattr(settings, "session_secret", RIGHT)
        with _factory()() as db:
            u = db.query(User).filter_by(email="root@example.com").one()
            from mimirsynth import mfa
            mfa.clear(db, u)
            u.failed_attempts = 0
            db.commit()
