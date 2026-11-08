"""Distilling repeated episodes (issue 297): the curator groups episodes that repeat the same lesson about one entity, the brain's LLM
writes one note, a person approves it one at a time, and once it is ingested the originals it covers (and a curator left ticked) are
deleted without touching the facts other episodes support."""
import json
import os

import pytest

from test_control import client  # noqa: F401

from mimirsynth import distil as D

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-distil"
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


def test_groups_need_every_pair_close_and_the_minimum_size():
    items = [{"uuid": u} for u in "abcde"]
    vec = {"a": [1, 0, 0], "b": [0.99, 0.1, 0], "c": [0.98, 0.15, 0], "d": [0, 1, 0], "e": [0.6, 0.8, 0]}
    found = D.groups(items, vec, 0.95, 3)
    assert [[m["uuid"] for m in g] for g, _ in found] == [["a", "b", "c"]] and found[0][1] >= 0.95
    assert D.groups(items, vec, 0.95, 4) == []                                              # three alike are not four
    assert D.groups(items, {"a": [1, 0], "b": [1, 0]}, 0.9, 3) == []                        # episodes without vectors do not count


def test_a_fact_is_covered_by_the_same_pair_and_relation_or_a_close_text():
    note = [{"s": "vw", "t": "alt", "name": "RUNS_ON", "e": [1, 0]}]
    assert D.covered({"s": "alt", "t": "vw", "name": "RunsOn", "e": None}, note)               # either direction, the canonical relation
    assert D.covered({"s": "vw", "t": "alt", "name": "HOSTED_BY", "e": [0.95, 0.05]}, note)   # another relation, the same text
    assert not D.covered({"s": "vw", "t": "s3", "name": "RUNS_ON", "e": [1, 0]}, note)        # other entities
    assert not D.covered({"s": "vw", "t": "alt", "name": "RUNS_ON", "invalid_at": "2026-01-01"}, note)   # history the note does not keep


@pytest.fixture()
def graph(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.backend.cache_clear()
    c = dbm.backend()
    if GRAPH in c.list_graphs():
        c.delete_graph(GRAPH)
    g = c.graph(GRAPH)
    g.query("CREATE (:Entity {uuid:'vw', name:'Vaultwarden'}), (:Entity {uuid:'alt', name:'altair'}), (:Entity {uuid:'s3', name:'s3-backups'}), "
            "(:Entity {uuid:'lonely', name:'only-in-e1'})")
    for n, when in ((1, "2026-01-01"), (2, "2026-02-01"), (3, "2026-03-01"), (4, "2026-04-01")):
        g.query("MATCH (v:Entity {uuid:'vw'}) CREATE (e:Episodic {uuid:$u, name:$n, content:$c, valid_at:$w})-[:MENTIONS]->(v)",
                {"u": f"e{n}", "n": f"lesson {n}", "c": f"Vaultwarden runs on altair (note {n})", "w": f"{when}T00:00:00Z"})
    g.query("MATCH (e:Episodic {uuid:'e1'}), (n:Entity {uuid:'lonely'}) CREATE (e)-[:MENTIONS]->(n)")
    for u, s, t, name, fact, eps in (("f1", "vw", "alt", "RUNS_ON", "Vaultwarden runs on altair", ["e1"]),
                                     ("f2", "vw", "alt", "RUNS_ON", "Vaultwarden is hosted on altair", ["e1", "e2"]),
                                     ("f3", "vw", "s3", "BACKS_UP_TO", "Vaultwarden backs up to s3-backups nightly", ["e3"]),
                                     ("f4", "lonely", "alt", "RELATES_TO", "only-in-e1 is near altair", ["e1"])):
        g.query("MATCH (a:Entity {uuid:$s}), (b:Entity {uuid:$t}) CREATE (a)-[:RELATES_TO {uuid:$u, name:$n, fact:$f, episodes:$e, "
                "created_at:'2026-01-01T00:00:00Z'}]->(b)", {"s": s, "t": t, "u": u, "n": name, "f": fact, "e": eps})
    yield g
    c.delete_graph(GRAPH)
    dbm.backend.cache_clear()


@needs_falkor
def test_distil_proposes_a_note_and_deletes_only_the_covered_ticked_originals(client, graph, monkeypatch):  # noqa: F811
    from mimirsynth.models import CuratorRun, Proposal
    from mimirsynth.store import _factory
    near = {"e1": [1, 0, 0], "e2": [0.99, 0.05, 0], "e3": [0.98, 0.1, 0], "e4": [0, 1, 0]}
    monkeypatch.setattr(D, "_vectors", lambda bid, uuids: {u: near[u] for u in uuids if u in near})
    monkeypatch.setattr(D, "_engine", lambda: {"base_url": "http://llm", "model": "m"})
    asked = []
    monkeypatch.setattr(D, "_ask", lambda eng, msgs: asked.append(msgs) or json.dumps(
        {"title": "Vaultwarden en altair", "note": "2026-03-01: Vaultwarden runs on altair and backs up nightly."}))
    assert client.post("/api/brains", json={"slug": "di1", "name": "DI1", "graph_name": GRAPH}).status_code == 201

    pv = client.post("/api/brains/di1/curator/preview?pass=distil").json()
    assert pv["count"] == 1 and [e["uuid"] for e in pv["findings"][0]["episodes"]] == ["e1", "e2", "e3"] and not asked   # read-only, no LLM
    client.put("/api/brains/di1/curator/settings", json={"enabled": True, "passes": {"contradictions": False, "distil": True}})
    assert client.get("/api/brains/di1/curator/settings").json()["distil_calls"] == 5
    client.post("/api/brains/di1/curator/run")
    run = client.get("/api/brains/di1/curator/runs").json()["items"][0]
    assert run["findings"] == {"distil": 1} and len(run["proposals"]) == 1 and len(asked) == 1
    pid = run["proposals"][0]
    with _factory()() as db:
        p = db.get(Proposal, pid)
        assert p.category == "curator.distil" and p.status == "pending" and "backs up nightly" in p.body and p.name.startswith("Curador: destila")
        assert p.reference_time.year == 2026 and p.reference_time.month == 3 and p.decision["curator"]["delete"] == ["e1", "e2", "e3"]

    # never approved without a person reading it, one at a time
    assert client.put("/api/brains/di1/review/categories/curator.distil/auto", json={"enabled": True}).status_code == 409
    bulk = client.post("/api/brains/di1/proposals/bulk", json={"verb": "approve", "ids": [pid]}).json()
    assert bulk["skipped"] == [{"id": pid, "reason": "distil"}]
    assert client.put(f"/api/brains/di1/curator/distil/{pid}", json={"delete": ["zz"]}).status_code == 422
    assert client.put(f"/api/brains/di1/curator/distil/{pid}", json={"delete": ["e1", "e3"]}).json() == {"delete": ["e1", "e3"]}

    # the note is ingested (the extraction is stood in for: it needs an LLM): one fact between the same entities as e1's own ones
    from mimirsynth import ingest

    async def fake_episode(graph_name, *a, **k):
        graph.query("MATCH (v:Entity {uuid:'vw'}), (a:Entity {uuid:'alt'}) CREATE (:Episodic {uuid:'note', name:'note', content:'n'})-[:MENTIONS]->(v), "
                    "(v)-[:RELATES_TO {uuid:'fn', name:'RUNS_ON', fact:'Vaultwarden runs on altair', episodes:['note']}]->(a)")
        graph.query("MATCH (n:Entity {uuid:'lonely'}), (a:Entity {uuid:'alt'}) "
                    "CREATE (n)-[:RELATES_TO {uuid:'fn2', name:'RELATES_TO', fact:'x', episodes:['note']}]->(a)")   # covers f4 as well
        return "note"
    monkeypatch.setattr(ingest, "add_episode", fake_episode)
    with _factory()() as db:
        db.get(Proposal, pid).status = "approved"
        db.commit()
    assert ingest.ingest_proposal(pid) == ""
    with _factory()() as db:
        p = db.get(Proposal, pid)
        assert p.status == "ingested" and p.episode_uuid == "note"
        out = p.ingest_report["distil"]
    assert [d["uuid"] for d in out["deleted"]] == ["e1"]
    kept = {k["uuid"]: k for k in out["kept"]}
    assert kept["e2"]["why"] == "unticked" and kept["e3"]["why"] == "says_more" and kept["e3"]["facts"] == ["Vaultwarden backs up to s3-backups nightly"]
    left = lambda q: graph.query(q).result_set  # noqa: E731
    assert left("MATCH (e:Episodic {uuid:'e1'}) RETURN e") == []
    assert left("MATCH ()-[r:RELATES_TO {uuid:'f1'}]->() RETURN r") == []                           # only e1 said it
    assert left("MATCH ()-[r:RELATES_TO {uuid:'f2'}]->() RETURN r.episodes")[0][0] == ["e2"]        # shared: only the reference goes
    assert left("MATCH (:Episodic {uuid:'e3'}) RETURN 1") and left("MATCH ()-[r {uuid:'f3'}]->() RETURN 1")
    assert left("MATCH (n:Entity {uuid:'lonely'}) RETURN n")                                          # still linked by the note
    with _factory()() as db:
        assert db.query(CuratorRun).count() >= 1
