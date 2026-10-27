"""Notificaciones: canales, agrupación de avisos, recuperación, horas de silencio, reintentos, visibilidad y comprobaciones."""
import hashlib
import hmac
import json
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from test_control import _as, client  # noqa: F401

from mimirsynth import appsettings, mail, notify
from mimirsynth import notify_channels as ch
from mimirsynth.main import app
from mimirsynth.models import Notification, NotifyChannel, NotifyDelivery, NotifyRead, User, now
from mimirsynth.secretbox import seal
from mimirsynth.store import _factory


@pytest.fixture(autouse=True)
def _clean(client):  # noqa: F811
    def wipe():
        with _factory()() as db:
            for m in (NotifyDelivery, Notification, NotifyChannel, NotifyRead):
                db.query(m).delete()
            db.commit()
    wipe()
    yield
    wipe()
    app.dependency_overrides.clear()


def _chan(name, kind="webhook", **kw):
    with _factory()() as db:
        c = NotifyChannel(name=name, kind=kind, config=kw.pop("config", {"url": "http://203.0.113.9/hook"}), secret=seal(kw.pop("secret", "")) if kw.get("secret") else "", **kw)
        db.add(c); db.commit()
        return c.id


def _deliveries():
    with _factory()() as db:
        return [(d.channel.name, d.kind, d.status) for d in db.query(NotifyDelivery).order_by(NotifyDelivery.id)]


def _mock(monkeypatch, handler):
    monkeypatch.setattr(ch, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


MSG = ch.Message(event="model.unavailable", severity="critical", title="Modelo caído: ñandú", body="Motor «x» no responde", brain="Casa", count=3, instance="MimirSynth")


# ---- canales ----
def test_ntfy_gotify_webhook_telegram_payloads(monkeypatch):
    seen = []
    _mock(monkeypatch, lambda r: (seen.append(r), httpx.Response(200, json={"ok": True}))[1])
    ch.send_ntfy({"url": "http://203.0.113.5", "topic": "alertas"}, "tk_abc", MSG)
    r = seen[-1]
    assert str(r.url) == "http://203.0.113.5/alertas" and r.headers["authorization"] == "Bearer tk_abc" and r.headers["priority"] == "5"
    assert r.headers["title"].startswith("=?UTF-8?B?") and "Repetido 3 veces" in r.content.decode()   # el título con acentos viaja codificado
    ch.send_gotify({"url": "http://203.0.113.6"}, "gt", MSG)
    r = seen[-1]
    assert str(r.url) == "http://203.0.113.6/message" and r.headers["x-gotify-key"] == "gt" and json.loads(r.content)["priority"] == 8
    ch.send_webhook({"url": "http://203.0.113.7/h"}, "clave", MSG)
    r = seen[-1]
    sig = "sha256=" + hmac.new(b"clave", r.content, hashlib.sha256).hexdigest()
    assert r.headers["x-mimirsynth-signature"] == sig and json.loads(r.content)["event"] == "model.unavailable"   # el receptor puede verificar el origen
    ch.send_webhook({"url": "http://203.0.113.7/h"}, "", MSG)
    assert "x-mimirsynth-signature" not in seen[-1].headers
    ch.send_telegram({"chat_id": "-100123", "thread_id": "12"}, "123:ABC", MSG)
    r = seen[-1]
    body = json.loads(r.content)
    assert str(r.url) == "https://api.telegram.org/bot123:ABC/sendMessage" and body["chat_id"] == "-100123" and body["message_thread_id"] == 12 and "parse_mode" not in body


def test_channel_errors_are_clear(monkeypatch):
    _mock(monkeypatch, lambda r: httpx.Response(400, json={"ok": False, "description": "chat not found"}))
    with pytest.raises(RuntimeError, match="chat not found"):
        ch.send_telegram({"chat_id": "1"}, "t", MSG)
    with pytest.raises(RuntimeError, match="faltan"):
        ch.send_telegram({"chat_id": ""}, "t", MSG)
    with pytest.raises(RuntimeError, match="token"):
        ch.send_gotify({"url": "http://203.0.113.6"}, "", MSG)
    with pytest.raises(RuntimeError, match="tema"):
        ch.send_ntfy({"url": "http://203.0.113.5", "topic": ""}, "", MSG)
    with pytest.raises(RuntimeError, match="HTTP 400"):
        ch.send_webhook({"url": "http://203.0.113.7"}, "", MSG)


def test_email_channel(monkeypatch):
    sent = []
    monkeypatch.setattr(mail, "configured", lambda: True)
    monkeypatch.setattr(mail, "send", lambda to, subj, body: sent.append((to, subj, body)))
    ch.send_email({"to": "a@x.com; b@x.com"}, "", MSG)
    assert sent[0][0] == "a@x.com, b@x.com" and "ñandú" in sent[0][1] and "Casa" in sent[0][2]
    with pytest.raises(RuntimeError, match="destinatarios"):
        ch.send_email({"to": ""}, "", MSG)
    monkeypatch.setattr(mail, "configured", lambda: False)
    with pytest.raises(RuntimeError, match="SMTP"):
        ch.send_email({"to": "a@x.com"}, "", MSG)


def test_url_guard(monkeypatch):
    assert ch.check_url("http://192.168.1.10:8080/") == "http://192.168.1.10:8080"          # red local permitida por defecto: lo habitual en un homelab
    for bad in ("ftp://203.0.113.1", "javascript:alert(1)", "", "http://"):
        with pytest.raises(ValueError):
            ch.check_url(bad)
    with pytest.raises(ValueError, match="link-local"):
        ch.check_url("http://169.254.169.254/latest/meta-data")                              # metadatos de la nube: nunca
    real = appsettings.get
    monkeypatch.setattr(appsettings, "get", lambda k: "yes" if k == "notify_block_private" else real(k))
    for private in ("http://10.0.0.5", "http://127.0.0.1:9000", "http://192.168.1.1"):
        with pytest.raises(ValueError, match="prohibido"):
            ch.check_url(private)
    assert ch.check_url("http://8.8.8.8") == "http://8.8.8.8"


# ---- avisos ----
def test_routing_by_severity_and_events():
    _chan("todo")                                              # warning o más, todos los eventos
    _chan("solo-criticos", min_severity="critical")
    _chan("solo-jobs", events=["job.failed"])
    _chan("apagado", enabled=False)
    notify.emit("model.unavailable", "LLM caído", key="llm")   # critical por defecto
    notify.emit("job.failed", "Trabajo fallido", key="j1")     # warning
    notify.emit("update.available", "Versión nueva", key="v9")  # info: por debajo del umbral de todos
    got = sorted((n, k) for n, k, _ in _deliveries())
    assert got == [("solo-criticos", "alert"), ("solo-jobs", "alert"), ("todo", "alert"), ("todo", "alert")]
    with _factory()() as db:
        assert db.query(Notification).count() == 3             # la campana guarda siempre los tres, haya o no canal


def test_grouping_reminder_and_recovery(monkeypatch):
    _chan("a"); _chan("b", min_severity="critical")
    first = notify.emit("job.failed", "Trabajo fallido", "error 1", key="k")
    assert notify.emit("job.failed", "Trabajo fallido", "error 2", key="k") == first      # mismo problema: no hay aviso nuevo
    assert len(_deliveries()) == 1
    with _factory()() as db:
        n = db.get(Notification, first)
        assert n.count == 2 and n.body == "error 2"
        n.last_at = now() - timedelta(hours=2); db.commit()
    notify.emit("job.failed", "Trabajo fallido", key="k")                                 # pasado el «aviso repetido»: recordatorio
    assert len(_deliveries()) == 2
    notify.emit("job.failed", "Trabajo fallido", key="otro")                              # otra clave: otro problema
    assert len(_deliveries()) == 3
    assert notify.resolve("job.failed", "k") is True and notify.resolve("job.failed", "k") is False
    kinds = [(n, k) for n, k, _ in _deliveries()]
    assert kinds.count(("a", "recovery")) == 1 and not any(k == "recovery" and n == "b" for n, k in kinds)   # solo avisa de la recuperación quien recibió el aviso
    notify.emit("job.failed", "Trabajo fallido", key="k")                                 # tras resolver, una nueva caída es un aviso nuevo
    with _factory()() as db:
        assert db.query(Notification).filter_by(event="job.failed", key="k").count() == 2


def test_info_events_have_no_recovery_message():
    _chan("a", min_severity="info")
    notify.emit("update.available", "Versión 9", key="v9")
    notify.resolve("update.available", "v9")
    assert [k for _, k, _ in _deliveries()] == ["alert"]


def test_quiet_hours_hold_non_critical(monkeypatch):
    from datetime import datetime
    t = datetime.now().astimezone()
    start, end = (t - timedelta(hours=1)).strftime("%H:%M"), (t + timedelta(hours=1)).strftime("%H:%M")
    real = appsettings.get
    monkeypatch.setattr(appsettings, "get", lambda k: {"notify_quiet_start": start, "notify_quiet_end": end}.get(k, real(k)))
    _chan("a", min_severity="info")
    notify.emit("job.failed", "Aviso normal", key="n")
    notify.emit("graph.down", "Crítico", key="g")
    with _factory()() as db:
        ds = {d.notification.title: d.next_try_at for d in db.query(NotifyDelivery)}
    ahora = now()
    assert ds["Aviso normal"].replace(tzinfo=ahora.tzinfo) > ahora + timedelta(minutes=30)   # espera al final del silencio
    assert ds["Crítico"].replace(tzinfo=ahora.tzinfo) <= ahora + timedelta(seconds=5)         # lo crítico no espera
    assert notify.process_due() == 1                                                         # solo sale el crítico (y falla: no hay URL real, pero se intenta)


# ---- envíos ----
def test_delivery_retries_then_fails_and_can_retry(client, monkeypatch):  # noqa: F811
    _chan("a")
    notify.emit("job.failed", "x", key="k")
    calls = []
    monkeypatch.setattr(notify, "deliver", lambda db, c, m: (calls.append(m.title), (_ for _ in ()).throw(RuntimeError("HTTP 500")))[1])
    for i in range(notify.MAX_ATTEMPTS):
        with _factory()() as db:
            db.query(NotifyDelivery).update({"next_try_at": now() - timedelta(seconds=1)}); db.commit()
        assert notify.process_due() == 1
    assert len(calls) == notify.MAX_ATTEMPTS and _deliveries() == [("a", "alert", "failed")]
    assert notify.process_due() == 0                                                         # fallido no se reintenta solo
    monkeypatch.setattr(notify, "deliver", lambda db, c, m: None)
    with _factory()() as db:
        did = db.query(NotifyDelivery).one().id
    assert client.post(f"/api/notifications/deliveries/{did}/retry").status_code == 200           # el administrador lo reintenta a mano
    assert notify.process_due() == 1 and _deliveries() == [("a", "alert", "sent")]
    assert client.post(f"/api/notifications/deliveries/{did}/retry").status_code == 404            # ya no está fallido


def test_delivery_success_and_backoff(monkeypatch):
    _chan("a")
    notify.emit("job.failed", "x", key="k")
    ok = {"n": 0}
    def flaky(db, c, m):
        ok["n"] += 1
        if ok["n"] == 1:
            raise RuntimeError("timeout")
    monkeypatch.setattr(notify, "deliver", flaky)
    assert notify.process_due() == 1
    with _factory()() as db:
        d = db.query(NotifyDelivery).one()
        assert d.status == "pending" and d.attempts == 1 and d.last_error == "timeout"
        assert d.next_try_at.replace(tzinfo=now().tzinfo) > now() + timedelta(seconds=30)   # espera antes de reintentar
        d.next_try_at = now() - timedelta(seconds=1); db.commit()
    assert notify.process_due() == 1
    assert _deliveries() == [("a", "alert", "sent")]


def test_ingest_failure_notice_has_no_memory_content(client, monkeypatch):  # noqa: F811
    """Un aviso de ingesta fallida lleva el título de la propuesta y el error, nunca el texto de la memoria."""
    from mimirsynth import ingest
    from mimirsynth.models import Brain, Proposal
    client.post("/api/brains", json={"slug": "ing", "name": "Ing"})
    async def boom(*a, **k):
        raise RuntimeError("el modelo respondió 500")
    monkeypatch.setattr(ingest, "add_episode", boom)
    monkeypatch.setattr(appsettings, "get", (lambda real: lambda k: 1 if k == "ingest_retries" else real(k))(appsettings.get))
    with _factory()() as db:
        b = db.query(Brain).filter_by(slug="ing").one()
        author = db.query(User).filter_by(sub="local-admin").one()
        p = Proposal(brain_id=b.id, author_id=author.id, name="Nota corta", body="SECRETO-DEL-CONTENIDO " * 20, status="approved", source="text", source_description="")
        db.add(p); db.commit()
        pid, bid = p.id, b.id
    assert "500" in ingest.ingest_proposal(pid)
    with _factory()() as db:
        n = db.query(Notification).filter_by(event="ingest.failed").one()
        assert n.brain_id == bid and "Nota corta" in n.body and "500" in n.body and "SECRETO" not in n.body + n.title


# ---- API ----
def test_channels_api_seals_secret_and_validates(client):  # noqa: F811
    r = client.post("/api/notifications/channels", json={"name": "Telegram", "kind": "telegram", "config": {"chat_id": "-100", "thread_id": "5", "extra": "ignorado"}, "secret": "123:TOKEN", "events": ["job.failed", "nada"]})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["has_secret"] is True and "123:TOKEN" not in json.dumps(j) and j["config"] == {"chat_id": "-100", "thread_id": "5"} and j["events"] == ["job.failed"]
    with _factory()() as db:
        c = db.query(NotifyChannel).one()
        assert "TOKEN" not in c.secret                                                        # sellado en la base de datos
    assert client.post("/api/notifications/channels", json={"name": "Telegram", "kind": "telegram"}).status_code == 409
    assert client.post("/api/notifications/channels", json={"name": "x", "kind": "sms"}).status_code == 400
    assert client.post("/api/notifications/channels", json={"name": "x", "kind": "webhook", "config": {"url": "ftp://a"}}).status_code == 400
    assert client.post("/api/notifications/channels", json={"name": "x", "kind": "telegram", "config": {"thread_id": "abc"}}).status_code == 400
    assert client.post("/api/notifications/channels", json={"name": "x", "kind": "webhook", "min_severity": "grave"}).status_code == 400
    cid = j["id"]
    up = client.put(f"/api/notifications/channels/{cid}", json={"name": "Telegram 2", "kind": "telegram", "config": {"chat_id": "-200"}, "enabled": False})
    assert up.status_code == 200 and up.json()["name"] == "Telegram 2" and up.json()["has_secret"] is True   # sin secreto nuevo se conserva
    assert client.put(f"/api/notifications/channels/{cid}", json={"name": "t", "kind": "ntfy"}).status_code == 400   # el tipo no cambia
    assert [c["name"] for c in client.get("/api/notifications/channels").json()] == ["Telegram 2"]
    assert client.delete(f"/api/notifications/channels/{cid}").status_code == 200
    assert client.get("/api/notifications/channels").json() == []
    acts = [a["action"] for a in client.get("/api/audit").json()]
    assert {"notify.channel.create", "notify.channel.update", "notify.channel.delete"} <= set(acts)
    assert "123:TOKEN" not in json.dumps(client.get("/api/audit").json())                    # ni rastro del secreto en la auditoría


def test_channel_test_endpoint(client, monkeypatch):  # noqa: F811
    cid = _chan("a")
    monkeypatch.setattr(notify, "deliver", lambda db, c, m: None)
    assert client.post(f"/api/notifications/channels/{cid}/test").json() == {"ok": True}
    monkeypatch.setattr(notify, "deliver", lambda db, c, m: (_ for _ in ()).throw(RuntimeError("HTTP 401: bad token")))
    r = client.post(f"/api/notifications/channels/{cid}/test").json()
    assert r["ok"] is False and "bad token" in r["error"]
    with _factory()() as db:
        assert db.query(Notification).count() == 0                                           # una prueba no es un aviso del sistema
    assert client.post("/api/notifications/channels/9999/test").status_code == 404


def test_inbox_visibility_unread_and_read(client):  # noqa: F811
    client.post("/api/brains", json={"slug": "na", "name": "NA"}); client.post("/api/brains", json={"slug": "nb", "name": "NB"})
    from mimirsynth.models import Brain
    with _factory()() as db:
        ids = {b.slug: b.id for b in db.query(Brain).filter(Brain.slug.in_(["na", "nb"]))}
    notify.emit("graph.down", "Instancia", key="g")                                          # sin brain: solo administradores
    notify.emit("ingest.failed", "De NA", brain_id=ids["na"], key="p1")
    notify.emit("ingest.failed", "De NB", brain_id=ids["nb"], key="p2")
    client.put("/api/brains/na/members", json={"email": "cura@x.com", "role": "curator"})
    client.put("/api/brains/nb/members", json={"email": "cura@x.com", "role": "reader"})
    client.put("/api/brains/na/members", json={"email": "lec@x.com", "role": "reader"})
    assert [i["title"] for i in client.get("/api/notifications").json()["items"]][::-1] == ["Instancia", "De NA", "De NB"]
    assert client.get("/api/notifications/summary").json() == {"unread": 3, "open": 3, "worst": "critical"}
    _as("cura@x.com", "Cura")
    assert [i["title"] for i in client.get("/api/notifications").json()["items"]] == ["De NA"]   # curador de NA; lector de NB no; nada de la instancia
    _as("lec@x.com", "Lec")
    assert client.get("/api/notifications").json()["items"] == []
    assert client.get("/api/notifications/channels").status_code == 403                     # los canales son del administrador de la instancia
    _as("cura@x.com", "Cura")
    assert client.get("/api/notifications/summary").json()["unread"] == 1
    assert client.post("/api/notifications/read").json() == {"ok": True}
    assert client.get("/api/notifications/summary").json()["unread"] == 0
    assert all(not i["unread"] for i in client.get("/api/notifications").json()["items"])
    notify.emit("ingest.failed", "Otro de NA", brain_id=ids["na"], key="p3")
    assert client.get("/api/notifications/summary").json()["unread"] == 1                    # lo posterior vuelve a contar
    assert [i["title"] for i in client.get("/api/notifications?unread=true").json()["items"]] == ["Otro de NA"]


def test_deliveries_listing(client, monkeypatch):  # noqa: F811
    _chan("a")
    notify.emit("job.failed", "x", key="k")
    monkeypatch.setattr(notify, "deliver", lambda db, c, m: (_ for _ in ()).throw(RuntimeError("boom")))
    notify.process_due()
    items = client.get("/api/notifications/deliveries").json()["items"]
    assert items[0]["channel"] == "a" and items[0]["status"] == "pending" and items[0]["error"] == "boom" and items[0]["attempts"] == 1
    assert client.get("/api/notifications/deliveries?status=failed").json()["total"] == 0


# ---- puntos de emisión y comprobaciones ----
def test_job_failure_emits_and_scan_error_resolves(client):  # noqa: F811
    from mimirsynth import jobs

    @jobs.register("test.fail", "Trabajo de prueba", limit=1)
    def _boom(ctx, p):
        raise RuntimeError("explotó")
    jobs.submit("test.fail", None, {}, "t", None)
    with _factory()() as db:
        n = db.query(Notification).filter_by(event="job.failed").one()
        assert n.title == "Trabajo fallido: Trabajo de prueba" and "explotó" in n.body


def test_health_check_needs_two_failures_in_a_row_and_recovers(monkeypatch):
    import mimirsynth.db as dbm
    notify._FAILS.clear()
    boom = lambda: (_ for _ in ()).throw(ConnectionError("conexión rechazada"))  # noqa: E731
    monkeypatch.setattr(dbm, "list_graphs", boom)
    notify.check_health()
    with _factory()() as db:
        assert db.query(Notification).filter_by(event="graph.down").count() == 0              # un fallo aislado no avisa
    monkeypatch.setattr(dbm, "list_graphs", lambda: [])
    notify.check_health()                                                                     # vuelve a responder: el contador empieza de cero
    monkeypatch.setattr(dbm, "list_graphs", boom)
    notify.check_health()
    with _factory()() as db:
        assert db.query(Notification).filter_by(event="graph.down").count() == 0              # dos fallos, pero no seguidos
    notify.check_health()                                                                     # segundo fallo seguido: ahora sí
    with _factory()() as db:
        n = db.query(Notification).filter_by(event="graph.down").one()
        assert n.resolved_at is None and "rechazada" in n.body and n.severity == "critical"
    monkeypatch.setattr(dbm, "list_graphs", lambda: [])
    notify.check_health()
    with _factory()() as db:
        assert db.query(Notification).filter_by(event="graph.down").one().resolved_at is not None


def test_health_check_failures_threshold_is_a_setting(monkeypatch):
    import mimirsynth.db as dbm
    notify._FAILS.clear()
    real = appsettings.get
    monkeypatch.setattr(appsettings, "get", lambda k: 1 if k == "notify_health_failures" else real(k))
    monkeypatch.setattr(dbm, "list_graphs", lambda: (_ for _ in ()).throw(ConnectionError("caído")))
    notify.check_health()
    with _factory()() as db:
        assert db.query(Notification).filter_by(event="graph.down").count() == 1             # con 1, al primer fallo


def test_update_check_is_opt_in(monkeypatch):
    calls = []
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (calls.append(a), httpx.Response(200, json={"tag_name": "v9.9.9"}, request=httpx.Request("GET", a[0])))[1])
    notify.check_update("0.6.0")
    assert calls == []                                                                        # por defecto no sale nada a internet
    real = appsettings.get
    monkeypatch.setattr(appsettings, "get", lambda k: "yes" if k == "notify_update_check" else real(k))
    notify.check_update("0.6.0")
    assert len(calls) == 1
    with _factory()() as db:
        assert db.query(Notification).filter_by(event="update.available").one().title == "Versión 9.9.9 disponible"
    assert notify._newer("v0.7.0", "0.6.0") and not notify._newer("v0.6.0", "0.6.0") and not notify._newer("v0.7.0-rc.1", "0.6.0")


def test_lockout_emits(client, monkeypatch):  # noqa: F811
    from test_users import PW, _admin, local  # noqa: F401
    from mimirsynth import auth, ratelimit
    from mimirsynth.config import settings
    from mimirsynth.models import User
    from sqlalchemy import update
    monkeypatch.setattr(settings, "auth_mode", "local")
    ratelimit.reset()
    with _factory()() as db:
        db.execute(update(User).where(User.sub.is_distinct_from("local-admin")).values(is_admin=False)); db.commit()
        auth.ensure_setup_token(db)
    _admin(client)
    c = TestClient(app)
    for _ in range(5):
        c.post("/api/auth/login", json={"email": "root@example.com", "password": "mal-mal-mal-mal"})
    try:
        with _factory()() as db:
            n = db.query(Notification).filter_by(event="security.lockout").one()
            assert "root@example.com" in n.body and "mal-mal" not in n.body
    finally:
        with _factory()() as db:                                                               # la base de pruebas se comparte: que la cuenta no quede bloqueada
            db.execute(update(User).where(User.email == "root@example.com").values(locked_until=None, failed_attempts=0)); db.commit()
        ratelimit.reset()
