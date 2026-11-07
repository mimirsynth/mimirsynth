"""Scheduled curator (#300, first part): off by default, the contradiction pass turns clear groups into proposals in quarantine with
their evidence, a pass that would change more than its batch waits for a person to confirm a sample, one run per brain and day, the
precision of a pass comes from the curators' decisions, and approving a curator's proposal invalidates the old fact without an LLM."""
import os

import pytest

from test_control import client  # noqa: F401

from mimirsynth import curator as K

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-curator"
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


@pytest.fixture()
def graph(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.client.cache_clear()
    c = dbm.client()
    if GRAPH in c.list_graphs():
        c.select_graph(GRAPH).delete()
    g = c.select_graph(GRAPH)
    for n in range(7):   # seven services, each «located at» two hosts: the newest one is clearly the current one
        g.query("CREATE (:Entity {uuid:$s, name:$sn}), (:Entity:Host {uuid:$a, name:$an}), (:Entity:Host {uuid:$b, name:$bn})",
                {"s": f"s{n}", "sn": f"svc{n}", "a": f"a{n}", "an": f"old{n}", "b": f"b{n}", "bn": f"new{n}"})
        for u, t, when in ((f"o{n}", f"a{n}", "2024-01-01T00:00:00Z"), (f"n{n}", f"b{n}", "2026-01-01T00:00:00Z")):
            g.query("MATCH (a:Entity {uuid:$s}), (b:Entity {uuid:$t}) CREATE (a)-[:RELATES_TO {uuid:$u, name:'LOCATED_AT', fact:$f, valid_at:$w, "
                    "created_at:$w}]->(b)", {"s": f"s{n}", "t": t, "u": u, "f": f"svc{n} at {t}", "w": when})
    for n in range(30):  # and thirty with a single host: the relation does not look multi-valued
        g.query("CREATE (a:Entity {uuid:$s, name:$sn})-[:RELATES_TO {uuid:$u, name:'LOCATED_AT', fact:'one host', valid_at:'2025-01-01T00:00:00Z', "
                "created_at:'2025-01-01T00:00:00Z'}]->(:Entity:Host {uuid:$h, name:$hn})", {"s": f"x{n}", "sn": f"single{n}", "u": f"x{n}f", "h": f"h{n}", "hn": f"host{n}"})
    yield g
    g.delete()
    dbm.client.cache_clear()


def _setup(client, slug):  # noqa: F811
    assert client.post("/api/brains", json={"slug": slug, "name": slug.upper(), "graph_name": GRAPH}).status_code == 201
    assert client.post(f"/api/brains/{slug}/vocab/relations", json={"name": "LocatedAt", "description": "Está en un sitio", "functional": True}).status_code == 201


@needs_falkor
def test_off_by_default_preview_and_the_sample_gate(client, graph):  # noqa: F811
    from mimirsynth.models import CuratorRun, Proposal
    from mimirsynth.store import _factory
    _setup(client, "cu1")
    s = client.get("/api/brains/cu1/curator/settings").json()
    assert s["enabled"] is False and s["precision"]["contradictions"]["precision"] is None
    pv = client.post("/api/brains/cu1/curator/preview").json()
    assert pv["count"] == 7 and pv["findings"][0]["keep"]["uuid"].startswith("n") and pv["findings"][0]["replace"][0]["uuid"].startswith("o")
    client.put("/api/brains/cu1/curator/settings", json={"enabled": True, "batch": 5})
    assert client.post("/api/brains/cu1/curator/run").status_code == 202
    run = client.get("/api/brains/cu1/curator/runs").json()["items"][0]
    assert run["status"] == "waiting" and run["findings"] == {"contradictions": 7} and len(run["sample"]["contradictions"]) == 7
    with _factory()() as db:
        from mimirsynth.models import Brain
        bid = db.query(Brain).filter(Brain.slug == "cu1").one().id
        assert db.query(Proposal).filter(Proposal.brain_id == bid, Proposal.category == "curator.contradictions").count() == 0   # nothing proposed yet
    assert client.post("/api/brains/cu1/curator/run").status_code == 409                    # it waits: not run again
    done = client.post(f"/api/brains/cu1/curator/runs/{run['id']}/confirm").json()
    assert done["status"] == "done" and len(done["proposals"]) == 7
    with _factory()() as db:
        p = db.get(Proposal, done["proposals"][0])
        assert p.status == "pending" and p.body == "" and p.claims[0]["verdict"] == "replaces" and p.decision["curator"]["pass"] == "contradictions"
        assert db.query(CuratorRun).filter(CuratorRun.id == run["id"]).one().status == "done"
    assert client.post("/api/brains/cu1/curator/preview").json()["count"] == 0              # already proposed: not twice


@needs_falkor
def test_a_small_batch_is_proposed_and_approving_applies_it(client, graph, monkeypatch):  # noqa: F811
    from mimirsynth import ingest
    from mimirsynth.models import Proposal
    from mimirsynth.store import _factory
    monkeypatch.setattr(ingest, "enabled", lambda: False)                                   # no LLM: the curator's proposals still apply
    _setup(client, "cu2")
    client.put("/api/brains/cu2/curator/settings", json={"enabled": True, "batch": 10})
    assert len(K.due()) >= 1 and K.due() == []                                               # once a day
    run = client.get("/api/brains/cu2/curator/runs").json()["items"][0]
    assert run["status"] == "done" and len(run["proposals"]) == 7
    pid, other = run["proposals"][:2]
    r = client.post(f"/api/brains/cu2/proposals/{pid}/approve", json={})
    assert r.status_code == 200 and r.json().get("undo_seconds")
    ingest.ingest_proposal(pid)
    with _factory()() as db:
        p = db.get(Proposal, pid)
        old = p.claims[0]["supersedes"]
        assert p.status == "ingested" and p.ingest_report["claims"]["superseded"] == [old]
    assert graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() RETURN r.invalid_at", {"u": old}).result_set[0][0] == "2026-01-01T00:00:00Z"
    client.post(f"/api/brains/cu2/proposals/{other}/reject", json={"note": "the old host is still in use"})
    prec = client.get("/api/brains/cu2/curator/settings").json()["precision"]["contradictions"]
    assert prec == {"approved": 1, "rejected": 1, "pending": 5, "precision": 0.5}


def test_settings_are_for_administrators_and_known_passes(client):  # noqa: F811
    client.post("/api/brains", json={"slug": "cu3", "name": "CU3"})
    assert client.put("/api/brains/cu3/curator/settings", json={"enabled": True, "passes": {"noise": True}}).status_code == 422
    tok = client.post("/api/brains/cu3/tokens", json={"name": "c", "role": "curator"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/brains/cu3/curator/settings", headers=h).status_code == 200
    assert client.put("/api/brains/cu3/curator/settings", headers=h, json={"enabled": True}).status_code == 403
