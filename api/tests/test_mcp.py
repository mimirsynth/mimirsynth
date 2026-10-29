"""Servidor MCP propio: protocolo, herramientas, roles del token y protecciones."""
import pytest
from fastapi.testclient import TestClient

from test_control import client  # noqa: F401

from mimirsynth import mcp_server
from mimirsynth.main import app
from mimirsynth.models import Proposal
from mimirsynth.store import _factory


def rpc(c, slug, method, params=None, rid=1, token=None, headers=None):
    msg = {"jsonrpc": "2.0", "method": method, **({"id": rid} if rid is not None else {}), **({"params": params} if params is not None else {})}
    return c.post(f"/api/brains/{slug}/mcp", json=msg, headers={**({"Authorization": f"Bearer {token}"} if token else {}), **(headers or {})})


def _token(client, slug, role):  # noqa: F811
    client.post("/api/brains", json={"slug": slug, "name": slug.upper()})
    r = client.post(f"/api/brains/{slug}/tokens", json={"name": f"t-{role}", "role": role})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_mcp_protocol_basics(client):  # noqa: F811
    tok = _token(client, "mcp1", "reader")
    c = TestClient(app)
    r = rpc(c, "mcp1", "initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}, token=tok).json()
    assert r["result"]["protocolVersion"] == "2025-03-26" and r["result"]["serverInfo"]["name"] == "mimirsynth" and "tools" in r["result"]["capabilities"]
    assert rpc(c, "mcp1", "initialize", {"protocolVersion": "1999-01-01"}, token=tok).json()["result"]["protocolVersion"] == mcp_server.SUPPORTED[0]  # versión desconocida: la nuestra
    assert rpc(c, "mcp1", "notifications/initialized", rid=None, token=tok).status_code == 202  # notificación: sin cuerpo
    assert rpc(c, "mcp1", "ping", token=tok).json()["result"] == {}
    assert [t["name"] for t in rpc(c, "mcp1", "tools/list", token=tok).json()["result"]["tools"]] == ["recall", "remember"]
    assert rpc(c, "mcp1", "no/existe", token=tok).json()["error"]["code"] == -32601
    assert rpc(c, "mcp1", "tools/call", {"name": "borrar_todo", "arguments": {}}, token=tok).json()["error"]["code"] == -32602
    assert c.post("/api/brains/mcp1/mcp", content=b"{no es json", headers={"Authorization": f"Bearer {tok}"}).status_code == 400
    batch = c.post("/api/brains/mcp1/mcp", json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}],
                   headers={"Authorization": f"Bearer {tok}"}).json()
    assert [x["id"] for x in batch] == [1, 2]
    assert c.get("/api/brains/mcp1/mcp").status_code == 405


def test_mcp_auth_and_isolation(client):  # noqa: F811
    tok = _token(client, "mcp2", "reader")
    other = _token(client, "mcp3", "reader")
    anon = TestClient(app)
    assert rpc(anon, "mcp2", "ping").status_code in (401, 403)  # sin token
    assert rpc(client, "mcp2", "ping").status_code == 401  # la sesión del navegador (aquí, administrador local) no vale: solo tokens
    assert rpc(anon, "mcp2", "ping", token="mst_falso").status_code == 401
    assert rpc(anon, "mcp2", "ping", token=other).status_code == 404  # el token de otro brain no abre este
    assert rpc(anon, "mcp2", "ping", token=tok, headers={"Origin": "https://evil.example"}).status_code == 403  # un navegador de otro origen no
    assert rpc(anon, "mcp2", "ping", token=tok, headers={"Origin": "http://testserver"}).status_code == 200


def test_mcp_recall_tool(client, monkeypatch):  # noqa: F811
    tok = _token(client, "mcp4", "reader")
    seen = {}
    def fake(brain_id, graph, query, facts, chunks, max_chars, n_docs=None, lang="es"):
        seen.update(graph=graph, query=query, facts=facts, docs=n_docs)
        return {"context": "## Hechos\n- Nextcloud corre en Notus", "facts": [], "chunks": []}
    monkeypatch.setattr(mcp_server, "recall", fake)
    c = TestClient(app)
    r = rpc(c, "mcp4", "tools/call", {"name": "recall", "arguments": {"query": "dónde corre Nextcloud", "facts": 3, "docs": 0}}, token=tok).json()["result"]
    assert r["isError"] is False and "Notus" in r["content"][0]["text"]
    assert seen == {"graph": "mcp4", "query": "dónde corre Nextcloud", "facts": 3, "docs": 0}  # el brain sale del token, no de los argumentos
    bad = rpc(c, "mcp4", "tools/call", {"name": "recall", "arguments": {"query": ""}}, token=tok).json()["result"]
    assert bad["isError"] is True and "query" in bad["content"][0]["text"]  # error para el modelo, no del protocolo
    monkeypatch.setattr(mcp_server, "recall", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("FalkorDB caído")))
    down = rpc(c, "mcp4", "tools/call", {"name": "recall", "arguments": {"query": "x"}}, token=tok).json()["result"]
    assert down["isError"] is True and "FalkorDB caído" in down["content"][0]["text"]


def test_mcp_remember_respects_roles(client, monkeypatch):  # noqa: F811
    from mimirsynth import ingest
    monkeypatch.setattr(ingest, "enabled", lambda: False)  # sin LLM: la aprobada no se ingiere
    c = TestClient(app, headers={"Accept-Language": "es"})
    args = {"name": "Nextcloud en Notus", "body": "Nextcloud corre en el LXC Notus desde octubre.", "confidence": 0.9}
    reader_tok = _token(client, "mcp5", "reader")
    r = rpc(c, "mcp5", "tools/call", {"name": "remember", "arguments": args}, token=reader_tok).json()["result"]
    assert r["isError"] is True and "lector" in r["content"][0]["text"]  # un lector no propone
    contrib = client.post("/api/brains/mcp5/tokens", json={"name": "c", "role": "contributor"}).json()["token"]
    r = rpc(c, "mcp5", "tools/call", {"name": "remember", "arguments": args}, token=contrib).json()["result"]
    assert r["isError"] is False and "cuarentena" in r["content"][0]["text"]
    curator = client.post("/api/brains/mcp5/tokens", json={"name": "k", "role": "curator"}).json()["token"]
    r = rpc(c, "mcp5", "tools/call", {"name": "remember", "arguments": {**args, "name": "Otra"}}, token=curator).json()["result"]
    assert r["isError"] is False and "aprobada" in r["content"][0]["text"]
    with _factory()() as db:
        got = {p.name: p.status for p in db.query(Proposal).filter(Proposal.name.in_(["Nextcloud en Notus", "Otra"]))}
    assert got == {"Nextcloud en Notus": "pending", "Otra": "approved"}
    assert rpc(c, "mcp5", "tools/call", {"name": "remember", "arguments": {"name": "sin cuerpo"}}, token=contrib).json()["result"]["isError"] is True
