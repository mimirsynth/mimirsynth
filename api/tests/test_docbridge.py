"""Puentes documento ↔ grafo: entidades mencionadas, documentos que mencionan una entidad y «promover a memoria»."""
import uuid

import pytest

from test_control import client  # noqa: F401
from test_docs import MD, _upload, fake_index  # noqa: F401

from mimirsynth import docbridge, docindex

ENTS = [
    {"uuid": "e1", "name": "TrueNAS Boreas", "type": "Server", "aliases": ["Cirrus"]},
    {"uuid": "e2", "name": "PBS", "type": "Service", "aliases": []},
    {"uuid": "e3", "name": "VM", "type": "Thing", "aliases": []},            # demasiado corto
    {"uuid": "e4", "name": "2026", "type": "Thing", "aliases": []},          # numérico
    {"uuid": "e5", "name": "Instalación", "type": "Concept", "aliases": []},
]


def test_find_mentions_matches_whole_words_aliases_and_counts():
    text = "El pool de Cirrus vive en TrueNAS Boreas. PBS hace backup; pbs también. Las VM 2026 y la subvención no cuentan. Instalación y reinstalación."
    got = {m["uuid"]: m["count"] for m in docbridge.find_mentions(text, ENTS)}
    assert got == {"e1": 2, "e2": 2, "e5": 1}                                  # alias contado con su principal; «VM», «2026» y subcadenas fuera
    assert docbridge.find_mentions("", ENTS) == [] and docbridge.find_mentions("nada de nada", ENTS) == []
    ordered = docbridge.find_mentions("PBS PBS PBS Cirrus", ENTS)
    assert [m["uuid"] for m in ordered] == ["e2", "e1"]                          # de más a menos citadas


def _slug(client):
    s = "p" + uuid.uuid4().hex[:8]
    assert client.post("/api/brains", json={"slug": s, "name": s, "graph_name": "g-" + s}).status_code == 201
    return s


def test_doc_entities_and_entity_mentions(client, fake_index, monkeypatch):
    monkeypatch.setattr(docbridge, "entities", lambda g: [{"uuid": "e9", "name": "Guía", "type": "Doc", "aliases": []}, {"uuid": "e8", "name": "CPU", "type": "HW", "aliases": []}])
    slug = _slug(client)
    _, r = _upload(client, slug, "guia.md", MD.encode())
    did = r.json()["id"]
    ents = client.get(f"/api/brains/{slug}/docs/{did}/entities").json()["entities"]
    assert [(e["name"], e["count"]) for e in ents][:2] == [("Guía", 1), ("CPU", 1)] or {e["name"] for e in ents} == {"Guía", "CPU"}
    monkeypatch.setattr(docindex, "mentions", lambda bid, phrases, limit=20: [{"document_id": did, "title": "Guía", "url": "", "chunk": 2, "heading_path": "Guía › Requisitos", "chunks": 1, "snippet": "la «CPU»"}] if "CPU" in phrases else [])
    from mimirsynth import index
    monkeypatch.setattr(index, "enabled", lambda: True)
    m = client.get(f"/api/brains/{slug}/docs/mentions", params={"entity": "e8"}).json()
    assert m["entity"] == "CPU" and m["documents"][0]["document_id"] == did and m["documents"][0]["snippet"] == "la «CPU»"
    assert client.get(f"/api/brains/{slug}/docs/mentions", params={"entity": "nada"}).status_code == 404


def test_promote_creates_quarantined_or_direct_proposal_with_provenance(client, fake_index):
    slug = _slug(client)
    _, r = _upload(client, slug, "guia.md", MD.encode())
    did = r.json()["id"]
    base = f"/api/brains/{slug}"
    assert client.post(f"{base}/docs/{did}/promote", json={"chunk": 999}).status_code == 404
    p = client.post(f"{base}/docs/{did}/promote", json={"chunk": 1})
    assert p.status_code == 201, p.text
    prop = p.json()
    assert prop["status"] in ("approved", "pending", "ingested", "failed") and "Guía" in prop["name"]
    full = client.get(f"{base}/proposals/{prop['id']}").json()
    assert "Fuente: «Guía»" in full["body"] and f"documento {did} · trozo 1" in full["source_description"] and full["confidence"] == 0.7
    dup = client.post(f"{base}/docs/{did}/promote", json={"chunk": 1})
    assert dup.status_code == 409 and f"#{prop['id']}" in dup.json()["detail"]                 # no se promueve dos veces
    edited = client.post(f"{base}/docs/{did}/promote", json={"chunk": 0, "text": "  Solo esta frase editada.  ", "name": "Mi nombre"}).json()
    body = client.get(f"{base}/proposals/{edited['id']}").json()["body"]
    assert edited["name"] == "Mi nombre" and body.startswith("Solo esta frase editada.\n\nFuente:")


# ---- relaciones entre las entidades mencionadas ----
class _FakeGraph:
    """Sustituto mínimo del grafo: devuelve filas fijas con la cabecera de FACT_RETURN y recuerda la consulta."""
    HEADER = ["uuid", "name", "fact", "valid_at", "invalid_at", "expired_at", "created_at", "reference_time", "episodes", "source", "source_uuid", "target", "target_uuid"]

    def __init__(self, facts):
        self.facts, self.queries = facts, []

    def query(self, q, params=None):
        self.queries.append((q, params))
        res = type("R", (), {})()
        res.header = [[1, h] for h in self.HEADER]
        res.result_set = self.facts
        return res


def _fact(uid, rel, fact, a, b, valid="2026-01-01T00:00:00Z", invalid=None):
    return [uid, rel, fact, valid, invalid, None, valid, None, [], a[1], a[0], b[1], b[0]]


MIR, LXC, SIR = ("e1", "MimirSynth"), ("e2", "LXC132"), ("e3", "Sirio")


def test_relations_between_current_expired_aliases_and_limit(monkeypatch):
    g = _FakeGraph([
        _fact("r1", "RUNS_ON", "MimirSynth corre en el LXC132", MIR, LXC, valid="2026-10-01T00:00:00Z"),
        _fact("r2", "MOUNTED_ON", "Sirio está montado en el LXC132", SIR, LXC, valid="2026-09-01T00:00:00Z"),
        _fact("r3", "RUNS_ON", "MimirSynth corría en el LXC120", MIR, LXC, valid="2026-05-01T00:00:00Z", invalid="2026-09-30T00:00:00Z"),
    ])
    monkeypatch.setattr(docbridge, "graph", lambda name: g)
    out = docbridge.relations_between("g", ["e1", "e2", "e3"], {"MOUNTED_ON": "STORED_ON"})
    assert [(r["source"], r["name"], r["target"]) for r in out["relations"]] == [("MimirSynth", "RUNS_ON", "LXC132"), ("Sirio", "STORED_ON", "LXC132")]   # vigentes; alias aplicado
    assert out["total"] == 2 and out["expired_count"] == 1                                                  # hay un hecho caducado que se puede mostrar
    assert out["relations"][0]["fact"] == "MimirSynth corre en el LXC132" and out["relations"][0]["status"] == "current"
    q, params = g.queries[0]
    assert "a.uuid IN $ids AND b.uuid IN $ids" in q and params == {"ids": ["e1", "e2", "e3"]}                 # una sola consulta, solo entre las entidades mencionadas
    both = docbridge.relations_between("g", ["e1", "e2", "e3"], expired=True)
    assert both["total"] == 3 and [r["status"] for r in both["relations"]].count("invalidated") == 1
    assert len(docbridge.relations_between("g", ["e1", "e2", "e3"], limit=1)["relations"]) == 1 and docbridge.relations_between("g", ["e1", "e2", "e3"], limit=1)["total"] == 2
    assert docbridge.relations_between("g", ["e1"]) == {"relations": [], "total": 0, "expired_count": 0} and len(g.queries) == 4     # con una sola entidad no se consulta


def test_doc_entities_endpoint_returns_relations_and_survives_graph_errors(client, fake_index, monkeypatch):  # noqa: F811
    monkeypatch.setattr(docbridge, "entities", lambda g: [{"uuid": "e1", "name": "Guía", "type": "Doc", "aliases": []}, {"uuid": "e2", "name": "CPU", "type": "HW", "aliases": []}])
    slug = _slug(client)
    _, r = _upload(client, slug, "guia.md", MD.encode())
    did = r.json()["id"]
    seen = {}
    def fake(graph_name, uuids, amap=None, expired=False, limit=30):
        seen.update(uuids=sorted(uuids), expired=expired, limit=limit)
        return {"relations": [{"uuid": "r1", "source_uuid": "e1", "source": "Guía", "target_uuid": "e2", "target": "CPU", "name": "mentions", "fact": "La guía habla de la CPU", "valid_at": None, "invalid_at": None, "status": "current"}], "total": 1, "expired_count": 2}
    monkeypatch.setattr(docbridge, "relations_between", fake)
    out = client.get(f"/api/brains/{slug}/docs/{did}/entities", params={"expired": "true", "relations": 5}).json()
    assert out["relations"][0]["fact"] == "La guía habla de la CPU" and out["total"] == 1 and out["expired_count"] == 2
    assert seen == {"uuids": ["e1", "e2"], "expired": True, "limit": 5}
    assert {e["name"] for e in out["entities"]} == {"Guía", "CPU"}
    monkeypatch.setattr(docbridge, "relations_between", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("FalkorDB caído")))
    out = client.get(f"/api/brains/{slug}/docs/{did}/entities").json()
    assert out["relations"] == [] and {e["name"] for e in out["entities"]} == {"Guía", "CPU"}                  # un fallo al leer relaciones no esconde las entidades
    seen.clear(); monkeypatch.setattr(docbridge, "relations_between", fake)
    assert client.get(f"/api/brains/{slug}/docs/{did}/entities", params={"relations": 0}).json()["relations"] == [] and not seen
