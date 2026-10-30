"""Entity page (#127): facts grouped by relation as an evolution, as_of, functional conflicts, neighbours, episodes and federation."""
import os

import pytest

from test_control import client  # noqa: F401

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
OWN, LENT = "zz-test-entity-own", "zz-test-entity-lent"


@pytest.fixture()
def graphs(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.client.cache_clear()
    c = dbm.client()
    for name in (OWN, LENT):
        if name in c.list_graphs():
            c.select_graph(name).delete()
    g = c.select_graph(OWN)
    g.query("CREATE (:Entity:Host {uuid:'nas', name:'nas01', summary:'NAS of the lab', aliases:['nas-01']}), (:Entity:Place {uuid:'a', name:'Room A'}), "
            "(:Entity:Place {uuid:'b', name:'Room B'}), (:Entity:Place {uuid:'c', name:'Room C'}), (:Entity:Job {uuid:'job', name:'nightly backup'}), "
            "(:Entity {uuid:'ups', name:'UPS'})")
    for u, a, rel, b, valid, inv in [("l1", "nas", "LOCATED_AT", "a", "2026-01-01T00:00:00Z", "2026-06-01T00:00:00Z"),
                                     ("l2", "nas", "LOCATED_AT", "b", "2026-06-01T00:00:00Z", None),
                                     ("l3", "nas", "LocatedAt", "c", "2026-09-01T00:00:00Z", None),       # same relation, another spelling
                                     ("p1", "nas", "POWERED_BY", "ups", "2026-02-01T00:00:00Z", None),
                                     ("j1", "job", "BACKS_UP", "nas", "2026-03-01T00:00:00Z", None),
                                     ("g1", "nas", "RELATES_TO", "b", "2026-04-01T00:00:00Z", None),       # generic: shown apart
                                     ("g2", "nas", "RELATES_TO", "job", "2026-04-02T00:00:00Z", None),
                                     ("g3", "nas", "RelatesTo", "ups", "2026-04-03T00:00:00Z", None)]:
        g.query("MATCH (x:Entity {uuid:$a}), (y:Entity {uuid:$b}) CREATE (x)-[:RELATES_TO {uuid:$u, name:$r, fact:$u + ' fact', valid_at:$v, "
                "created_at:$v, invalid_at:$i, expired_at:$i, episodes:['e1']}]->(y)", {"u": u, "a": a, "b": b, "r": rel, "v": valid, "i": inv})
    g.query("MATCH (n:Entity {uuid:'nas'}) CREATE (:Episodic {uuid:'e1', name:'Lab inventory', valid_at:'2026-01-01T00:00:00Z', source_description:'notes'})-[:MENTIONS]->(n)")
    c.select_graph(LENT).query("CREATE (:Entity:Host {uuid:'lent', name:'lent host'})-[:RELATES_TO {uuid:'g1', name:'RUNS', fact:'lent host runs X', "
                               "created_at:'2026-01-01T00:00:00Z'}]->(:Entity {uuid:'x', name:'X'})")
    yield g
    for name in (OWN, LENT):
        c.select_graph(name).delete()
    dbm.client.cache_clear()


@pytest.mark.skipif(not FALKOR, reason="needs a disposable FalkorDB (MIMIRSYNTH_TEST_FALKOR=host)")
def test_entity_page(client, graphs):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "ep", "name": "EP", "graph_name": OWN}).status_code == 201
    assert client.post("/api/brains", json={"slug": "epl", "name": "EPL", "graph_name": LENT}).status_code == 201
    r = client.get("/api/brains/ep/entities/nas").json()
    assert r["entity"]["name"] == "nas01" and r["entity"]["labels"] == ["Host"] and r["entity"]["aliases"] == ["nas-01"] and not r["read_only"]
    assert r["facts"] == {"total": 8, "shown": 8, "not_yet": 0, "truncated": False}
    assert r["groups"][-1]["relation"] == "RELATES_TO" and r["groups"][-1]["generic"] and len(r["groups"][-1]["current"]) == 3   # last, even with most facts
    assert not any(g["generic"] for g in r["groups"][:-1])
    groups = {(g["direction"], g["relation"]): g for g in r["groups"]}
    loc = groups[("out", "LOCATED_AT")]                                                     # both spellings, one group
    assert [f["uuid"] for f in loc["current"]] == ["l2", "l3"] and [f["uuid"] for f in loc["previous"]] == ["l1"]
    assert loc["previous"][0]["invalid_at"] == "2026-06-01T00:00:00Z" and loc["current"][0]["other"] == {"uuid": "b", "name": "Room B", "labels": ["Place"]}
    assert not loc["functional"] and not loc["conflict"]
    assert groups[("in", "BACKS_UP")]["current"][0]["other"]["name"] == "nightly backup"
    assert r["episodes"]["total"] == 1 and r["episodes"]["items"][0]["name"] == "Lab inventory"
    assert {n["name"] for n in r["neighbors"]} == {"Room A", "Room B", "Room C", "UPS", "nightly backup"} and r["neighbors"][-1]["name"] == "Room A"
    assert next(n for n in r["neighbors"] if n["uuid"] == "a")["current"] == 0

    # a single-valued relation with two current values is flagged, and shown first
    client.post("/api/brains/ep/vocab/relations", json={"name": "LocatedAt", "description": "Is in a place", "functional": True})
    r = client.get("/api/brains/ep/entities/nas").json()
    assert r["groups"][0]["relation"] == "LOCATED_AT" and r["groups"][0]["functional"] and r["groups"][0]["conflict"]

    # as_of: what was current on a given day (validity time); what was not yet true is left out
    r = client.get("/api/brains/ep/entities/nas", params={"as_of": "2026-03-15"}).json()
    loc = next(g for g in r["groups"] if g["relation"] == "LOCATED_AT")
    assert [f["uuid"] for f in loc["current"]] == ["l1"] and loc["previous"] == [] and not loc["conflict"]
    assert r["facts"]["not_yet"] == 5 and r["facts"]["shown"] == 3   # 2 locations and the 3 generic facts came later and r["as_of"].startswith("2026-03-15")
    assert client.get("/api/brains/ep/entities/nas", params={"as_of": "yesterday"}).status_code == 400

    # federation: a lent entity is read with origin, read-only; without the grant, 404
    assert client.get("/api/brains/ep/entities/lent", params={"origin": "epl"}).status_code == 404
    assert client.post("/api/brains/epl/grants", json={"target": "ep", "scope": "graph"}).status_code == 201
    r = client.get("/api/brains/ep/entities/lent", params={"origin": "epl"}).json()
    assert r["read_only"] and r["entity"]["origin"] == "epl" and r["groups"][0]["current"][0]["uuid"] == "g1"
    assert client.get("/api/brains/ep/entities/lent").status_code == 404                  # not in this brain's own graph
    assert client.get("/api/brains/ep/entities/nope").status_code == 404

    # find by name or merged name, exact match first
    assert [e["uuid"] for e in client.get("/api/brains/ep/entities", params={"q": "nas-01"}).json()] == ["nas"]
    assert client.get("/api/brains/ep/entities", params={"q": "room"}).json()[0]["name"].startswith("Room")
