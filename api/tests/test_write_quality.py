"""Quality at write time (#458): the facts an ingestion just created that repeat each other, or a current fact, word for word become
one; those with a placeholder or the memory itself at one end are dropped; nothing that was already in the brain is deleted; the
ingest report says what and why; and a failure here never fails the ingestion."""
import os

import pytest

from test_control import client  # noqa: F401

from mimirsynth import write_quality as W

EP = "ep-new"
FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-write-quality"
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


def fact(uuid, text, su="vw", tu="al", source="Vaultwarden", target="altair", episodes=(EP,), invalid_at=None):
    return {"uuid": uuid, "fact": text, "su": su, "tu": tu, "source": source, "target": target, "episodes": list(episodes),
            "invalid_at": invalid_at, "expired_at": None}


def test_repeats_of_one_episode_become_one():
    found = [fact("e1", "Vaultwarden runs on altair"), fact("e2", "vaultwarden  runs on Altair."),
             fact("e3", "Vaultwarden runs on altair", su="al", tu="vw", source="altair", target="Vaultwarden"),   # same pair, other way
             fact("e4", "Vaultwarden runs on altair", tu="nas", target="nas01"),                                  # another pair: stays
             fact("e5", "Vaultwarden runs on altair v2")]                                                         # another text: stays
    out = W.decide(found, EP, [])
    assert out["gone"] == ["e2", "e3"] and out["link"] == [] and out["dropped"] == []
    assert out["collapsed"] == [{"fact": "vaultwarden  runs on Altair.", "kept": "e1", "why": W.SAME_EPISODE},
                                {"fact": "Vaultwarden runs on altair", "kept": "e1", "why": W.SAME_EPISODE}]


def test_a_repeat_of_a_current_fact_is_linked_to_it_and_a_near_one_is_not():
    found = [fact("e1", "Vaultwarden runs on altair"), fact("e2", "Vaultwarden runs on altair"), fact("e3", "Vaultwarden is backed up nightly")]
    current = [{"uuid": "x1", "fact": "Vaultwarden runs on altair.", "su": "al", "tu": "vw"},
               {"uuid": "x2", "fact": "Vaultwarden is backed up every night", "su": "vw", "tu": "al"}]   # near, not the same: a curator's call
    out = W.decide(found, EP, current)
    assert out["gone"] == ["e2", "e1"] and out["link"] == ["x1"]
    assert [(c["fact"], c["kept"], c["why"]) for c in out["collapsed"]] == [("Vaultwarden runs on altair", "x1", W.SAME_EPISODE),
                                                                          ("Vaultwarden runs on altair", "x1", W.SAME_CURRENT)]


def test_an_invalidated_new_fact_is_never_linked_to_a_current_one():
    out = W.decide([fact("e1", "Vaultwarden runs on altair", invalid_at="2026-01-01")], EP,
                   [{"uuid": "x1", "fact": "Vaultwarden runs on altair", "su": "vw", "tu": "al"}])
    assert out["gone"] == [] and out["link"] == []


def test_trivial_new_facts_are_dropped_and_what_was_already_there_is_never_touched():
    found = [fact("e1", "It runs on altair", su="it", source="it"),
             fact("e2", "The graph stores Vaultwarden", tu="g", target="the graph"),
             fact("e3", "It was here before", su="it", source="it", episodes=("old", EP)),        # already in the brain: stays
             fact("e4", "It runs on altair", su="it", source="it", episodes=("old",)),            # idem
             fact("e5", "Vaultwarden is self-hosted")]                                            # generic-looking: a curator's call
    out = W.decide(found, EP, [{"uuid": "e4", "fact": "It runs on altair", "su": "it", "tu": "al"}])
    assert out["gone"] == ["e1", "e2"] and out["collapsed"] == [] and out["link"] == []
    assert [(d["fact"], d["rule"]) for d in out["dropped"]] == [("It runs on altair", "placeholder"), ("The graph stores Vaultwarden", "meta")]
    assert all(d["why"] for d in out["dropped"])


def test_a_trivial_fact_that_replaced_another_stays_for_a_person():
    found = [fact("e1", "It runs on altair", su="it", source="it"),
             fact("x1", "Vaultwarden runs on vega", tu="al", episodes=("old",), invalid_at="2026-11-01")]   # invalidated by this episode
    assert W.decide(found, EP, [])["gone"] == []


class _Graph:
    def __init__(self, found, current):
        self.found, self.current, self.writes = found, current, []

    def query(self, q, p=None):
        if q == W._FOUND:
            data = [f for f in self.found if f["uuid"] in p["u"]]
        elif q == W._CURRENT:
            data = self.current
        else:
            self.writes.append((q, p))
            data = []
        keys = list(data[0]) if data else ["uuid"]
        return type("R", (), {"header": keys, "result_set": [[d[k] for k in keys] for d in data]})()


def test_apply_deletes_links_and_reports(monkeypatch):
    g = _Graph([fact("e1", "Vaultwarden runs on altair"), fact("e2", "Vaultwarden runs on altair"),
                fact("e3", "It runs on altair", su="it", source="it"), fact("e4", "Vaultwarden uses PostgreSQL", tu="pg", target="PostgreSQL")],
               [{"uuid": "x1", "fact": "Vaultwarden uses PostgreSQL", "su": "vw", "tu": "pg"}])
    monkeypatch.setattr(W, "graph", lambda name: g)
    rep = {"edges": 4, "_edges": [("e1", "RUNS_ON"), ("e2", "RUNS_ON"), ("e3", "RUNS_ON"), ("e4", "USES")]}
    W.apply(type("B", (), {"graph_name": "g"})(), rep, EP)
    assert rep["_edges"] == [("e1", "RUNS_ON")] and rep["edges"] == 1
    assert [c["kept"] for c in rep["collapsed"]] == ["e1", "x1"] and [d["rule"] for d in rep["dropped"]] == ["placeholder"]
    delete, link, episode = g.writes
    assert "DELETE r" in delete[0] and "size(r.episodes) = 1" in delete[0] and delete[1] == {"u": ["e2", "e3", "e4"], "e": EP}
    assert link[1] == {"u": "x1", "e": EP} and episode[1] == {"e": EP, "g": ["e2", "e3", "e4"], "l": ["x1"]}


def test_apply_with_nothing_to_do_writes_nothing(monkeypatch):
    g = _Graph([fact("e1", "Vaultwarden runs on altair")], [])
    monkeypatch.setattr(W, "graph", lambda name: g)
    rep = {"edges": 1, "_edges": [("e1", "RUNS_ON")]}
    W.apply(type("B", (), {"graph_name": "g"})(), rep, EP)
    assert g.writes == [] and rep == {"edges": 1, "_edges": [("e1", "RUNS_ON")]}


def test_a_failure_here_never_fails_the_ingestion(client, monkeypatch):  # noqa: F811
    from mimirsynth import ingest, vocab_apply
    from mimirsynth.models import Proposal
    from mimirsynth.store import _factory
    monkeypatch.setattr(ingest, "enabled", lambda: True)

    async def fake(graph, name, body, source, desc, ref, ontology=None, report=None):
        report.update({"entities": 2, "edges": 1, "_edges": [("e1", "RUNS_ON")], "_nodes": []})
        return "ep-1"
    monkeypatch.setattr(ingest, "add_episode", fake)

    def broken(name):
        raise RuntimeError("graph down")
    monkeypatch.setattr(W, "graph", broken)
    monkeypatch.setattr(vocab_apply, "graph", broken)
    client.post("/api/brains", json={"slug": "wq", "name": "WQ"})
    pid = client.post("/api/brains/wq/proposals", json={"name": "VW", "body": "Vaultwarden runs on altair."}).json()["id"]
    ingest.ingest_proposal(pid)
    with _factory()() as db:
        p = db.get(Proposal, pid)
        assert p.status == "ingested" and p.episode_uuid == "ep-1" and p.ingest_report["quality_error"] is True


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
    g.query("CREATE (vw:Entity {uuid:'vw', name:'Vaultwarden'}), (al:Entity {uuid:'al', name:'altair'}), (it:Entity {uuid:'it', name:'it'}), "
            "(pg:Entity {uuid:'pg', name:'PostgreSQL'}), (:Episodic {uuid:'ep-new', entity_edges:['e1', 'e2', 'e3', 'e4', 'x2']}), "
            "(vw)-[:RELATES_TO {uuid:'e1', name:'RUNS_ON', fact:'Vaultwarden runs on altair', episodes:['ep-new']}]->(al), "
            "(vw)-[:RELATES_TO {uuid:'e2', name:'RUNS_ON', fact:'Vaultwarden runs on altair.', episodes:['ep-new']}]->(al), "
            "(it)-[:RELATES_TO {uuid:'e3', name:'RUNS_ON', fact:'It runs on altair', episodes:['ep-new']}]->(al), "
            "(vw)-[:RELATES_TO {uuid:'e4', name:'USES', fact:'Vaultwarden uses PostgreSQL', episodes:['ep-new']}]->(pg), "
            "(vw)-[:RELATES_TO {uuid:'x1', name:'USES', fact:'Vaultwarden uses PostgreSQL', episodes:['ep-old']}]->(pg), "
            "(it)-[:RELATES_TO {uuid:'x2', name:'RUNS_ON', fact:'It runs on altair', episodes:['ep-old', 'ep-new']}]->(al)")
    yield g
    c.delete_graph(GRAPH)
    dbm.backend.cache_clear()


@needs_falkor
def test_write_quality_on_a_real_graph(graph):
    rep = {"edges": 5, "_edges": [("e1", "RUNS_ON"), ("e2", "RUNS_ON"), ("e3", "RUNS_ON"), ("e4", "USES"), ("x2", "RUNS_ON")]}
    W.apply(type("B", (), {"graph_name": GRAPH})(), rep, EP)
    n = lambda q: graph.query(q).result_set  # noqa: E731
    assert sorted(r[0] for r in n("MATCH ()-[r:RELATES_TO]->() RETURN r.uuid")) == ["e1", "x1", "x2"]
    assert sorted(n("MATCH ()-[r:RELATES_TO {uuid:'x1'}]->() RETURN r.episodes")[0][0]) == ["ep-new", "ep-old"]
    assert sorted(n("MATCH (e:Episodic {uuid:'ep-new'}) RETURN e.entity_edges")[0][0]) == ["e1", "x1", "x2"]
    assert rep["edges"] == 2 and len(rep["collapsed"]) == 2 and [d["rule"] for d in rep["dropped"]] == ["placeholder"]
