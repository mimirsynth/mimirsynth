"""Procedencia en el visor del grafo: cada nodo y hecho dice de qué orígenes viene (tipo de origen, documento, contribuidor, token)."""
import os

import pytest

from test_control import client  # noqa: F401
from test_docs import MD, _upload, fake_index  # noqa: F401

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
pytestmark = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
GRAPH = "zz-test-provenance"


@pytest.fixture()
def falkor(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.client.cache_clear()
    c = dbm.client()
    if GRAPH in c.list_graphs():
        c.select_graph(GRAPH).delete()
    yield c.select_graph(GRAPH)
    c.select_graph(GRAPH).delete()
    dbm.client.cache_clear()


def _link_episode(pid: int, ep: str) -> None:
    from mimirsynth.models import Proposal
    from mimirsynth.store import _factory
    with _factory()() as db:
        db.get(Proposal, pid).episode_uuid = ep
        db.commit()


def test_graph_reports_sources_per_node_and_fact(client, fake_index, falkor, monkeypatch):  # noqa: F811
    from mimirsynth import ingest
    monkeypatch.setattr(ingest, "enabled", lambda: False)  # sin LLM: las propuestas no se ingieren; el episodio se enlaza a mano
    assert client.post("/api/brains", json={"slug": "prov", "name": "Prov", "graph_name": GRAPH}).status_code == 201
    base = "/api/brains/prov"
    _, up = _upload(client, "prov", "guia.md", MD.encode(), title="Guía de backups")
    did = up.json()["id"]
    from_doc = client.post(f"{base}/docs/{did}/promote", json={"chunk": 1}).json()["id"]
    tok = client.post(f"{base}/tokens", json={"name": "agente-claude", "role": "contributor"}).json()["token"]
    from_agent = client.post(f"{base}/proposals", json={"name": "Agente", "body": "Nextcloud corre en Notus."}, headers={"Authorization": f"Bearer {tok}"}).json()["id"]
    _link_episode(from_doc, "ep-doc")
    _link_episode(from_agent, "ep-agent")
    falkor.query(
        "CREATE (a:Entity:Server {uuid:'A', name:'Notus'}), (b:Entity {uuid:'B', name:'Nextcloud'}), (c:Entity {uuid:'C', name:'Huérfana'}), "
        "(d:Entity {uuid:'D', name:'Importada'}), "
        "(e1:Episodic {uuid:'ep-doc', source:'text'}), (e2:Episodic {uuid:'ep-agent', source:'message'}), (e3:Episodic {uuid:'ep-raw', source:'json'}), "
        "(e1)-[:MENTIONS]->(a), (e2)-[:MENTIONS]->(a), (e2)-[:MENTIONS]->(b), (e3)-[:MENTIONS]->(d), "
        "(a)-[:RELATES_TO {uuid:'f1', name:'HOSTS', fact:'Notus aloja Nextcloud', episodes:['ep-doc','ep-agent'], created_at:'2026-10-01T00:00:00Z'}]->(b), "
        "(b)-[:RELATES_TO {uuid:'f2', name:'USES', fact:'Nextcloud usa la importada', episodes:['ep-raw'], created_at:'2026-10-01T00:00:00Z'}]->(d)")

    plain = client.get(f"{base}/graph").json()  # sin agrupación: no se calcula (el visor actual no la usa)
    assert "groups" not in plain and "sources" not in plain["nodes"][0] and not any(k.endswith("episodes") for k in plain["links"][0])
    r = client.get(f"{base}/graph", params={"group_by": "source"}, headers={"Accept-Language": "es"})
    assert r.status_code == 200, r.text
    g = r.json()
    nodes, links = {n["uuid"]: n for n in g["nodes"]}, {x["uuid"]: x for x in g["links"]}
    assert g["group_by"] == "source" and not any(k.endswith("episodes") for k in links["f1"])
    # Notus: un pasaje promovido de un documento y una propuesta de un agente → dos orígenes
    a = nodes["A"]
    assert a["sources"] == ["source:document", "source:message"] and a["source_count"] == 2
    assert a["provenance"]["document"] == [f"document:{did}"] and len(a["provenance"]["token"]) == 1
    assert len(a["provenance"]["author"]) == 1  # las dos propuestas son de la misma persona: un solo contribuidor
    assert a["provenance"]["label"] == ["label:Server"]
    # Nextcloud: la menciona el agente y su hecho visible con Notus viene también del documento
    assert sorted(nodes["B"]["sources"]) == ["source:document", "source:json", "source:message"] and nodes["B"]["source_count"] == 3
    # sin episodio: sin origen; episodio sin propuesta: solo su tipo
    assert nodes["C"]["sources"] == [] and nodes["C"]["source_count"] == 0 and nodes["C"]["provenance"]["label"] == []
    assert nodes["D"]["sources"] == ["source:json"] and nodes["D"]["provenance"]["author"] == []
    # hechos: según sus episodios
    assert links["f1"]["source_count"] == 2 and links["f2"]["sources"] == ["source:json"] and links["f1"]["provenance"]["label"] == []
    # catálogo de orígenes con nombre visible y recuentos, de mayor a menor
    src = {x["key"]: x for x in g["groups"]["source"]}
    assert src["source:document"]["name"] == "Documento" and src["source:message"]["name"] == "Mensaje" and src["source:json"]["name"] == "JSON"
    assert (src["source:json"]["nodes"], src["source:json"]["facts"]) == (2, 1)
    assert g["groups"]["source"][0]["nodes"] >= g["groups"]["source"][-1]["nodes"]
    assert g["groups"]["document"] == [{"key": f"document:{did}", "name": "Guía de backups", "nodes": 2, "facts": 1}]
    assert g["groups"]["token"][0]["name"] == "agente-claude"

    by_doc = client.get(f"{base}/graph", params={"group_by": "document"}).json()
    assert {n["uuid"]: n["source_count"] for n in by_doc["nodes"]} == {"A": 1, "B": 1, "C": 0, "D": 0}
    en = client.get(f"{base}/graph", params={"group_by": "source"}, headers={"Accept-Language": "en"}).json()
    assert {x["key"]: x["name"] for x in en["groups"]["source"]}["source:message"] == "Message"
    assert client.get(f"{base}/graph", params={"group_by": "planeta"}).status_code == 422
