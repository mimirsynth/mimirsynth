"""What needs a person's decision (#164): the counters of the «Needs your attention» block, the same ones each page computes, cached for
a short time, only for curators and above, with the type corrections only for administrators."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from test_control import client  # noqa: F401

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-attention"
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _bid(slug: str) -> int:
    from mimirsynth.models import Brain
    from mimirsynth.store import _factory
    with _factory()() as db:
        return db.query(Brain).filter(Brain.slug == slug).one().id


def _tok(client, slug, role):  # noqa: F811
    return {"Authorization": f"Bearer {client.post(f'/api/brains/{slug}/tokens', json={'name': role, 'role': role}).json()['token']}"}


def _seed(bid: int) -> None:
    """Two pending proposals, one pending correction, a decided one, a pending type correction and a reference run that got worse."""
    from mimirsynth.models import Proposal, RefRun, RetypeSuggestion, User
    from mimirsynth.store import _factory
    with _factory()() as db:
        uid = db.query(User).first().id
        for kind, status in (("memory", "pending"), ("memory", "pending"), ("correction", "pending"), ("memory", "rejected")):
            db.add(Proposal(brain_id=bid, author_id=uid, name="p", body="b", kind=kind, status=status))
        db.add(RetypeSuggestion(brain_id=bid, entity_uuid="web", name="web", current_type="", suggested_type="Server", confidence=0.9))
        db.add(RefRun(brain_id=bid, status="done", params={}, summary={"delta": {"regressed": True, "lost": [{"id": 1, "text": "a"}, {"id": 1, "text": "b"}],
                                                                               "new_false_positives": [{"id": 2, "text": "c"}]}}))
        db.add(RefRun(brain_id=bid, status="done", params={"min_sim": 0.9}, summary={"delta": {"regressed": False}}))  # a simulation: ignored
        db.commit()


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
    g.query("CREATE (:Entity {uuid:'web', name:'web'}), (:Entity {uuid:'Web', name:'Web'}), (:Entity {uuid:'ip1', name:'10.0.0.1'}),"
            " (:Entity {uuid:'ip2', name:'10.0.0.2'})")
    for uuid, target, valid in (("old", "ip1", _ago(200)), ("fresh", "ip2", _ago(10))):
        g.query("MATCH (a:Entity {uuid:'web'}), (b:Entity {uuid:$t}) CREATE (a)-[:RELATES_TO {uuid:$u, name:'HAS_IP', fact:$f, valid_at:$v, "
                "created_at:$v}]->(b)", {"t": target, "u": uuid, "f": f"web HAS_IP {target}", "v": valid})
    yield g
    g.delete()
    dbm.client.cache_clear()


@needs_falkor
def test_every_counter_and_who_sees_it(client, graph, monkeypatch):  # noqa: F811
    from mimirsynth import attention
    assert client.post("/api/brains", json={"slug": "at1", "name": "At1", "graph_name": GRAPH}).status_code == 201
    bid = _bid("at1")
    _seed(bid)
    client.post("/api/brains/at1/vocab/relations", json={"name": "HasIp", "description": "La IP de un host", "functional": True,
                                                          "shelf_life_days": 90})
    attention.forget(bid)
    out = client.get("/api/brains/at1/attention").json()
    assert out == {"proposals": 2, "corrections": 1, "duplicates": 1, "conflicts": 1, "stale": 1, "retype": 1, "refqueries": 2}
    curator = client.get("/api/brains/at1/attention", headers=_tok(client, "at1", "curator")).json()
    assert "retype" not in curator and curator["conflicts"] == 1                       # only administrators can apply a type correction
    assert client.get("/api/brains/at1/attention", headers=_tok(client, "at1", "contributor")).status_code == 403


@needs_falkor
def test_cached_for_a_short_time_and_a_failing_counter_leaves_the_rest(client, graph, monkeypatch):  # noqa: F811
    from mimirsynth import attention
    assert client.post("/api/brains", json={"slug": "at2", "name": "At2", "graph_name": GRAPH}).status_code == 201
    bid = _bid("at2")
    attention.forget(bid)
    calls = []
    real = attention.COUNTERS["duplicates"]
    monkeypatch.setitem(attention.COUNTERS, "duplicates", lambda ctx: calls.append(1) or real(ctx))
    monkeypatch.setitem(attention.COUNTERS, "conflicts", lambda ctx: 1 / 0)
    first = client.get("/api/brains/at2/attention").json()
    assert first["conflicts"] is None and first["duplicates"] == 1 and first["stale"] == 0 and first["proposals"] == 0
    client.get("/api/brains/at2/attention")
    assert len(calls) == 1                                                              # the second read comes from the cache
    client.get("/api/brains/at2/attention", params={"fresh": True})
    assert len(calls) == 2                                                              # Content quality asks for them again
    attention.forget(bid)
    client.get("/api/brains/at2/attention")
    assert len(calls) == 3
