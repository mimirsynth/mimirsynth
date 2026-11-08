"""The type of one entity changed by hand from its page (#179), and «apply as…» in the type corrector."""
import os

import pytest
from sqlalchemy import select

from test_control import _as, client  # noqa: F401

from mimirsynth.main import app
from mimirsynth.models import Audit, Brain, RetypeSuggestion, User
from mimirsynth.store import _factory

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-entity-type"


@pytest.fixture()
def graphs(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.backend.cache_clear()
    c = dbm.backend()
    if GRAPH in c.list_graphs():
        c.delete_graph(GRAPH)
    g = c.graph(GRAPH)
    g.query("CREATE (:Entity:Event {uuid:'vps', name:'vps01'}), (:Entity {uuid:'ups', name:'UPS'}), (:Entity:Topic {uuid:'nas', name:'nas01'})")
    yield g
    c.delete_graph(GRAPH)
    dbm.backend.cache_clear()


def _labels(g, uuid: str) -> list[str]:
    return sorted(g.query("MATCH (n:Entity {uuid:$u}) RETURN [l IN labels(n) WHERE l <> 'Entity']", {"u": uuid}).result_set[0][0])


def _setup(client, slug: str):  # noqa: F811
    assert client.post("/api/brains", json={"slug": slug, "name": slug.upper(), "graph_name": GRAPH}).status_code == 201
    for name in ("Host", "Event", "Device"):
        assert client.post(f"/api/brains/{slug}/vocab/types", json={"name": name, "description": f"A {name.lower()}"}).status_code == 201
    with _factory()() as db:
        bid = db.scalar(select(Brain.id).where(Brain.slug == slug))
        db.add(RetypeSuggestion(brain_id=bid, entity_uuid="vps", name="vps01", current_type="Event", suggested_type="Device", confidence=0.9))
        db.add(RetypeSuggestion(brain_id=bid, entity_uuid="nas", name="nas01", current_type="Topic", suggested_type="Device", confidence=0.8))
        db.commit()
    return bid


@pytest.mark.skipif(not FALKOR, reason="needs a disposable FalkorDB (MIMIRSYNTH_TEST_FALKOR=host)")
def test_change_type_by_hand_and_undo(client, graphs):  # noqa: F811
    bid = _setup(client, "et")
    assert client.put("/api/brains/et/members", json={"email": "rita@x.com", "role": "reader"}).status_code == 200
    assert client.put("/api/brains/et/members", json={"email": "cora@x.com", "role": "curator"}).status_code == 200

    _as("rita@x.com", "Rita")                                       # a reader cannot
    assert client.put("/api/brains/et/entities/vps/type", json={"type": "Host"}).status_code == 403
    _as("cora@x.com", "Cora")
    assert client.put("/api/brains/et/entities/vps/type", json={"type": "Server"}).status_code == 400    # outside the ontology
    assert client.put("/api/brains/et/entities/vps/type", json={"type": "Host`) DELETE (n"}).status_code == 400
    assert client.put("/api/brains/et/entities/nope/type", json={"type": "Host"}).status_code == 404
    assert client.put("/api/brains/et/entities/vps/type", json={"type": "Event"}).status_code == 409     # already that type
    r = client.put("/api/brains/et/entities/vps/type", json={"type": "Host"})
    assert r.status_code == 200 and r.json()["labels"] == ["Host"]
    op = r.json()["op"]
    assert _labels(graphs, "vps") == ["Host"]
    assert client.get("/api/brains/et/entities/vps").json()["entity"]["labels"] == ["Host"]
    types = client.get("/api/brains/et/vocab/types").json()
    assert types["ops"][0]["id"] == op and types["ops"][0]["kind"] == "entity.retype" and "Event → Host" in types["ops"][0]["summary"]
    with _factory()() as db:
        assert db.scalar(select(RetypeSuggestion.status).where(RetypeSuggestion.brain_id == bid, RetypeSuggestion.entity_uuid == "vps")) == "superseded"
        a = db.scalars(select(Audit).where(Audit.action == "vocab.entity.retype")).all()[-1]
        cora = db.scalar(select(User.id).where(User.email == "cora@x.com"))
        assert a.brain_id == bid and a.user_id == cora and "vps01" in a.detail["summary"] and "Event → Host" in a.detail["summary"]

    # the corrector no longer offers it as pending; the other suggestion stays
    app.dependency_overrides.clear()
    pending = client.get("/api/brains/et/retype", params={"status": "pending"}).json()
    assert [i["entity_uuid"] for i in pending["items"]] == ["nas"] and pending["counts"]["superseded"] == 1

    # a curator undoes it from Recent changes: labels and suggestion as they were
    _as("cora@x.com", "Cora")
    assert client.post(f"/api/brains/et/vocab/ops/{op}/revert").status_code == 200
    assert _labels(graphs, "vps") == ["Event"]
    with _factory()() as db:
        assert db.scalar(select(RetypeSuggestion.status).where(RetypeSuggestion.brain_id == bid, RetypeSuggestion.entity_uuid == "vps")) == "pending"

    # an entity without a suggestion gets a superseded one, so an analysis does not propose it; undoing removes it again
    r = client.put("/api/brains/et/entities/ups/type", json={"type": "Device"})
    assert r.status_code == 200 and _labels(graphs, "ups") == ["Device"]
    with _factory()() as db:
        assert db.scalar(select(RetypeSuggestion.status).where(RetypeSuggestion.brain_id == bid, RetypeSuggestion.entity_uuid == "ups")) == "superseded"
    assert client.post(f"/api/brains/et/vocab/ops/{r.json()['op']}/revert").status_code == 200
    assert _labels(graphs, "ups") == []
    with _factory()() as db:
        assert db.scalar(select(RetypeSuggestion).where(RetypeSuggestion.brain_id == bid, RetypeSuggestion.entity_uuid == "ups")) is None
    app.dependency_overrides.clear()


@pytest.mark.skipif(not FALKOR, reason="needs a disposable FalkorDB (MIMIRSYNTH_TEST_FALKOR=host)")
def test_apply_suggestion_as_another_type(client, graphs):  # noqa: F811
    bid = _setup(client, "et2")
    with _factory()() as db:
        sid = db.scalar(select(RetypeSuggestion.id).where(RetypeSuggestion.brain_id == bid, RetypeSuggestion.entity_uuid == "nas"))
    assert client.post(f"/api/brains/et2/retype/{sid}/apply-as", json={"type": "Server"}).status_code == 400
    assert client.post(f"/api/brains/et2/retype/{sid}/apply-as", json={"type": "Host"}).status_code == 200
    assert _labels(graphs, "nas") == ["Host"]
    applied = client.get("/api/brains/et2/retype", params={"status": "applied"}).json()["items"]
    assert [(i["entity_uuid"], i["suggested_type"], i["previous_type"]) for i in applied] == [("nas", "Host", "Topic")]
    assert client.post(f"/api/brains/et2/retype/{sid}/apply-as", json={"type": "Device"}).status_code == 404   # no longer pending
    assert client.post(f"/api/brains/et2/retype/{sid}/revert").status_code == 200
    assert _labels(graphs, "nas") == ["Topic"]

    # a curator cannot use the corrector, which works in bulk
    assert client.put("/api/brains/et2/members", json={"email": "cora@x.com", "role": "curator"}).status_code == 200
    _as("cora@x.com", "Cora")
    assert client.post(f"/api/brains/et2/retype/{sid}/apply-as", json={"type": "Host"}).status_code == 403
    app.dependency_overrides.clear()
