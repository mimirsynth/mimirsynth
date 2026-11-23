"""Topics to review (#456): the brain's entities ranked by recall traffic, size, noise and how long ago they were reviewed, with the
inputs next to each row."""
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from test_control import _as, client  # noqa: F401  (first: it sets the test environment before mimirsynth reads its settings)

from mimirsynth import deps, topic_queue as tq
from mimirsynth.main import app
from mimirsynth.models import Brain, FactProbe, FactRecall, RecallSample, TopicReview
from mimirsynth.store import _factory


def _f(u, s, sname, t, tname, fact, day=1):
    return {"uuid": u, "fact": fact, "created_at": f"2025-01-{day:02d}T00:00:00Z", "source_uuid": s, "source": sname, "target_uuid": t, "target": tname,
            "source_labels": ["Entity", "Service"] if s == "mail" else ["Entity"], "target_labels": ["Entity"]}


FACTS = [_f("m1", "mail", "Mailer", "sg", "Sendgrid", "Mailer sends through Sendgrid"),
         _f("m2", "mail", "Mailer", "sg", "Sendgrid", "Mailer sends through Sendgrid", 2),       # a repeat of m1
         _f("m3", "mail", "Mailer", "pm", "Postmark", "Mailer sends through Postmark", 3),
         _f("m4", "mail", "Mailer", "q", "Queue", "Mailer reads the queue", 4),                 # Queue has one fact: not a topic
         _f("s1", "sg", "Sendgrid", "wh", "Webhook", "Sendgrid calls the bounce webhook", 5),
         _f("p1", "pm", "Postmark", "eu", "EU region", "Postmark runs in the EU region", 6)]


class _Graph:
    def __init__(self, facts):
        self.facts = facts

    def query(self, q, params=None):
        if q == tq.FACTS:
            return self.facts[:(params or {}).get("n", len(self.facts))]
        return []   # no embeddings: repeats are found by their text


def _brain(client, slug, monkeypatch, facts=FACTS):  # noqa: F811
    assert client.post("/api/brains", json={"slug": slug, "name": slug}).status_code == 201
    monkeypatch.setattr(deps, "graph", lambda name: _Graph(facts))
    monkeypatch.setattr(tq, "rows", lambda res: res)
    with _factory()() as db:
        return db.scalar(select(Brain.id).where(Brain.slug == slug))


def test_the_queue_ranks_by_traffic_size_and_noise_and_shows_why(client, monkeypatch):  # noqa: F811
    bid = _brain(client, "tq1", monkeypatch)
    other = _brain(client, "tq1b", monkeypatch)
    with _factory()() as db:
        db.add_all([FactRecall(brain_id=bid, fact_uuid="m3", count=10),
                    FactRecall(brain_id=other, fact_uuid="m1", count=99),          # another brain's traffic never counts here
                    FactProbe(brain_id=bid, fact_uuid="s1", verifier="http", state="refuted"),
                    FactProbe(brain_id=bid, fact_uuid="p1", verifier="http", state="verified"),
                    TopicReview(brain_id=bid, entity_uuid="sg", name="Sendgrid", status="ready", trigger="retirement",
                                actions=[{"decision": "pending"}]),
                    # Mailer was reviewed after its newest fact: nothing new, it drops down
                    TopicReview(brain_id=bid, entity_uuid="mail", name="Mailer", status="ready", actions=[],
                                finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc))])
        db.commit()
    out = client.get("/api/brains/tq1/topics/queue").json()
    assert out["recalls_from"] == "counts" and out["replay_days"] is None and out["entities"] == 3 and not out["facts_truncated"]
    by = {x["uuid"]: x for x in out["items"]}
    assert [x["uuid"] for x in out["items"]][:3] == ["pm", "sg", "mail"] and "q" not in by and "wh" not in by   # one fact is no topic
    assert by["pm"]["recalls"] == 10 and by["pm"]["facts"] == 2 and by["pm"]["flagged"] == 0 and by["pm"]["last_review"] is None
    assert by["sg"]["recalls"] == 0 and by["sg"]["repeats"] == 1 and by["sg"]["flagged"] == 1 and by["sg"]["flagged_share"] == 0.333
    assert by["sg"]["retirement"] and by["sg"]["waiting"]["trigger"] == "retirement"
    assert by["mail"]["recalls"] == 10 and by["mail"]["facts"] == 4 and by["mail"]["repeats"] == 1 and by["mail"]["waiting"] is None
    assert by["mail"]["last_review"]["new_facts"] == 0 and by["mail"]["type"] == "Service" and by["pm"]["type"] is None
    assert by["mail"]["score"] == tq.score(10, 4, 1, 0, False, tq.REVIEWED)
    assert client.get("/api/brains/tq1/topics/queue", params={"limit": 1}).json()["items"][0]["uuid"] == "pm"
    assert client.get("/api/brains/tq1/topics/queue", params={"limit": 0}).status_code == 422


def test_with_the_replay_sample_on_the_recalls_are_the_sampled_ones(client, monkeypatch):  # noqa: F811
    bid = _brain(client, "tq2", monkeypatch)
    with _factory()() as db:
        db.get(Brain, bid).replay = {"enabled": True, "days": 14}
        db.add_all([FactRecall(brain_id=bid, fact_uuid="m3", count=50),           # with the sample on, the counts are not read
                    RecallSample(brain_id=bid, query="how is mail sent", items=[{"kind": "fact", "id": "m1"}, {"kind": "fact", "id": "m2"}]),
                    RecallSample(brain_id=bid, query="bounces", items=[{"kind": "fact", "id": "s1"}, {"kind": "chunk", "id": "m3"}])])
        db.commit()
    out = client.get("/api/brains/tq2/topics/queue").json()
    by = {x["uuid"]: x for x in out["items"]}
    assert out["recalls_from"] == "replay" and out["replay_days"] == 14
    assert by["sg"]["recalls"] == 2 and by["mail"]["recalls"] == 1 and by["pm"]["recalls"] == 0   # one recall counts once per entity


def test_new_facts_since_the_last_review_bring_a_topic_back():
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert tq.freshness(None, now, now) == 1
    assert tq.freshness(now - timedelta(days=5), now - timedelta(days=6), now) == tq.REVIEWED          # nothing new since
    assert tq.freshness(now - timedelta(days=1), now, now) < tq.freshness(now - timedelta(days=20), now, now) < 1
    assert tq.freshness(now - timedelta(days=tq.FRESH_DAYS + 1), now, now) == 1
    assert tq.score(0, 2, 0, 0, False, 1) < tq.score(0, 2, 1, 0, False, 1) < tq.score(0, 2, 1, 0.5, False, 1) < tq.score(0, 2, 1, 0.5, True, 1)
    assert tq.score(0, 2, 0, 0, False, 1) < tq.score(1, 2, 0, 0, False, 1)                              # traffic multiplies
    assert tq._when("2025-01-02T00:00:00Z") == datetime(2025, 1, 2, tzinfo=timezone.utc) and tq._when("bad") is None


def test_a_review_with_new_facts_since_counts_them(client, monkeypatch):  # noqa: F811
    bid = _brain(client, "tq3", monkeypatch)
    with _factory()() as db:
        db.add(TopicReview(brain_id=bid, entity_uuid="mail", name="Mailer", status="ready", actions=[],
                           finished_at=datetime(2025, 1, 2, 12, tzinfo=timezone.utc)))
        db.commit()
    by = {x["uuid"]: x for x in client.get("/api/brains/tq3/topics/queue").json()["items"]}
    assert by["mail"]["last_review"]["new_facts"] == 2      # m3 and m4 arrived after it


def test_only_curators_see_the_queue(client, monkeypatch):  # noqa: F811
    _brain(client, "tq4", monkeypatch)
    assert client.put("/api/brains/tq4/members", json={"email": "rina@x.com", "role": "reader"}).status_code in (200, 201)
    _as("rina@x.com", "Rina")
    assert client.get("/api/brains/tq4/topics/queue").status_code == 403
    app.dependency_overrides.clear()


def test_an_empty_brain_has_an_empty_queue(client, monkeypatch):  # noqa: F811
    _brain(client, "tq5", monkeypatch, facts=[])
    out = client.get("/api/brains/tq5/topics/queue").json()
    assert out["items"] == [] and out["entities"] == 0


# --- against the graph -------------------------------------------------------------------------------

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-topic-queue"


@pytest.mark.skipif(not FALKOR, reason="needs a disposable FalkorDB (MIMIRSYNTH_TEST_FALKOR=host)")
def test_the_queue_reads_the_current_facts_of_the_graph(client, monkeypatch):  # noqa: F811
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.backend.cache_clear()
    c = dbm.backend()
    if GRAPH in c.list_graphs():
        c.delete_graph(GRAPH)
    g = c.graph(GRAPH)
    g.query("CREATE (m:Entity:Service {uuid:'mail', name:'Mailer'}), (s:Entity {uuid:'sg', name:'Sendgrid'}), (p:Entity {uuid:'pm', name:'Postmark'}),"
            " (m)-[:RELATES_TO {uuid:'m1', fact:'Mailer sends through Sendgrid', created_at:'2025-01-01T00:00:00Z'}]->(s),"
            " (m)-[:RELATES_TO {uuid:'m2', fact:'Mailer sends through Sendgrid', created_at:'2025-01-02T00:00:00Z'}]->(s),"
            " (m)-[:RELATES_TO {uuid:'m3', fact:'Mailer sends through Postmark', created_at:'2025-01-03T00:00:00Z'}]->(p),"
            " (m)-[:RELATES_TO {uuid:'old', fact:'Mailer used SMTP', created_at:'2020-01-01T00:00:00Z', invalid_at:'2021-01-01T00:00:00Z'}]->(p)")
    try:
        assert client.post("/api/brains", json={"slug": "tqg", "name": "TQ", "graph_name": GRAPH}).status_code == 201
        out = client.get("/api/brains/tqg/topics/queue").json()
        by = {x["uuid"]: x for x in out["items"]}
        assert set(by) == {"mail", "sg"}                                   # Postmark has one current fact: the invalidated one is not counted
        assert by["mail"]["type"] == "Service" and by["mail"]["facts"] == 3 and by["mail"]["repeats"] == 1 and by["sg"]["repeats"] == 1
    finally:
        c.delete_graph(GRAPH)
        dbm.backend.cache_clear()
