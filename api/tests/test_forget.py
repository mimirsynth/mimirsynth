"""Right to be forgotten, the report (issue 134): what deleting an entity would touch, layer by layer, read-only, found by the entity and
by its name and aliases as whole words without case or accents; only the brain's owner, from a session, and the audit log keeps counts."""
import os

import pytest

from test_control import client  # noqa: F401

from mimirsynth import forget as F

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-forget"
SNAP = f"_snap_{GRAPH}_20260101000000"
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


def test_the_matcher_ignores_case_and_accents_and_needs_whole_words():
    m = F.Matcher(["José Pérez", "jperez@example.com", "Al"])
    assert m.terms == ["jperez@example.com", "jose perez"]                    # a term under three letters is dropped
    assert m("Hoy habló JOSE   PEREZ con Ana") and m("mail a jperez@example.com") and m({"who": "José Pérez"})
    assert not m("josé pereza") and not m("Pérez") and not m(None)
    assert all("_" in p for p in m.like())                                     # accents may differ: those letters are wildcards


@pytest.fixture()
def graph(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.client.cache_clear()
    c = dbm.client()
    for name in (GRAPH, SNAP):
        if name in c.list_graphs():
            c.select_graph(name).delete()
    g = c.select_graph(GRAPH)
    for target in (g, c.select_graph(SNAP)):   # the snapshot an entity merge kept holds the person too
        target.query("CREATE (p:Entity {uuid:'p', name:'José Pérez', aliases:['Pepe Pérez']}), (a:Entity {uuid:'acme', name:'Acme', "
                      "summary:'Acme, where José Pérez works'}), (x:Entity {uuid:'x', name:'Madrid'}), (d:Entity {uuid:'d', name:'jperez@example.com'}), "
                      "(p)-[:RELATES_TO {uuid:'f1', name:'WORKS_AT', fact:'José Pérez works at Acme'}]->(a), "
                      "(a)-[:RELATES_TO {uuid:'f2', name:'LOCATED_IN', fact:'Acme hired Jose Perez in Madrid'}]->(x), "
                      "(a)-[:RELATES_TO {uuid:'f3', name:'LOCATED_IN', fact:'Acme is in Madrid'}]->(x), "
                      "(:Episodic {uuid:'e1', name:'n1', content:'a note'})-[:MENTIONS]->(p), "
                      "(:Episodic {uuid:'e2', name:'n2', content:'Pepe Perez called'}), (:Episodic {uuid:'e3', name:'n3', content:'nothing here'})")
    yield g
    for name in (GRAPH, SNAP):
        c.select_graph(name).delete()
    dbm.client.cache_clear()


@needs_falkor
def test_the_report_lists_every_layer_and_changes_nothing(client, graph):  # noqa: F811
    from mimirsynth.models import Audit, Brain, FactConfirmation, Job, Notification, Proposal, RecallLog, RefQuery, User
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "fg1", "name": "FG1", "graph_name": GRAPH}).status_code == 201
    with _factory()() as db:
        bid, uid = db.query(Brain).filter(Brain.slug == "fg1").one().id, db.query(User).first().id
        db.add_all([Proposal(brain_id=bid, author_id=uid, name="Note", body="José Pérez prefers mornings", source="text", status="ingested"),
                    Proposal(brain_id=bid, author_id=uid, name="Other", body="nothing about anyone", source="text", status="pending"),
                    RecallLog(brain_id=bid, rid="r1", query_hash="h", query_text="where does jose perez work"),
                    Notification(event="x", title="Pepe Pérez", brain_id=bid), Job(kind="k", brain_id=bid, title="Ingerir: José Pérez"),
                    Audit(brain_id=bid, action="x", detail={"name": "José Pérez"}), RefQuery(brain_id=bid, query="who is Pepe Perez"),
                    FactConfirmation(brain_id=bid, fact_uuid="f1")])
        db.commit()
    r = client.post("/api/brains/fg1/forget/report", json={"entity": "p", "aliases": ["jperez@example.com"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["entity"]["name"] == "José Pérez" and set(out["terms"]) == {"jose perez", "pepe perez", "jperez@example.com"}
    lay = {x["key"]: x for x in out["layers"]}
    assert lay["entity"]["action"] == "delete" and lay["entity"]["facts"] == 1
    assert lay["episodes"]["count"] == 2 and lay["episodes"]["mentions"] == 1 and lay["episodes"]["text"] == 1   # e1 by the graph, e2 by name
    assert [i["uuid"] for i in lay["other_facts"]["items"]] == ["f2"] and lay["other_facts"]["action"] == "review"
    assert [i["uuid"] for i in lay["other_summaries"]["items"]] == ["acme"]
    assert [i["uuid"] for i in lay["similar_entities"]["items"]] == ["d"]                              # named like an alias
    assert lay["snapshots"]["count"] == 1 and lay["snapshots"]["items"][0] == {"name": SNAP, "entity": True, "episodes": 1}
    assert lay["proposals"]["count"] == 1 and lay["proposals"]["action"] == "purge"
    assert lay["recall_logs"]["count"] == 1 and lay["notifications"]["count"] == 1 and lay["jobs"]["count"] == 1
    assert lay["audit"]["count"] == 1 and lay["ref_queries"]["count"] == 1 and lay["fact_records"]["count"] == 1
    assert {x["key"] for x in out["layers"] if x["where"] == "outside"} == {"backups", "logs", "other_systems"}
    assert graph.query("MATCH (n:Entity {uuid:'p'}) RETURN n").result_set                              # nothing was deleted
    with _factory()() as db:
        a = db.query(Audit).filter(Audit.action == "forget.report").one()
        assert "Pérez" not in str(a.detail) and "perez" not in str(a.detail).lower() and a.detail["counts"]["episodes"] == 2

    assert client.post("/api/brains/fg1/forget/report", json={"entity": "nope"}).status_code == 404
    graph.query("CREATE (:Entity {uuid:'al', name:'Al'})")
    assert client.post("/api/brains/fg1/forget/report", json={"entity": "al"}).status_code == 422   # nothing long enough to look for
