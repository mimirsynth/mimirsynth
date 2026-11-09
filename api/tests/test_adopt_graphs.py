"""Adopting the graphs already in a database (#359): the inventory says what each one is, a Graphiti graph written outside MimirSynth
becomes a brain whose recall, facts and timeline work, a full brain needs its vectors to match the embedding engine, a read-only one is
never written (not even by a path that forgets to check), a new brain never lands on a graph that is nobody's, and a graph that is not
adopted stays byte for byte as it was."""
import json
import os
from datetime import datetime, timezone

import pytest

from test_control import client  # noqa: F401  (fixture with the app and the test database)

from mimirsynth import graphconn as G
from mimirsynth.config import settings
from mimirsynth.db import vector as gvec
from mimirsynth.graphdb import ReadOnlyError, backend

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
needs_graph = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host) o un Neo4j")
OUTSIDE, IGNORED, LOOKONLY = "zz_outside", "zz_ignored", "zz_lookonly"
V = [0.6, 0.8, 0.0]  # every vector the same: the query finds the fact with similarity 1


def _seed(name: str, dim: int = 3) -> None:
    """A small graph as Graphiti writes it: two entities, a fact between them and the episode that mentions both."""
    t = datetime(2026, 3, 1, tzinfo=timezone.utc).isoformat()
    v = (V + [0.0] * dim)[:dim]
    backend().graph(name).query(
        f"CREATE (a:Entity {{uuid: $p + '-a', name: 'Vaultwarden', group_id: $g, summary: '', created_at: $t, name_embedding: {gvec('$v')}}}) "
        f"CREATE (b:Entity {{uuid: $p + '-b', name: 'altair', group_id: $g, summary: '', created_at: $t, name_embedding: {gvec('$v')}}}) "
        "CREATE (a)-[:RELATES_TO {uuid: $p + '-f', name: 'RUNS_ON', fact: 'Vaultwarden runs on altair', group_id: $g, created_at: $t, "
        f"valid_at: $t, episodes: [$p + '-e'], fact_embedding: {gvec('$v')}}}]->(b) "
        "CREATE (e:Episodic {uuid: $p + '-e', name: 'note', content: 'Vaultwarden runs on altair', source: 'text', "
        "source_description: 'outside', group_id: $g, created_at: $t, valid_at: $t, entity_edges: [$p + '-f']}) "
        "CREATE (e)-[:MENTIONS {uuid: $p + '-m1', group_id: $g, created_at: $t}]->(a) "
        "CREATE (e)-[:MENTIONS {uuid: $p + '-m2', group_id: $g, created_at: $t}]->(b)",
        {"p": name, "g": name, "t": t, "v": v})


def _snapshot(name: str):
    """The graph as it is: FalkorDB's binary dump or, on Neo4j, every node and relationship with its labels and properties."""
    b = backend()
    if b.can_dump():
        return b.dump(name)
    g = b.graph(name)
    nodes = sorted(json.dumps([sorted(r[0]), r[1]], sort_keys=True, default=str)
                   for r in g.ro_query("MATCH (n) RETURN labels(n), properties(n)").result_set)
    rels = sorted(json.dumps([r[0], r[1]], sort_keys=True, default=str)
                  for r in g.ro_query("MATCH ()-[r]->() RETURN type(r), properties(r)").result_set)
    return nodes, rels


@pytest.fixture()
def graphs(monkeypatch):
    from mimirsynth import db as dbm
    if not os.environ.get("MIMIRSYNTH_TEST_NEO4J"):
        monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.backend.cache_clear()
    b = dbm.backend()
    for n in (OUTSIDE, IGNORED, LOOKONLY):
        if b.exists(n):
            b.delete_graph(n)
    _seed(OUTSIDE)
    _seed(IGNORED)
    _seed(LOOKONLY, dim=4)
    yield b
    for n in (OUTSIDE, IGNORED, LOOKONLY):
        if b.exists(n):
            b.delete_graph(n)
    dbm.backend.cache_clear()


def _drop(client, slug):  # noqa: F811
    client.post(f"/api/brains/{slug}/delete", json={"confirm": slug, "delete_graph": False})


@needs_graph
def test_an_outside_graphiti_graph_becomes_a_brain_whose_recall_facts_and_timeline_work(client, graphs, monkeypatch):  # noqa: F811
    from mimirsynth import recall
    before = _snapshot(IGNORED)
    inv = {g["name"]: g for g in client.get("/api/admin/graph/inventory").json()["graphs"]}
    o = inv[OUTSIDE]
    assert (o["nodes"], o["edges"], o["entities"], o["episodes"], o["dim"], o["graphiti"]) == (3, 3, 2, 1, 3, True)
    assert o["brain"] is None and o["valid_name"] and o["group_ids"] == [OUTSIDE] and inv[LOOKONLY]["dim"] == 4
    assert o["dim_ok"] is (client.get("/api/admin/graph/inventory").json()["engine_dim"] == 3)

    monkeypatch.setattr(G, "_engine_dim", lambda: 768)                                 # the engine's dimension is not the graph's
    r = client.post("/api/admin/graph/adopt", json={"graph": OUTSIDE, "slug": "zz-outside", "name": "Outside"})
    assert r.status_code == 409 and "768" in r.json()["detail"] and "solo lectura" in r.json()["detail"]
    monkeypatch.setattr(G, "_engine_dim", lambda: 3)
    r = client.post("/api/admin/graph/adopt", json={"graph": OUTSIDE, "slug": "zz-outside", "name": "Outside"})
    assert r.status_code == 201, r.text
    assert r.json()["graph_name"] == OUTSIDE and r.json()["read_only"] is False
    try:
        assert client.post("/api/admin/graph/adopt", json={"graph": OUTSIDE, "slug": "zz-other", "name": "x"}).status_code == 409
        assert client.post("/api/admin/graph/adopt", json={"graph": "_snap_x", "slug": "zz-snap", "name": "x"}).status_code == 404

        monkeypatch.setattr(recall, "get_embedder", lambda: type("E", (), {"embed": lambda self, t: [list(V) for _ in t]})())
        out = client.post("/api/brains/zz-outside/recall", json={"query": "where does vaultwarden run?"}).json()
        assert "Vaultwarden runs on altair" in [f["fact"] for f in out["facts"]]
        facts = client.get("/api/brains/zz-outside/facts").json()
        assert [f["fact"] for f in facts["items"]] == ["Vaultwarden runs on altair"]
        events = client.get("/api/brains/zz-outside/timeline").json()
        assert any(e["fact"] == "Vaultwarden runs on altair" for e in events)

        r = client.post("/api/brains", json={"slug": "zz-ignored", "name": "x"})
        assert r.status_code == 201   # its own graph «zz-ignored», next to the existing «zz_ignored» that nobody adopted
        _drop(client, "zz-ignored")
        assert _snapshot(IGNORED) == before                                              # never adopted: untouched, byte for byte
    finally:
        _drop(client, "zz-outside")


@needs_graph
def test_a_new_brain_never_lands_on_a_graph_that_is_nobodys(client, graphs):  # noqa: F811
    backend().graph("zz-nobody").query("CREATE (:Entity {name: 'x', group_id: 'zz-nobody'})")
    try:
        r = client.post("/api/brains", json={"slug": "zz-nobody", "name": "Nobody"})
        assert r.status_code == 409 and "adóptalo" in r.json()["detail"]
        r = client.post("/api/brains", json={"slug": "zz-nobody2", "name": "Explicit", "graph_name": "zz-nobody"})   # asked by name: allowed
        assert r.status_code == 201
        _drop(client, "zz-nobody2")
    finally:
        backend().delete_graph("zz-nobody")


@needs_graph
def test_a_read_only_brain_is_read_and_never_written(client, graphs, monkeypatch):  # noqa: F811
    from mimirsynth import db as dbm
    from mimirsynth import recall
    monkeypatch.setattr(G, "_engine_dim", lambda: 3)                                   # its vectors (4) do not match: read-only only
    assert client.post("/api/admin/graph/adopt", json={"graph": LOOKONLY, "slug": "zz-look", "name": "Look"}).status_code == 409
    r = client.post("/api/admin/graph/adopt", json={"graph": LOOKONLY, "slug": "zz-look", "name": "Look", "read_only": True})
    assert r.status_code == 201 and r.json()["read_only"] is True
    before = _snapshot(LOOKONLY)
    try:
        facts = client.get("/api/brains/zz-look/facts").json()
        assert [f["fact"] for f in facts["items"]] == ["Vaultwarden runs on altair"]           # read: yes
        r = client.post("/api/brains/zz-look/proposals", json={"name": "n", "body": "Vaultwarden moved to nas01"})
        assert r.status_code == 409 and "solo lectura" in r.json()["detail"]                   # written: no
        with pytest.raises(ReadOnlyError):                                                     # nor by a path that does not check
            dbm.graph(LOOKONLY).query("MATCH (n:Entity) SET n.name = 'changed'")
        assert dbm.graph(LOOKONLY).query("MATCH (n:Entity) RETURN count(n)").result_set[0][0] == 2   # reading through it still works
        monkeypatch.setattr(recall, "get_embedder", lambda: type("E", (), {"embed": lambda self, t: [[0.6, 0.8, 0.0, 0.0] for _ in t]})())
        assert client.post("/api/brains/zz-look/recall", json={"query": "vaultwarden"}).status_code == 200
        r = client.patch("/api/admin/graph/brains/zz-look", json={"read_only": False})
        assert r.status_code == 409                                                            # full needs matching vectors
        assert _snapshot(LOOKONLY) == before
        monkeypatch.setattr(G, "_engine_dim", lambda: 4)
        r = client.patch("/api/admin/graph/brains/zz-look", json={"read_only": False})
        assert r.status_code == 200 and r.json()["read_only"] is False
        assert dbm.graph(LOOKONLY).query("MATCH (n:Entity {name: 'altair'}) SET n.summary = 'a host' RETURN count(n)").result_set[0][0] == 1
    finally:
        _drop(client, "zz-look")


def test_a_read_only_brain_waits_to_be_ingested(client, monkeypatch):  # noqa: F811
    """An approved proposal of a brain made read-only after it was approved is not ingested: it waits, with the reason."""
    from mimirsynth import ingest
    from mimirsynth.deps import READ_ONLY
    from mimirsynth.models import Brain, Proposal, User
    from mimirsynth.store import _factory
    with _factory()() as db:
        u = db.query(User).first() or User(email="ro@example.com", name="ro")
        b = Brain(slug="zz-ro-ingest", name="RO", graph_name="zz_ro_ingest", read_only=True)
        db.add_all([u, b])
        db.commit()
        p = Proposal(brain_id=b.id, author_id=u.id, name="n", body="x", source="text", status="approved")
        db.add(p)
        db.commit()
        pid, bid = p.id, b.id
    try:
        assert ingest.ingest_proposal(pid) == ""
        with _factory()() as db:
            p = db.get(Proposal, pid)
            assert p.status == "approved" and p.ingest_error == READ_ONLY
    finally:
        with _factory()() as db:
            db.query(Proposal).filter(Proposal.id == pid).delete()
            db.query(Brain).filter(Brain.id == bid).delete()
            db.commit()
