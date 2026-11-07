"""Archiving what is never recalled (#297): every logged recall notes when its own facts came back; the curator's archive pass only
proposes once the brain has been tracked for the whole period, and only facts not recalled, not confirmed and not verified in it;
approving archives the fact in a sidecar table (the graph untouched), the recall leaves it out unless asked, and it can be restored."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from test_control import client  # noqa: F401
from test_recall_ratings import OUT

from mimirsynth import archive as A

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-archive"
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


def test_recalls_note_their_own_facts_and_archived_ones_are_left_out(client, monkeypatch):  # noqa: F811
    from mimirsynth import memory
    from mimirsynth.models import Brain, FactArchive, FactRecall
    from mimirsynth.store import _factory
    monkeypatch.setattr(memory, "recall", lambda *a, **k: dict(OUT))
    client.post("/api/brains", json={"slug": "ar1", "name": "AR1"})
    client.post("/api/brains/ar1/recall", json={"query": "q"})
    client.post("/api/brains/ar1/recall", json={"query": "q"})
    with _factory()() as db:
        bid = db.query(Brain).filter(Brain.slug == "ar1").one().id
        rows = {r.fact_uuid: r for r in db.query(FactRecall).filter(FactRecall.brain_id == bid)}
        assert set(rows) == {"f1"} and rows["f1"].count == 2                                 # f2 is lent by another brain: not ours
        db.add(FactArchive(brain_id=bid, fact_uuid="f1"))
        db.commit()
    A.forget(bid)
    facts = [{"uuid": "f1", "fact": "a"}, {"uuid": "f2", "fact": "b", "origin": "other"}, {"uuid": "f3", "fact": "c"}]
    assert [f["uuid"] for f in A.leave_out(bid, facts)] == ["f2", "f3"]
    assert client.delete("/api/brains/ar1/archive/f1").json() == {"ok": True}
    assert [f["uuid"] for f in A.leave_out(bid, facts)] == ["f1", "f2", "f3"]
    assert client.delete("/api/brains/ar1/archive/f1").status_code == 404


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
    old, new = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(), (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    g.query("CREATE (:Entity {uuid:'vw', name:'Vaultwarden'})")
    for u, t, when in (("used", "altair", old), ("unused", "rack 7", old), ("confirmed", "Ops", old), ("young", "nas01", new)):
        g.query("MATCH (a:Entity {uuid:'vw'}) CREATE (a)-[:RELATES_TO {uuid:$u, name:'X', fact:$f, created_at:$w, valid_at:$w}]->(:Entity {uuid:$t, name:$t})",
                {"u": u, "t": t, "f": f"Vaultwarden X {t}", "w": when})
    yield g
    g.delete()
    dbm.client.cache_clear()


@needs_falkor
def test_the_archive_pass_waits_for_tracking_and_archiving_is_reversible(client, graph, monkeypatch):  # noqa: F811
    from mimirsynth import ingest
    from mimirsynth.models import Brain, FactConfirmation, FactRecall, Proposal
    from mimirsynth.store import _factory
    monkeypatch.setattr(ingest, "enabled", lambda: False)
    client.post("/api/brains", json={"slug": "ar2", "name": "AR2", "graph_name": GRAPH})
    with _factory()() as db:
        bid = db.query(Brain).filter(Brain.slug == "ar2").one().id
    assert client.post("/api/brains/ar2/curator/preview?pass=archive").json()["count"] == 0       # nothing tracked yet
    now = datetime.now(timezone.utc)
    with _factory()() as db:
        db.add(FactRecall(brain_id=bid, fact_uuid="used", first_recalled_at=now - timedelta(days=10), last_recalled_at=now))
        db.commit()
    assert client.post("/api/brains/ar2/curator/preview?pass=archive").json()["count"] == 0       # tracked for 10 days of 180
    with _factory()() as db:
        r = db.query(FactRecall).filter(FactRecall.brain_id == bid).one()
        r.first_recalled_at = now - timedelta(days=200)
        db.add(FactConfirmation(brain_id=bid, fact_uuid="confirmed"))
        db.commit()
    pv = client.post("/api/brains/ar2/curator/preview?pass=archive").json()
    assert [f["replace"][0]["uuid"] for f in pv["findings"]] == ["unused"]                       # not used, confirmed or young
    client.put("/api/brains/ar2/curator/settings", json={"enabled": True, "batch": 10, "passes": {"contradictions": False, "archive": True}})
    client.post("/api/brains/ar2/curator/run")
    pid = client.get("/api/brains/ar2/curator/runs").json()["items"][0]["proposals"][0]
    with _factory()() as db:
        p = db.get(Proposal, pid)
        assert p.category == "curator.archive" and p.claims[0]["verdict"] == "archives" and p.name.startswith("Curador: archivar")
    client.post(f"/api/brains/ar2/proposals/{pid}/approve", json={})
    ingest.ingest_proposal(pid)
    with _factory()() as db:
        assert db.get(Proposal, pid).ingest_report["claims"]["archived"] == ["unused"]
    assert graph.query("MATCH ()-[r:RELATES_TO {uuid:'unused'}]->() RETURN r.invalid_at").result_set[0][0] is None   # the graph untouched
    listed = client.get("/api/brains/ar2/archive").json()["items"]
    assert listed[0]["fact_uuid"] == "unused" and listed[0]["fact"] == "Vaultwarden X rack 7" and listed[0]["reason"].startswith("not recalled")
    assert "unused" in A.archived(bid)
    client.delete("/api/brains/ar2/archive/unused")
    assert "unused" not in A.archived(bid)
