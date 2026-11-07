"""Current-state card per entity (#294): every current fact per relation (one value only where a curator marked the relation functional,
saying how many others are current), nothing no longer true, derived from the graph when asked, first in the recall's context for a
question about the present and absent for one about the past, off by default."""
import os

import pytest

from test_control import client  # noqa: F401

from mimirsynth import statecard as SC

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-statecard"
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


def test_past_questions():
    assert SC.about_the_past("¿dónde corría antes Vaultwarden?") and SC.about_the_past("what was the IP of the wiki")
    assert not SC.about_the_past("¿dónde corre Vaultwarden?") and not SC.about_the_past("vaultwarden host")


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
    g.query("CREATE (:Entity {uuid:'vw', name:'Vaultwarden'})")
    for u, rel, t, fact, when, inv in (("a1", "RUNS_ON", "altair", "Vaultwarden runs on altair", "2026-01-01T00:00:00Z", None),
                                       ("a0", "RUNS_ON", "eridani", "Vaultwarden ran on eridani", "2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
                                       ("i1", "HAS_IP", "10.0.0.5", "Vaultwarden has IP 10.0.0.5", "2025-01-01T00:00:00Z", None),
                                       ("i2", "HAS_IP", "10.0.0.6", "Vaultwarden has IP 10.0.0.6", "2025-02-01T00:00:00Z", None),
                                       ("l1", "LOCATED_AT", "rack 2", "Vaultwarden is in rack 2", "2025-03-01T00:00:00Z", None),
                                       ("l2", "LOCATED_AT", "rack 4", "Vaultwarden is in rack 4", "2026-03-01T00:00:00Z", None)):
        g.query("MATCH (a:Entity {uuid:'vw'}) CREATE (a)-[:RELATES_TO {uuid:$u, name:$r, fact:$f, valid_at:$w, created_at:$w, invalid_at:$i, expired_at:$i}]->"
                "(:Entity {uuid:$t, name:$t})", {"u": u, "r": rel, "t": t, "f": fact, "w": when, "i": inv})
    yield g
    g.delete()
    dbm.client.cache_clear()


@needs_falkor
def test_the_card_its_place_in_the_recall_and_its_endpoint(client, graph):  # noqa: F811
    from mimirsynth.models import Brain
    from mimirsynth.recall import build_context
    from mimirsynth.store import _factory
    client.post("/api/brains", json={"slug": "sc", "name": "SC", "graph_name": GRAPH})
    with _factory()() as db:
        bid = db.query(Brain).filter(Brain.slug == "sc").one().id
    c = SC.card(bid, graph, "vw", None, {"LOCATED_AT"})
    rels = {r["relation"]: r for r in c["relations"]}
    assert [v["target"] for v in rels["RUNS_ON"]["values"]] == ["altair"]                    # what stopped being true is not there
    assert [v["target"] for v in rels["HAS_IP"]["values"]] == ["10.0.0.6", "10.0.0.5"]       # not functional: all, newest first
    assert [v["target"] for v in rels["LOCATED_AT"]["values"]] == ["rack 4"] and rels["LOCATED_AT"]["also_current"] == 1
    facts = [{"uuid": "a1", "status": "current", "source_uuid": "vw", "fact": "Vaultwarden runs on altair", "valid_at": "2026-01-01T00:00:00Z", "created_at": None}]
    assert SC.for_recall(bid, graph, "¿dónde corre Vaultwarden?", facts, None) == []          # off by default
    cards = SC.for_recall(bid, graph, "¿dónde corre Vaultwarden?", facts, None, on=True)
    assert [x["name"] for x in cards] == ["Vaultwarden"]
    assert SC.for_recall(bid, graph, "¿dónde corría antes Vaultwarden?", facts, None, on=True) == []
    ctx = build_context(facts, [], 6000, cards=cards)
    assert ctx.index("## Estado actual de «Vaultwarden»") < ctx.index("## Hechos vigentes") and "- RUNS_ON: altair (desde 2026-01-01)" in ctx
    assert client.get("/api/brains/sc/entities/vw/state").json()["name"] == "Vaultwarden"
    assert client.get("/api/brains/sc/entities/nope/state").status_code == 404
