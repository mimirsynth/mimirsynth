"""Aliases equal to the entity's own name (#194): merges no longer write them, the entity page never shows them, and a cleanup removes
the ones older merges wrote; undoing a merge still works."""
import os

import pytest

from test_control import client  # noqa: F401

from mimirsynth.entity_types import name_key, other_names

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-entity-aliases"


def test_other_names():
    assert name_key("  Lyra  Box ") == name_key("lyra box") == "lyra box"
    assert other_names("Lyra", ["Lyra", "lyra ", "LYRA", "lyra-vps", "Lyra VPS", "lyra vps", None, 3, ""]) == ["lyra-vps", "Lyra VPS"]
    assert other_names("Cognee", ["Cognee 1.6.2"]) == ["Cognee 1.6.2"] and other_names("X", None) == []


@pytest.fixture()
def g(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.client.cache_clear()
    c = dbm.client()
    for name in [GRAPH, *[x for x in c.list_graphs() if x.startswith(f"_snap_{GRAPH}_")]]:
        if name in c.list_graphs():
            c.select_graph(name).delete()
    graph = c.select_graph(GRAPH)
    graph.query("CREATE (:Entity:Host {uuid:'k', name:'Lyra'}), (:Entity:Host {uuid:'d1', name:'lyra'}), (:Entity:Host {uuid:'d2', name:'Lyra VPS'}), "
                "(:Entity:Host {uuid:'old', name:'Vaultwarden', aliases:['Vaultwarden', 'vaultwarden', 'Vaultwarden v1.30']}), (:Entity {uuid:'x', name:'X'})")
    graph.query("MATCH (a:Entity {uuid:'d1'}), (b:Entity {uuid:'x'}) CREATE (a)-[:RELATES_TO {uuid:'f1', name:'RUNS', fact:'lyra runs X'}]->(b)")
    yield graph
    for name in [GRAPH, *[x for x in c.list_graphs() if x.startswith(f"_snap_{GRAPH}_")]]:
        c.select_graph(name).delete()
    dbm.client.cache_clear()


def _aliases(g, uuid):
    return g.query("MATCH (n:Entity {uuid:$u}) RETURN coalesce(n.aliases, [])", {"u": uuid}).result_set[0][0]


@pytest.mark.skipif(not FALKOR, reason="needs a disposable FalkorDB (MIMIRSYNTH_TEST_FALKOR=host)")
def test_merge_read_cleanup_and_undo(client, g):  # noqa: F811
    from mimirsynth import entity_aliases
    assert client.post("/api/brains", json={"slug": "eal", "name": "EAL", "graph_name": GRAPH}).status_code == 201
    base = "/api/brains/eal/vocab"
    # a duplicate with the same name apart from case adds no alias; one with another name does
    assert client.post(f"{base}/duplicates/merge", json={"keeper": "k", "merge": ["d1", "d2"]}).status_code == 200
    assert _aliases(g, "k") == ["Lyra VPS"]
    assert g.query("MATCH (:Entity {uuid:'k'})-[r:RELATES_TO]->() RETURN count(r)").result_set[0][0] == 1

    # the page hides the aliases older merges wrote; the cleanup lists them, and only removes them with apply
    page = client.get("/api/brains/eal/entities/old").json()["entity"]
    assert page["aliases"] == ["Vaultwarden v1.30"]
    assert entity_aliases.clean(GRAPH) == [{"uuid": "old", "name": "Vaultwarden", "removed": 2, "aliases": ["Vaultwarden v1.30"],
                                            "before": ["Vaultwarden", "vaultwarden", "Vaultwarden v1.30"], "dropped": ["Vaultwarden", "vaultwarden"]}]
    assert _aliases(g, "old") == ["Vaultwarden", "vaultwarden", "Vaultwarden v1.30"]
    assert entity_aliases.main(["--brain", "eal", "--apply"]) == 0
    assert _aliases(g, "old") == ["Vaultwarden v1.30"] and entity_aliases.clean(GRAPH) == []
    assert entity_aliases.main(["--brain", "nope"]) == 1

    # undoing the merge brings both duplicates back and takes away only the alias it added
    op = client.get(f"{base}/types").json()["ops"][0]
    assert op["kind"] == "entity.merge" and client.post(f"{base}/ops/{op['id']}/revert").status_code == 200
    assert _aliases(g, "k") == [] and g.query("MATCH (n:Entity) WHERE n.uuid IN ['d1', 'd2'] RETURN count(n)").result_set[0][0] == 2
    assert g.query("MATCH (:Entity {uuid:'d1'})-[r:RELATES_TO]->() RETURN count(r)").result_set[0][0] == 1


@pytest.mark.skipif(not FALKOR, reason="needs a disposable FalkorDB (MIMIRSYNTH_TEST_FALKOR=host)")
def test_cleanup_from_content_quality(client, g):  # noqa: F811
    """#202: preview, apply as a job after a copy of the graph, the change in the history, undo, and the role."""
    from sqlalchemy import select
    from test_control import _as
    from mimirsynth.db import client as fclient
    from mimirsynth.main import app
    from mimirsynth.models import Audit
    from mimirsynth.store import _factory
    g.query("MATCH (n:Entity {uuid:'k'}) SET n.aliases = ['Lyra', 'Lyra VPS', 'lyra vps', 'Lyra VPS']")
    assert client.post("/api/brains", json={"slug": "eal2", "name": "EAL2", "graph_name": GRAPH}).status_code == 201
    base = "/api/brains/eal2/vocab"

    pv = client.get(f"{base}/entity-aliases").json()   # the dry run writes nothing
    assert pv["entities"] == 2 and pv["aliases"] == 5   # 3 on Lyra, 2 on Vaultwarden
    assert {i["uuid"]: (i["aliases"], i["dropped"]) for i in pv["items"]} == {
        "k": (["Lyra VPS"], ["Lyra", "lyra vps", "Lyra VPS"]), "old": (["Vaultwarden v1.30"], ["Vaultwarden", "vaultwarden"])}
    assert _aliases(g, "k") == ["Lyra", "Lyra VPS", "lyra vps", "Lyra VPS"]

    r = client.post(f"{base}/entity-aliases")
    assert r.status_code == 202 and r.json()["job"]
    assert _aliases(g, "k") == ["Lyra VPS"] and _aliases(g, "old") == ["Vaultwarden v1.30"]   # first spelling kept
    assert any(x.startswith(f"_snap_{GRAPH}_") and x.endswith("_alias") for x in fclient().list_graphs())
    op = client.get(f"{base}/types").json()["ops"][0]
    assert op["kind"] == "entity.aliases" and op["summary"] == "Limpiados 5 alias repetidos en 2 entidades"
    with _factory()() as db:
        a = db.scalars(select(Audit).where(Audit.action == "vocab.entity.aliases")).all()[-1]
        assert a.detail["aliases"] == 5 and a.detail["entities"] == 2

    # nothing left: the action says so and writes nothing
    assert client.get(f"{base}/entity-aliases").json() == {"entities": 0, "aliases": 0, "items": []}
    assert client.post(f"{base}/entity-aliases").json() == {"job": None, "entities": 0}

    # an entity changed since the cleanup is left as it is; the other gets its aliases back
    g.query("MATCH (n:Entity {uuid:'old'}) SET n.aliases = ['Vaultwarden v1.30', 'VW']")
    r = client.post(f"{base}/ops/{op['id']}/revert")
    assert r.status_code == 200 and r.json()["restored"] == 1
    assert _aliases(g, "k") == ["Lyra", "Lyra VPS", "lyra vps", "Lyra VPS"] and _aliases(g, "old") == ["Vaultwarden v1.30", "VW"]

    # a curator (or anyone below a brain administrator) cannot preview or run it
    assert client.put("/api/brains/eal2/members", json={"email": "cu@x.com", "role": "curator"}).status_code == 200
    _as("cu@x.com", "Cu")
    assert client.get(f"{base}/entity-aliases").status_code == 403 and client.post(f"{base}/entity-aliases").status_code == 403
    app.dependency_overrides.clear()
