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
    def __init__(self, facts, vectors=None):
        self.facts, self.vectors, self.asked = facts, vectors or {}, []

    def query(self, q, params=None):
        if q == tq.FACTS:
            return self.facts[:(params or {}).get("n", len(self.facts))]
        self.asked += params["u"]
        return [{"uuid": u, "e": self.vectors[u]} for u in params["u"] if u in self.vectors]   # none given: repeats by their text


def _brain(client, slug, monkeypatch, facts=FACTS, graph=None):  # noqa: F811
    assert client.post("/api/brains", json={"slug": slug, "name": slug}).status_code == 201
    g = graph or _Graph(facts)
    monkeypatch.setattr(deps, "graph", lambda name: g)
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
                    # a retirement review ready after the newest fact, with an action to decide: still work to do, it keeps its weight
                    TopicReview(brain_id=bid, entity_uuid="sg", name="Sendgrid", status="ready", trigger="retirement",
                                actions=[{"decision": "pending"}, {"decision": "approved"}], finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
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
    assert by["sg"]["retirement"] and by["sg"]["waiting"]["trigger"] == "retirement" and by["sg"]["waiting"]["pending"] == 1
    assert by["sg"]["score"] == tq.score(0, 3, 1, 1 / 3, True, 1)
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


def test_a_fact_from_an_entity_to_itself_counts_once(client, monkeypatch):  # noqa: F811
    _brain(client, "tq6", monkeypatch, facts=[_f("s1", "a", "A", "a", "A", "A relates to itself"), _f("s2", "a", "A", "b", "B", "A uses B"),
                                               _f("s3", "c", "C", "c", "C", "C relates to itself")])
    by = {x["uuid"]: x for x in client.get("/api/brains/tq6/topics/queue").json()["items"]}
    assert by["a"]["facts"] == 2 and by["a"]["repeats"] == 0 and "c" not in by      # one fact of its own is no topic


def test_a_retirement_review_still_counts_when_a_newer_manual_review_also_waits(client, monkeypatch):  # noqa: F811
    bid, other = _brain(client, "tq7", monkeypatch), other_brain(client)
    from mimirsynth.models import Job
    with _factory()() as db:
        live, dead = Job(brain_id=bid, kind="topic.review", title="t", status="running", params={}), \
            Job(brain_id=bid, kind="topic.review", title="t", status="failed", params={})
        db.add_all([live, dead])
        db.flush()
        db.add_all([TopicReview(brain_id=bid, entity_uuid="sg", name="Sendgrid", status="ready", trigger="retirement", actions=[{"decision": "pending"}]),
                    TopicReview(brain_id=bid, entity_uuid="sg", name="Sendgrid", status="ready", trigger="manual", actions=[{"decision": "applying"}]),
                    TopicReview(brain_id=bid, entity_uuid="pm", name="Postmark", status="running", job_id=live.id),
                    TopicReview(brain_id=bid, entity_uuid="mail", name="Mailer", status="queued", job_id=dead.id),   # its job died: not waiting
                    TopicReview(brain_id=other, entity_uuid="mail", name="Mailer", status="ready", trigger="retirement",
                                actions=[{"decision": "pending"}])])                                             # another brain's
        db.commit()
    by = {x["uuid"]: x for x in client.get("/api/brains/tq7/topics/queue").json()["items"]}
    assert by["sg"]["retirement"] and by["sg"]["waiting"]["trigger"] == "manual"          # the newest one is shown, the retirement still counts
    assert by["pm"]["waiting"]["status"] == "running" and not by["pm"]["retirement"]
    assert by["mail"]["waiting"] is None and not by["mail"]["retirement"] and by["mail"]["last_review"] is None


def other_brain(client):  # noqa: F811
    """Another brain of the instance, created once."""
    with _factory()() as db:
        bid = db.scalar(select(Brain.id).where(Brain.slug == "tq-other"))
    if bid is None:
        assert client.post("/api/brains", json={"slug": "tq-other", "name": "other"}).status_code == 201
        with _factory()() as db:
            bid = db.scalar(select(Brain.id).where(Brain.slug == "tq-other"))
    return bid


def test_flagged_facts_come_from_the_shelf_life_and_the_probes_of_this_brain(client, monkeypatch):  # noqa: F811
    from mimirsynth import shelflife
    bid, other = _brain(client, "tq8", monkeypatch), other_brain(client)
    with _factory()() as db:
        db.add_all([FactProbe(brain_id=bid, fact_uuid="m3", verifier="http", state="refuted"),
                    FactProbe(brain_id=other, fact_uuid="m4", verifier="http", state="refuted")])
        db.commit()
    monkeypatch.setattr(shelflife, "scan", lambda db, brain, limit: {"items": [{"uuid": "m1"}]})
    by = {x["uuid"]: x for x in client.get("/api/brains/tq8/topics/queue").json()["items"]}
    assert by["mail"]["flagged"] == 2 and by["mail"]["flagged_share"] == 0.5 and by["sg"]["flagged"] == 1 and by["pm"]["flagged"] == 1

    def down(db, brain, limit):
        raise ConnectionError("graph down")
    monkeypatch.setattr(shelflife, "scan", down)
    by = {x["uuid"]: x for x in client.get("/api/brains/tq8/topics/queue").json()["items"]}
    assert by["mail"]["flagged"] == 1                                                     # only the probe: the list still stands


def test_another_brains_sample_never_counts(client, monkeypatch):  # noqa: F811
    bid, other = _brain(client, "tq9", monkeypatch), other_brain(client)
    with _factory()() as db:
        db.get(Brain, bid).replay = {"enabled": True}
        db.add_all([RecallSample(brain_id=bid, query="q", items=[{"kind": "fact", "id": "p1"}]),
                    RecallSample(brain_id=other, query="q", items=[{"kind": "fact", "id": "m1"}] * 3)])
        db.commit()
    by = {x["uuid"]: x for x in client.get("/api/brains/tq9/topics/queue").json()["items"]}
    assert by["pm"]["recalls"] == 1 and by["mail"]["recalls"] == 0 and by["sg"]["recalls"] == 0


def test_repeats_use_the_embeddings_and_a_large_group_is_measured_by_its_text(client, monkeypatch):  # noqa: F811
    big = [_f(f"b{n}", "x", "X", "y", "Y", f"X talks to Y on port {n}") for n in range(tq.GROUP_CAP + 1)]
    big += [_f("bdup", "x", "X", "y", "Y", "X talks to Y on port 0")]                        # one repeat by its text
    small = [_f("s1", "x", "X", "z", "Z", "X stores its backups in Z"), _f("s2", "x", "X", "z", "Z", "Backups of X are kept in Z")]
    g = _Graph(big + small, vectors={"s1": [1.0, 0.0], "s2": [0.999, 0.01]})
    _brain(client, "tq10", monkeypatch, graph=g)
    by = {x["uuid"]: x for x in client.get("/api/brains/tq10/topics/queue").json()["items"]}
    assert by["z"]["repeats"] == 1                       # two wordings, the same thing, by their embeddings
    assert by["y"]["repeats"] == 1 and by["x"]["repeats"] == 2
    assert set(g.asked) == {"s1", "s2"}                  # the large group never asks for its embeddings


def test_a_graph_that_is_down_answers_in_words(client, monkeypatch):  # noqa: F811
    class Down:
        def query(self, q, params=None):
            raise ConnectionError("redis refused")
    _brain(client, "tq11", monkeypatch, graph=Down())
    r = client.get("/api/brains/tq11/topics/queue", headers={"Accept-Language": "en"})
    assert r.status_code == 503 and r.json()["detail"] == "The brain's graph could not be read. Try again in a moment."


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
