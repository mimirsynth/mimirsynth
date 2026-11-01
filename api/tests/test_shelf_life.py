"""Shelf life per relation type (#114): a current fact past its relation's shelf life is to review: it weighs less in the recall and
says so, it is listed for curators, confirming it renews its date without touching the graph, and nothing changes without a shelf life."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from test_control import client  # noqa: F401

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-shelf-life"
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


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
    g.query("CREATE (:Entity {uuid:'web', name:'web'}), (:Entity {uuid:'ip1', name:'10.0.0.1'}), (:Entity {uuid:'ip2', name:'10.0.0.2'}),"
            " (:Entity {uuid:'ip3', name:'10.0.0.3'}), (:Entity {uuid:'ops', name:'Ops'})")
    for uuid, name, target, valid, invalid, vec in (("old", "HAS_IP", "ip1", _ago(200), None, [1, 0, 0, 0]),
                                                     ("fresh", "HAS_IP", "ip2", _ago(10), None, [0.9, 0.1, 0, 0]),
                                                     ("nodate", "HAS_IP", "ip3", None, None, [0.8, 0.2, 0, 0]),
                                                     ("gone", "HAS_IP", "ip1", _ago(400), _ago(300), [0.7, 0.3, 0, 0]),
                                                     ("owner", "OWNED_BY", "ops", _ago(500), None, [0.6, 0.4, 0, 0])):
        g.query("MATCH (a:Entity {uuid:'web'}), (b:Entity {uuid:$t}) CREATE (a)-[:RELATES_TO {uuid:$u, name:$n, fact:$f, valid_at:$v, "
                "invalid_at:$i, expired_at:$i, created_at:$c, fact_embedding: vecf32($e)}]->(b)",
                {"t": target, "u": uuid, "n": name, "f": f"web {name} {target} ({uuid})", "v": valid, "i": invalid, "c": _ago(1), "e": vec})
    yield g
    g.delete()
    dbm.client.cache_clear()


class Emb:
    def embed(self, texts):
        return [[1.0, 0, 0, 0] for _ in texts]


@needs_falkor
def test_a_fact_past_its_shelf_life_is_to_review(client, graph):  # noqa: F811
    from mimirsynth import recall as R
    from mimirsynth.models import Audit
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "sl1", "name": "Sl1", "graph_name": GRAPH}).status_code == 201
    # without a shelf life nothing changes
    out = R.recall(_bid("sl1"), GRAPH, "ip de web", 5, 0, 4000, embedder=Emb(), n_docs=0)
    assert not any(f.get("stale_since") for f in out["facts"]) and "sin confirmar" not in out["context"]
    assert client.get("/api/brains/sl1/review/stale").json() == {"relations": {}, "total": 0, "items": [], "truncated": False}
    # a shelf life of 90 days on HasIp (the graph writes HAS_IP: the same relation)
    r = client.post("/api/brains/sl1/vocab/relations", json={"name": "HasIp", "description": "La IP de un host", "shelf_life_days": 90})
    assert r.status_code == 201, r.text
    stale = client.get("/api/brains/sl1/review/stale").json()
    assert stale["relations"] == {"HAS_IP": 90} and [i["uuid"] for i in stale["items"]] == ["old"]   # not fresh, nodate or gone
    assert stale["items"][0]["days_over"] >= 109 and stale["items"][0]["confirmed_at"] is None
    out = R.recall(_bid("sl1"), GRAPH, "ip de web", 5, 0, 4000, embedder=Emb(), n_docs=0)
    by = {f["uuid"]: f for f in out["facts"]}
    assert by["old"].get("stale_since") and not by["fresh"].get("stale_since") and not by["owner"].get("stale_since")
    assert by["old"]["score"] < by["fresh"]["score"]                                # it weighs less: the fresh one comes first
    assert [f["uuid"] for f in out["facts"]].index("fresh") < [f["uuid"] for f in out["facts"]].index("old")
    assert "(old)" in out["context"] and "sin confirmar desde" in out["context"]
    # confirming renews its date: nothing in the graph changes
    before = graph.query("MATCH ()-[r:RELATES_TO {uuid:'old'}]->() RETURN properties(r)").result_set[0][0]
    assert client.post("/api/brains/sl1/review/stale/old/confirm").status_code == 200
    assert graph.query("MATCH ()-[r:RELATES_TO {uuid:'old'}]->() RETURN properties(r)").result_set[0][0] == before
    assert client.get("/api/brains/sl1/review/stale").json()["total"] == 0
    out = R.recall(_bid("sl1"), GRAPH, "ip de web", 5, 0, 4000, embedder=Emb(), n_docs=0)
    assert not any(f.get("stale_since") for f in out["facts"])
    assert client.post("/api/brains/sl1/review/stale/gone/confirm").status_code == 409     # already invalidated
    assert client.post("/api/brains/sl1/review/stale/nope/confirm").status_code == 404
    with _factory()() as db:
        assert db.query(Audit).filter(Audit.action == "fact.confirm").count() == 1


def _bid(slug: str) -> int:
    from mimirsynth.models import Brain
    from mimirsynth.store import _factory
    with _factory()() as db:
        return db.query(Brain).filter(Brain.slug == slug).one().id


@needs_falkor
def test_the_daily_check_counts_without_text(client, graph):  # noqa: F811
    from mimirsynth import shelflife
    from mimirsynth.models import Notification
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "sl2", "name": "Sl2", "graph_name": GRAPH}).status_code == 201
    client.post("/api/brains/sl2/vocab/relations", json={"name": "OwnedBy", "description": "Quién lleva un servicio", "shelf_life_days": 30})
    assert shelflife.check_all() >= 1
    with _factory()() as db:
        n = db.query(Notification).filter(Notification.event == "facts.stale", Notification.key == "stale:sl2").one()
        assert "1 hechos" in n.title and "Ops" not in n.title + n.body and n.resolved_at is None
    client.post("/api/brains/sl2/review/stale/owner/confirm")
    shelflife.check_all()
    with _factory()() as db:
        assert db.query(Notification).filter(Notification.key == "stale:sl2").one().resolved_at is not None


@needs_falkor
def test_the_queue_says_when_it_shows_only_part(client, graph, monkeypatch):  # noqa: F811
    """Review of #158: past MAX_SCAN facts of the relations with a shelf life, the oldest are read and `truncated` says so."""
    from mimirsynth import shelflife
    assert client.post("/api/brains", json={"slug": "sl4", "name": "Sl4", "graph_name": GRAPH}).status_code == 201
    client.post("/api/brains/sl4/vocab/relations", json={"name": "HasIp", "description": "La IP de un host", "shelf_life_days": 5})
    full = client.get("/api/brains/sl4/review/stale").json()
    assert full["truncated"] is False and {i["uuid"] for i in full["items"]} == {"old", "fresh"}     # OWNED_BY is not even read
    monkeypatch.setattr(shelflife, "MAX_SCAN", 1)
    part = client.get("/api/brains/sl4/review/stale").json()
    assert part["truncated"] is True and [i["uuid"] for i in part["items"]] == ["old"]                 # the oldest
    r = client.post("/api/brains/sl4/review/stale/owner/confirm")
    assert r.status_code == 409 and "vida útil" in r.json()["detail"]                                 # OWNED_BY has none here


@needs_falkor
def test_the_recall_reuses_the_shelf_lives_until_the_ontology_changes(client, graph, monkeypatch):  # noqa: F811
    from mimirsynth import shelflife
    assert client.post("/api/brains", json={"slug": "sl5", "name": "Sl5", "graph_name": GRAPH}).status_code == 201
    bid = _bid("sl5")
    reads = []
    real = shelflife.get_ontology
    monkeypatch.setattr(shelflife, "get_ontology", lambda db, b: reads.append(b) or real(db, b))
    facts = [{"uuid": "old", "name": "HAS_IP", "status": "current", "valid_at": _ago(200), "score": 0.9}]
    for _ in range(3):
        shelflife.mark(bid, [dict(f) for f in facts])
    assert reads == [bid]                                                       # one read for three recalls
    client.post("/api/brains/sl5/vocab/relations", json={"name": "HasIp", "description": "La IP de un host", "shelf_life_days": 90})
    out = shelflife.mark(bid, [dict(f) for f in facts])
    assert out[0].get("stale_since")                                            # saving the ontology cleared the cache


def test_shelf_life_in_the_ontology(client):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "sl3", "name": "Sl3"}).status_code == 201
    r = client.post("/api/brains/sl3/vocab/relations", json={"name": "RunsVersion", "description": "Versión que ejecuta", "shelf_life_days": 30})
    assert r.status_code == 201
    rel = lambda: next(t for t in client.get("/api/brains/sl3/ontology").json()["ontology"]["edge_types"] if t["name"] == "RunsVersion")  # noqa: E731
    assert rel()["shelf_life_days"] == 30
    assert client.put("/api/brains/sl3/vocab/relations/RunsVersion", json={"description": "Versión que ejecuta"}).status_code == 200
    assert rel()["shelf_life_days"] == 30                                           # empty leaves it as it was
    client.put("/api/brains/sl3/vocab/relations/RunsVersion", json={"description": "Versión que ejecuta", "shelf_life_days": 0})
    assert "shelf_life_days" not in rel()                                           # 0 removes it
    r = client.post("/api/brains/sl3/vocab/relations", json={"name": "RelatesTo", "description": "Genérica", "shelf_life_days": 30})
    assert r.status_code in (400, 422)                                              # a generic relation cannot have one
    from mimirsynth import shelflife
    assert shelflife.shelf_lives({"edge_types": [{"name": "HasIp", "shelf_life_days": 90}, {"name": "LocatedAt"}]}) == {"HAS_IP": 90}
    now = datetime.now(timezone.utc)
    assert shelflife.stale_since(None, None, 10) is None                            # no date: never stale
    assert shelflife.stale_since(_ago(20), now - timedelta(days=2), 10) is None     # confirmed two days ago
