"""Política de secretos de cada brain (#116): propuestas, MCP, decisor, auditoría, excepciones y análisis en solo lectura."""
import json

from fastapi.testclient import TestClient

from test_control import _as, client  # noqa: F401
from test_mcp import rpc

from mimirsynth import decider, deciders_admin, ingest
from mimirsynth.main import app
from mimirsynth.models import Audit, Proposal
from mimirsynth.store import _factory

TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8J9k0" * 2  # con forma de token de GitHub, montado para no dejarlo literal en el código
POSSIBLE = "DB_PASSWORD=" + "Zq8!mW2#pL5v"


def _brain(client, slug, mode=None):  # noqa: F811
    client.post("/api/brains", json={"slug": slug, "name": slug.upper()})
    if mode:
        assert client.patch(f"/api/brains/{slug}", json={"secret_mode": mode}).json()["secret_mode"] == mode
    return {"Authorization": "Bearer " + client.post(f"/api/brains/{slug}/tokens", json={"name": "c", "role": "contributor"}).json()["token"]}


def _audits(action):
    with _factory()() as db:
        return [json.dumps(a.detail) for a in db.query(Audit).filter(Audit.action == action)]


def test_mask_by_default_and_decider_waits_for_a_person(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ingest, "enabled", lambda: False)
    monkeypatch.setattr(deciders_admin, "default_decider", lambda db: object())
    monkeypatch.setattr(decider, "triage", lambda *a, **k: (_ for _ in ()).throw(AssertionError("el decisor no debe ver esta propuesta")))
    h = _brain(client, "sg-mask")
    r = client.post("/api/brains/sg-mask/proposals", headers=h, json={"name": f"Token {TOKEN}", "body": f"El token es {TOKEN}.\n{POSSIBLE}"})
    assert r.status_code == 201
    p = client.get(f"/api/brains/sg-mask/proposals/{r.json()['id']}").json()
    assert TOKEN not in p["name"] + p["body"] and "[secreto eliminado: token de GitHub]" in p["body"] and p["name"] == "Token [secreto eliminado: token de GitHub]"
    assert "Zq8!mW2#pL5v" in p["body"]                                                       # lo posible no se toca: se marca
    got = {(s["field"], s["rule"], s["action"]) for s in p["secrets"]}
    assert got == {("name", "github_token", "masked"), ("body", "github_token", "masked"), ("body", "assigned_secret", "flagged")}
    flagged = next(s for s in p["secrets"] if s["action"] == "flagged")
    assert p["body"][flagged["start"]:flagged["end"]] == "Zq8!mW2#pL5v"                   # posiciones sobre el texto guardado
    assert p["status"] == "pending" and p["decision"] is None                                 # el decisor no la aprueba sola
    assert all(TOKEN not in a and "Zq8!" not in a for a in _audits("proposal.submit"))       # ni la auditoría guarda valores


def test_block_rejects_only_certain_secrets(client):  # noqa: F811
    h = _brain(client, "sg-block", "block")
    r = client.post("/api/brains/sg-block/proposals", headers={**h, "Accept-Language": "es"}, json={"name": "Clave", "body": f"usa {TOKEN}"})
    assert r.status_code == 422 and "token de GitHub" in r.json()["detail"] and TOKEN not in r.json()["detail"]
    en = client.post("/api/brains/sg-block/proposals", headers={**h, "Accept-Language": "en"}, json={"name": "Clave", "body": f"usa {TOKEN}"})
    assert en.status_code == 422 and "GitHub token" in en.json()["detail"]
    assert any("github_token" in a and TOKEN not in a for a in _audits("proposal.blocked"))
    with _factory()() as db:
        assert db.query(Proposal).filter(Proposal.name == "Clave").count() == 0
    ok = client.post("/api/brains/sg-block/proposals", headers=h, json={"name": "Posible", "body": POSSIBLE})
    assert ok.status_code == 201 and ok.json()["secrets"][0]["action"] == "flagged"         # lo posible no bloquea


def test_warn_changes_nothing_and_flags_everything(client):  # noqa: F811
    h = _brain(client, "sg-warn", "warn")
    p = client.post("/api/brains/sg-warn/proposals", headers=h, json={"name": "Aviso", "body": f"usa {TOKEN}"}).json()
    full = client.get(f"/api/brains/sg-warn/proposals/{p['id']}").json()
    assert TOKEN in full["body"] and [(s["rule"], s["action"]) for s in full["secrets"]] == [("github_token", "flagged")]


def test_policy_validation_visibility_and_allow_list(client):  # noqa: F811
    h = _brain(client, "sg-cfg")
    assert client.patch("/api/brains/sg-cfg", json={"secret_mode": "nada"}).status_code == 400
    assert client.patch("/api/brains/sg-cfg", json={"secret_allow": "rule:inventada"}).status_code == 400
    assert client.patch("/api/brains/sg-cfg", json={"secret_allow": "(["}).status_code == 400
    assert client.patch("/api/brains/sg-cfg", json={"secret_allow": "rule:github_token"}).json()["secret_allow"] == "rule:github_token"
    p = client.post("/api/brains/sg-cfg/proposals", headers=h, json={"name": "Permitido", "body": f"usa {TOKEN}"}).json()
    assert p["secrets"] == [] and TOKEN in client.get(f"/api/brains/sg-cfg/proposals/{p['id']}").json()["body"]
    assert any("secret_allow" in a for a in _audits("brain.update"))
    client.put("/api/brains/sg-cfg/members", json={"email": "lector@x.com", "role": "reader"})
    _as("lector@x.com", "Lector")
    mine = next(b for b in client.get("/api/brains").json() if b["slug"] == "sg-cfg")
    assert "secret_mode" not in mine and "secret_allow" not in mine                         # solo lo ve quien administra el brain
    assert client.get("/api/brains/sg-cfg/secrets/scan").status_code == 403
    app.dependency_overrides.clear()


def test_mcp_remember_is_guarded(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ingest, "enabled", lambda: False)
    c = TestClient(app, headers={"Accept-Language": "es"})
    _brain(client, "sg-mcp")
    tok = client.post("/api/brains/sg-mcp/tokens", json={"name": "c", "role": "contributor"}).json()["token"]
    r = rpc(c, "sg-mcp", "tools/call", {"name": "remember", "arguments": {"name": "Acceso", "body": f"token {TOKEN}"}}, token=tok).json()["result"]
    assert r["isError"] is False
    with _factory()() as db:
        assert TOKEN not in db.query(Proposal).filter(Proposal.name == "Acceso").one().body
    client.patch("/api/brains/sg-mcp", json={"secret_mode": "block"})
    r = rpc(c, "sg-mcp", "tools/call", {"name": "remember", "arguments": {"name": "Acceso 2", "body": f"token {TOKEN}"}}, token=tok).json()["result"]
    assert r["isError"] is True and "secretos" in r["content"][0]["text"] and TOKEN not in r["content"][0]["text"]


def test_author_is_told_what_was_masked_or_flagged(client, monkeypatch):  # noqa: F811
    """Feedback on #138: a curator's proposal is masked and approved at once, so the response must say what was removed."""
    monkeypatch.setattr(ingest, "enabled", lambda: False)
    _brain(client, "sg-tell")
    cur = {"Authorization": "Bearer " + client.post("/api/brains/sg-tell/tokens", json={"name": "k", "role": "curator"}).json()["token"]}
    p = client.post("/api/brains/sg-tell/proposals", headers={**cur, "Accept-Language": "es"}, json={"name": "Acceso", "body": f"usa {TOKEN} y {TOKEN}"}).json()
    assert p["status"] == "approved" and p["review_kind"] == "direct"                         # enmascarado: el curador la aprueba al enviarla
    assert p["secrets_notice"] == "Secretos enmascarados antes de guardar: token de GitHub ×2. Lo guardado no lleva su valor."
    assert [s["action"] for s in client.get("/api/brains/sg-tell/proposals").json()["items"][0]["secrets"]] == ["masked", "masked"]  # también en la lista
    en = client.post("/api/brains/sg-tell/proposals", headers={**cur, "Accept-Language": "en"}, json={"name": "Posible", "body": POSSIBLE}).json()
    assert en["status"] == "pending" and en["secrets_notice"].startswith("Flagged for a curator to review") and "Zq8!" not in en["secrets_notice"]
    clean = client.post("/api/brains/sg-tell/proposals", headers=cur, json={"name": "Limpia", "body": "texto"}).json()
    assert clean["secrets_notice"] == ""
    c = TestClient(app, headers={"Accept-Language": "es"})
    tok = cur["Authorization"].split()[1]
    r = rpc(c, "sg-tell", "tools/call", {"name": "remember", "arguments": {"name": "Por MCP", "body": f"token {TOKEN}"}}, token=tok).json()["result"]
    text = r["content"][0]["text"]
    assert r["isError"] is False and text.startswith("Memoria guardada y aprobada") and "enmascarados antes de guardar: token de GitHub" in text and TOKEN not in text


def test_scan_existing_is_read_only_and_never_returns_values(client):  # noqa: F811
    h = _brain(client, "sg-scan", "warn")
    client.post("/api/brains/sg-scan/proposals", headers=h, json={"name": "Vieja", "body": f"La clave del despliegue es {TOKEN} y nada más"})
    client.post("/api/brains/sg-scan/proposals", headers=h, json={"name": "Limpia", "body": "Nextcloud corre en Notus"})
    out = client.get("/api/brains/sg-scan/secrets/scan").json()
    assert out["proposals"] == 2 and out["mode"] == "warn"
    assert [(r["rule"], r["count"], r["items"], r["certain"]) for r in out["rules"]] == [("github_token", 1, 1, True)]
    item = out["items"][0]
    assert item["kind"] == "proposal" and item["title"] == "Vieja" and item["findings"][0]["context"].endswith("La clave del despliegue es ")
    assert TOKEN not in json.dumps(out)
    with _factory()() as db:                                                                # no cambia nada
        assert TOKEN in db.query(Proposal).filter(Proposal.name == "Vieja").one().body
    assert _audits("secrets.scan")


def test_flagged_waits_even_for_a_curator_and_audit_hides_it(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ingest, "enabled", lambda: False)
    _brain(client, "sg-cur", "warn")
    cur = {"Authorization": "Bearer " + client.post("/api/brains/sg-cur/tokens", json={"name": "k", "role": "curator"}).json()["token"]}
    p = client.post("/api/brains/sg-cur/proposals", headers=cur, json={"name": f"Clave {TOKEN}", "body": "texto"}).json()
    assert p["status"] == "pending" and p["review_kind"] == ""                               # no se aprueba al enviarla
    ok = client.post("/api/brains/sg-cur/proposals", headers=cur, json={"name": "Limpia", "body": "texto"}).json()
    assert ok["status"] == "approved"                                                        # sin hallazgos, como siempre
    names = [json.loads(a)["name"] for a in _audits("proposal.submit") if '"Clave' in a]
    assert names == ["Clave […]"]                                                           # el título marcado no llega a la auditoría
    assert all(TOKEN not in a for a in _audits("proposal.submit"))
