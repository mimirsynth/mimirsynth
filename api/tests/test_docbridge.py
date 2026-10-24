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
