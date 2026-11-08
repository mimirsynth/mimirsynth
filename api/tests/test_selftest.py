"""Ingestion self-test (#296): after a proposal is ingested, each new fact gets a template control question; a fact that does not come
back among the first ones flags the proposal with its question and what outranked it; the checks are rate limited per brain, can be
turned off, and the memory health counts the share of retrievable proposals."""
import os

import pytest

from test_control import client  # noqa: F401

from mimirsynth import selftest as S

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-selftest"
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


def test_the_question_and_the_check():
    assert S.question({"source": "Vaultwarden", "name": "HOSTED_ON"}) == "Vaultwarden hosted on"
    assert S.question({"source": "Wiki", "name": "RunsOn"}) == "Wiki runs on"
    facts = [{"uuid": "a", "fact": "Vaultwarden runs on altair", "source": "Vaultwarden", "name": "RUNS_ON"},
             {"uuid": "b", "fact": "Wiki uses PostgreSQL", "source": "Wiki", "name": "USES"}]
    answers = {"Vaultwarden runs on": [{"uuid": "x", "fact": "other", "status": "current"}, {"uuid": "a", "fact": "…", "status": "current"}],
               "Wiki uses": [{"uuid": "old", "fact": "Wiki used MySQL", "status": "invalidated"}, {"uuid": "y", "fact": "Wiki is on pve2", "status": "current"}]}
    out = S.check(1, "g", facts, lambda q: {"facts": answers[q]})
    assert out[0] == {"fact_uuid": "a", "fact": "Vaultwarden runs on altair", "question": "Vaultwarden runs on", "found": True, "rank": 2, "outranked_by": []}
    assert out[1]["found"] is False and out[1]["outranked_by"] == ["Wiki is on pve2"]               # what came first, never history


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
    g.query("CREATE (:Entity {uuid:'vw', name:'Vaultwarden'})-[:RELATES_TO {uuid:'n1', name:'RUNS_ON', fact:'Vaultwarden runs on altair', episodes:['ep-1']}]->"
            "(:Entity {uuid:'al', name:'altair'})")
    g.query("MATCH (a:Entity {uuid:'vw'}) CREATE (a)-[:RELATES_TO {uuid:'n2', name:'BACKED_UP_TO', fact:'Vaultwarden is backed up to nas01', episodes:['ep-1']}]->"
            "(:Entity {uuid:'nas', name:'nas01'})")
    yield g
    c.delete_graph(GRAPH)
    dbm.backend.cache_clear()


@needs_falkor
def test_an_ingested_proposal_is_checked_and_flagged(client, graph, monkeypatch):  # noqa: F811
    from mimirsynth import ingest, recall as R
    from mimirsynth.models import Brain, Proposal
    from mimirsynth.store import _factory
    from mimirsynth.config import settings
    monkeypatch.setattr(ingest, "enabled", lambda: True)

    async def fake(*a, **k):
        return "ep-1"
    monkeypatch.setattr(ingest, "add_episode", fake)
    seen = []

    def fake_recall(bid, gname, q, *a, **k):
        seen.append(q)
        return {"facts": [{"uuid": "n1", "fact": "x", "status": "current"}] if "runs on" in q else [{"uuid": "zz", "fact": "Vaultwarden's backup is weekly", "status": "current"}]}
    monkeypatch.setattr(R, "recall", fake_recall)
    client.post("/api/brains", json={"slug": "st", "name": "ST", "graph_name": GRAPH})
    pid = client.post("/api/brains/st/proposals", json={"name": "VW", "body": "Vaultwarden runs on altair and is backed up to nas01."}).json()["id"]
    ingest.ingest_proposal(pid)                                            # a curator's own proposal: approved; ingesting runs the check
    with _factory()() as db:
        st = db.get(Proposal, pid).selftest
        bid = db.query(Brain).filter(Brain.slug == "st").one().id
    assert st["retrievable"] is False and sorted(seen) == ["Vaultwarden backed up to", "Vaultwarden runs on"]
    miss = next(r for r in st["results"] if not r["found"])
    assert miss["fact_uuid"] == "n2" and miss["outranked_by"] == ["Vaultwarden's backup is weekly"]
    assert client.get(f"/api/brains/st/proposals/{pid}").json()["selftest"]["retrievable"] is False
    with _factory()() as db:
        assert S.retrievability(db, bid) == {"retrievable": 0.0, "selftested": 1, "not_retrievable": 1}
    monkeypatch.setattr(settings, "ingest_selftest_per_hour", 1)          # the hour's checks are used up: it says so
    pid2 = client.post("/api/brains/st/proposals", json={"name": "VW2", "body": "Again."}).json()["id"]
    ingest.ingest_proposal(pid2)
    with _factory()() as db:
        assert db.get(Proposal, pid2).selftest["skipped"] == "rate"
    monkeypatch.setattr(settings, "ingest_selftest", "no")
    pid3 = client.post("/api/brains/st/proposals", json={"name": "VW3", "body": "Off."}).json()["id"]
    ingest.ingest_proposal(pid3)
    with _factory()() as db:
        assert db.get(Proposal, pid3).selftest is None


def test_a_check_that_cannot_run_says_so_and_does_not_fail(client, monkeypatch):  # noqa: F811
    from mimirsynth import jobs, recall as R
    from mimirsynth.models import Brain, Job, Proposal, User
    from mimirsynth.store import _factory
    client.post("/api/brains", json={"slug": "st2", "name": "ST2"})
    with _factory()() as db:
        bid = db.query(Brain).filter(Brain.slug == "st2").one().id
        p = Proposal(brain_id=bid, author_id=db.query(User).first().id, name="x", body="y", status="ingested", episode_uuid="ep-x")
        db.add(p)
        db.commit()
        pid = p.id
    monkeypatch.setattr(S, "rows", lambda res: [{"uuid": "a", "fact": "f", "source": "S", "name": "R"}])
    monkeypatch.setattr(S, "graph", lambda name: type("G", (), {"query": lambda self, *a, **k: None})())

    def down(*a, **k):
        raise RuntimeError("embedding engine down")
    monkeypatch.setattr(R, "recall", down)
    jid = jobs.submit(S.KIND, bid, {"pid": pid}, "t")
    with _factory()() as db:
        assert db.get(Job, jid).status == "done" and db.get(Proposal, pid).selftest["error"] == "embedding engine down"
