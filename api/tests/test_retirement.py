"""Retirement trigger (#455): a new fact saying an entity was retired or replaced queues one topic review of it, with that fact as its
anchor; the review proposes the facts that still describe it as live, and nothing is invalidated without a curator."""
import json
import os
import re

import pytest
from sqlalchemy import select

from test_control import _as, client  # noqa: F401  (first: it sets the test environment before mimirsynth reads its settings)

from mimirsynth import jobs, retirement, topic_review as tr_
from mimirsynth.main import app
from mimirsynth.models import Brain, Job, TopicReview
from mimirsynth.store import _factory

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-retirement"
ENGINE = {"base_url": "http://llm", "model": "m", "api_key": ""}


def _fact(text: str, anchor: bool = False, own: bool = True) -> dict:
    f = {"kind": "fact", "own": own, "uuid": text, "fact": text, "source": "A", "target": "B", "valid_at": "2025-01-01", "invalid_at": None,
         "current": True, "probe": None}
    return {**f, "anchor": True} if anchor else f


# --- which facts and which end ----------------------------------------------------------------------

def test_the_relation_name_says_which_end_is_retired():
    assert retirement.end("REPLACED_BY", {}) == "source" and retirement.end("ReplacedBy", {}) == "source"
    assert retirement.end("WAS_REPLACED_BY", {}) == "source" and retirement.end("has been superseded by", {}) == "source"
    assert retirement.end("MigratedTo", {}) == "source" and retirement.end("SUPERSEDES", {}) == "target"
    assert retirement.end("Supersedes", {}) == "target" and retirement.end("DECOMMISSIONED", {}) == "target"
    assert retirement.end("REEMPLAZADO_POR", {}) == "source" and retirement.end("SUSTITUYE_A", {}) == "target"
    assert retirement.end("REPLACED", {}) == "target" and retirement.end("SUPERSEDED", {}) == "target"   # «Postmark REPLACED Sendgrid»
    assert retirement.end("WAS_DECOMMISSIONED", {}) == "source" and retirement.end("IS_DEPRECATED", {}) == "source"   # passive: the first
    assert retirement.end("WAS_HOSTED_ON", {}) is None
    for name in ("RELATES_TO", "HOSTED_ON", "REMOVED_FROM", "REMOVED", "", None, "REPLACEMENT_FOR"):
        assert retirement.end(name, {}) is None
    marked = retirement.marks({"edge_types": [{"name": "Sunsets", "description": "x", "retires": "target"},
                                              {"name": "MigratedTo", "description": "x", "retires": "target"}, {"name": "HostedOn", "description": "x"}]})
    assert marked == {"SUNSETS": "target", "MIGRATED_TO": "target"}
    assert retirement.end("SUNSETS", marked) == "target" and retirement.end("MIGRATED_TO", marked) == "target"   # the brain's mark wins
    assert retirement.end("HOSTED_ON", marked) is None


def test_a_relation_is_marked_from_the_ontology_but_never_a_generic_one(client):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "ret0", "name": "R0"}).status_code == 201
    url = "/api/brains/ret0/vocab/relations"
    assert client.post(url, json={"name": "Sunsets", "description": "Something retires something", "retires": "target"}).status_code == 201
    assert client.post(url, json={"name": "RelatesTo", "description": "Anything", "retires": "source"}).status_code == 400
    onto = client.get("/api/brains/ret0/ontology").json()["ontology"]
    assert next(t for t in onto["edge_types"] if t["name"] == "Sunsets")["retires"] == "target"
    assert client.put(f"{url}/Sunsets", json={"description": "Something retires something", "retires": "source"}).status_code == 200
    assert client.put(f"{url}/Sunsets", json={"description": "Something retires something"}).status_code == 200   # left out: kept
    onto = client.get("/api/brains/ret0/ontology").json()["ontology"]
    assert next(t for t in onto["edge_types"] if t["name"] == "Sunsets")["retires"] == "source"
    assert client.put(f"{url}/Sunsets", json={"description": "Something retires something", "retires": "none"}).status_code == 200
    onto = client.get("/api/brains/ret0/ontology").json()["ontology"]
    assert "retires" not in next(t for t in onto["edge_types"] if t["name"] == "Sunsets")


# --- the review: the anchors go in every call and are never acted on ----------------------------------

def test_the_anchors_open_every_call_and_the_prompt_says_the_topic_was_retired():
    items = {"F1": _fact("Postmark replaced Sendgrid", anchor=True)}
    items.update({f"F{i}": _fact(f"fact number {i} " + "x" * 80) for i in range(2, 8)})
    one = len(tr_.line("F2", items["F2"])) + 1
    chunks, left = tr_.pack(items, calls=3, budget=one * 4)
    assert all(c[0] == "F1" for c in chunks) and [x for c in chunks for x in c if x != "F1"] == [f"F{i}" for i in range(2, 8)]
    assert left == {"facts": 0, "episodes": 0, "neighbour_facts": 0}
    user = tr_.messages({"name": "Sendgrid", "labels": []}, items, chunks[1])[1]["content"]
    assert "Retired or replaced, according to: F1" in user
    assert "Retired or replaced" not in tr_.messages({"name": "Sendgrid", "labels": []}, items, ["F2"])[1]["content"]
    assert "never act on the facts that say it was retired" in tr_.SYSTEM and tr_.PROMPT_VERSION == "topic-review/2"


def test_an_action_that_would_invalidate_the_anchor_is_discarded():
    items = {"F1": _fact("Postmark replaced Sendgrid", anchor=True), "F2": _fact("Mailer sends through Sendgrid"),
             "F3": _fact("Sendgrid was replaced by Postmark")}
    ok = lambda **kw: tr_.check(tr_.Action(why="because", **kw), items, set(items))  # noqa: E731
    assert ok(type="invalidate", facts=["F2"], evidence=["F1"])[1] == ""
    assert ok(type="invalidate", facts=["F1"], evidence=["F2"])[1] == "anchor"
    assert ok(type="drop_trivial", facts=["F1"])[1] == "anchor"
    assert ok(type="merge", facts=["F3", "F1"], keep="F3")[1] == "anchor"      # merging it away invalidates it too
    assert ok(type="merge", facts=["F1", "F3"], keep="F1")[1] == ""            # keeping it is fine
    assert ok(type="merge", facts=["F1", "F3"])[0]["keep"] == "F1"             # also when the first is kept by default
    assert ok(type="rewrite", facts=["F1"], text="Postmark replaced Sendgrid in 2025.", evidence=["F3"])[1] == "anchor"   # nor rewritten


# --- queueing --------------------------------------------------------------------------------------

def _queued_jobs(monkeypatch):
    """Jobs that stay queued (the tests run jobs inline): a review waits as it does while the workers are busy."""
    def submit(kind, brain_id, params, title, user_id=None, **kw):
        with _factory()() as db:
            j = Job(brain_id=brain_id, kind=kind, title=title, status="queued", params=params)
            db.add(j)
            db.commit()
            return j.id
    monkeypatch.setattr(jobs, "submit", submit)


def _anchor(u: str) -> dict:
    return {"uuid": u, "fact": f"fact {u}", "relation": "REPLACES", "proposal": None}


def test_one_review_per_entity_a_second_fact_joins_it_and_each_limit_says_why(client, monkeypatch):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "ret1", "name": "R1"}).status_code == 201
    monkeypatch.setattr(tr_, "_engine", lambda: ENGINE)
    _queued_jobs(monkeypatch)
    with _factory()() as db:
        b = db.scalar(select(Brain).where(Brain.slug == "ret1"))
        what, rid = tr_.queue_retirement(db, b, "sg", "Sendgrid", [_anchor("a1")])
        assert what == "queued"
        assert tr_.queue_retirement(db, b, "sg", "Sendgrid", [_anchor("a1"), _anchor("a2")]) == ("joined", rid)
        r = db.get(TopicReview, rid)
        db.refresh(r)
        assert r.trigger == "retirement" and r.created_by is None and [a["uuid"] for a in r.anchors] == ["a1", "a2"]
        assert db.scalar(select(Job.status).where(Job.id == r.job_id)) == "queued"
        # a running review read the topic before the fact came in: a new one is queued
        r.status = "running"
        db.commit()
        what, again = tr_.queue_retirement(db, b, "sg", "Sendgrid", [_anchor("a3")])
        assert what == "queued" and again != rid

    with _factory()() as db:   # the daily limit counts the automatic reviews of the day, of any entity
        b = db.scalar(select(Brain).where(Brain.slug == "ret1"))
        b.curator = {"retirement_daily": 2}
        db.commit()
        assert tr_.queue_retirement(db, b, "other", "Other", [_anchor("a4")]) == ("daily", None)
        b.curator = {"retirement_reviews": False}
        db.commit()
        assert tr_.queue_retirement(db, b, "other", "Other", [_anchor("a4")]) == ("off", None)
        b.curator = {}
        b.read_only = True
        db.commit()
        assert tr_.queue_retirement(db, b, "other", "Other", [_anchor("a4")]) == ("read_only", None)
        b.read_only = False
        db.commit()
        monkeypatch.setattr(tr_, "_engine", lambda: None)
        assert tr_.queue_retirement(db, b, "other", "Other", [_anchor("a4")]) == ("no_engine", None)
        monkeypatch.setattr(tr_, "_engine", lambda: ENGINE)
        monkeypatch.setattr(tr_.usage, "paused", lambda bid: True)
        assert tr_.queue_retirement(db, b, "other", "Other", [_anchor("a4")]) == ("paused", None)


def test_the_reviews_a_retirement_queues_never_stop_a_curator_from_asking_for_one(client, monkeypatch):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "ret2", "name": "R2"}).status_code == 201
    monkeypatch.setattr(tr_, "_engine", lambda: ENGINE)
    _queued_jobs(monkeypatch)
    with _factory()() as db:
        b = db.scalar(select(Brain).where(Brain.slug == "ret2"))
        for n in range(tr_.MAX_ACTIVE):
            assert tr_.queue_retirement(db, b, f"e{n}", "x", [_anchor(f"a{n}")])[0] == "queued"
    from mimirsynth import deps

    class Graph:   # the entity exists; nothing else is read before the review is queued
        def query(self, q, params=None):
            return None
    monkeypatch.setattr(deps, "graph", lambda name: Graph())
    monkeypatch.setattr(tr_, "rows", lambda res: [{"uuid": "mail", "name": "Mailer", "labels": []}])
    r = client.post("/api/brains/ret2/topics/entity/mail")
    assert r.status_code == 202 and r.json()["created"] and r.json()["review"]["trigger"] == "manual"


def test_the_topics_tab_counts_the_reviews_with_actions_to_decide(client):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "ret3", "name": "R3"}).status_code == 201
    with _factory()() as db:
        bid = db.scalar(select(Brain.id).where(Brain.slug == "ret3"))
        db.add_all([TopicReview(brain_id=bid, entity_uuid="a", status="ready", actions=[{"decision": "pending"}, {"decision": "approved"}]),
                    TopicReview(brain_id=bid, entity_uuid="b", status="ready", actions=[{"decision": "rejected"}]),
                    TopicReview(brain_id=bid, entity_uuid="c", status="ready", actions=[]),
                    TopicReview(brain_id=bid, entity_uuid="d", status="queued")])
        db.commit()
    assert client.get("/api/brains/ret3/attention", params={"fresh": True}).json()["topics"] == 1


def test_forgetting_finds_a_review_by_its_anchor_and_the_ingest_report_loses_the_name(client):  # noqa: F811
    from mimirsynth import forget
    from mimirsynth.write_quality import without_text
    assert client.post("/api/brains", json={"slug": "ret4", "name": "R4"}).status_code == 201
    with _factory()() as db:
        bid = db.scalar(select(Brain.id).where(Brain.slug == "ret4"))
        r = TopicReview(brain_id=bid, entity_uuid="pm", status="queued", anchors=[{"uuid": "a1", "fact": "Postmark replaced Sendgrid", "relation": "REPLACES"}])
        db.add(r)
        db.commit()
        assert [x.id for x in forget._topic_reviews(db, bid, "sg", {"a1"}, lambda v: False)] == [r.id]         # it cites one of its facts
        assert [x.id for x in forget._topic_reviews(db, bid, "sg", set(), lambda v: "Sendgrid" in str(v))] == [r.id]   # it names it
    assert without_text({"retirement": {"queued": [], "error": "KeyError"}})["retirement"]["error"] == "failed"
    rep = {"edges": 2, "retirement": {"queued": [{"entity": "sg", "name": "Sendgrid", "facts": ["a1"], "review": 3}], "not_queued": [], "joined": []}}
    out = without_text(rep)
    assert out["retirement"]["queued"] == [{"entity": "sg", "facts": ["a1"], "review": 3}] and rep["retirement"]["queued"][0]["name"] == "Sendgrid"


# --- against the graph -------------------------------------------------------------------------------

@pytest.fixture()
def env(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.backend.cache_clear()
    c = dbm.backend()
    if GRAPH in c.list_graphs():
        c.delete_graph(GRAPH)
    g = c.graph(GRAPH)
    # Sendgrid is replaced by Postmark; the memory still describes Sendgrid as live
    g.query("CREATE (m:Entity:Service {uuid:'mail', name:'Mailer'}), (s:Entity {uuid:'sg', name:'Sendgrid'}), (p:Entity {uuid:'pm', name:'Postmark'}),"
            " (w:Entity {uuid:'wh', name:'Bounce webhook'}),"
            " (m)-[:RELATES_TO {uuid:'live1', name:'SENDS_THROUGH', fact:'Mailer sends through Sendgrid', created_at:'2023-02-01T00:00:00Z'}]->(s),"
            " (s)-[:RELATES_TO {uuid:'live2', name:'CALLS', fact:'Sendgrid calls the bounce webhook', created_at:'2023-02-01T00:00:00Z'}]->(w),"
            " (p)-[:RELATES_TO {uuid:'ret1', name:'REPLACES', fact:'Postmark replaced Sendgrid in March 2025', created_at:'2025-03-02T00:00:00Z'}]->(s),"
            " (s)-[:RELATES_TO {uuid:'ret2', name:'WAS_REPLACED_BY', fact:'Sendgrid was replaced by Postmark', created_at:'2025-03-03T00:00:00Z'}]->(p),"
            " (m)-[:RELATES_TO {uuid:'other', name:'SENDS_THROUGH', fact:'Mailer sends through Postmark', created_at:'2025-03-02T00:00:00Z'}]->(p)")
    asked = []

    def fake_ask(eng, msgs, max_tokens):
        user = msgs[1]["content"]
        asked.append(user)
        ids = {m.group(2).strip(): m.group(1) for m in re.finditer(r"^(F\d+) \|.*\| (.+)$", user, re.M)}
        anchor = ids["Postmark replaced Sendgrid in March 2025"]
        return json.dumps({"state": "Sendgrid was replaced by Postmark in March 2025.", "actions": [
            {"type": "invalidate", "facts": [ids["Mailer sends through Sendgrid"], ids["Sendgrid calls the bounce webhook"]], "evidence": [anchor],
             "why": "Sendgrid was replaced."},
            {"type": "invalidate", "facts": [anchor], "evidence": [ids["Mailer sends through Postmark"]], "why": "old news"}]})
    monkeypatch.setattr(tr_, "_ask", fake_ask)
    monkeypatch.setattr(tr_, "_engine", lambda: ENGINE)
    yield g, asked
    c.delete_graph(GRAPH)
    dbm.backend.cache_clear()


def _invalid(g, uuid: str):
    return g.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() RETURN r.invalid_at", {"u": uuid}).result_set[0][0]


@pytest.mark.skipif(not FALKOR, reason="needs a disposable FalkorDB (MIMIRSYNTH_TEST_FALKOR=host)")
def test_retiring_an_entity_queues_exactly_one_review_with_the_facts_that_describe_it_as_live(client, env, monkeypatch):  # noqa: F811
    g, asked = env
    _queued_jobs(monkeypatch)   # the review waits, so the second fact can join it
    assert client.post("/api/brains", json={"slug": "ret9", "name": "R9", "graph_name": GRAPH}).status_code == 201
    with _factory()() as db:
        b = db.scalar(select(Brain).where(Brain.slug == "ret9"))
        out = retirement.detect(db, b, {"_edges": [("ret1", "REPLACES"), ("other", "SENDS_THROUGH")], "_new_edges": ["ret1", "other"]}, 41, graph=g)
        assert [e["entity"] for e in out["queued"]] == ["sg"] and out["joined"] == [] and out["not_queued"] == []
        rid = out["queued"][0]["review"]
        # the second fact of the same retirement joins the review still queued; an edge that is not new is never read
        out = retirement.detect(db, b, {"_edges": [("ret2", "WAS_REPLACED_BY"), ("live1", "SENDS_THROUGH")], "_new_edges": ["ret2"]}, 42, graph=g)
        assert out["joined"] == [{"entity": "sg", "name": "Sendgrid", "facts": ["ret2"], "review": rid}] and out["queued"] == []
        assert retirement.detect(db, b, {"_edges": [("live1", "REPLACES")], "_new_edges": []}, graph=g) is None
        assert len(db.scalars(select(TopicReview).where(TopicReview.brain_id == b.id)).all()) == 1
    tr_.run(rid)
    assert len(asked) == 1 and "Retired or replaced, according to:" in asked[0] and "Name: Sendgrid" in asked[0]
    d = client.get(f"/api/brains/ret9/topics/{rid}").json()
    assert d["trigger"] == "retirement" and [a["uuid"] for a in d["anchors"]] == ["ret1", "ret2"] and d["anchors"][0]["proposal"] == 41
    assert len(d["actions"]) == 1 and d["discarded"] == {"anchor": 1}
    assert {d["items"][x]["uuid"] for x in d["actions"][0]["facts"]} == {"live1", "live2"}
    assert not _invalid(g, "live1") and not _invalid(g, "live2") and not _invalid(g, "ret1")   # nothing without a curator
    assert client.post(f"/api/brains/ret9/topics/{rid}/actions/0/approve", json={}).json()["action"]["decision"] == "approved"
    assert _invalid(g, "live1") and _invalid(g, "live2") and not _invalid(g, "ret1") and not _invalid(g, "other")
    app.dependency_overrides.clear()


@pytest.mark.skipif(not FALKOR, reason="needs a disposable FalkorDB (MIMIRSYNTH_TEST_FALKOR=host)")
def test_an_ingestion_reports_the_review_its_retirement_fact_asked_for(client, env, monkeypatch):  # noqa: F811
    from mimirsynth import ingest, vocab_apply, write_quality
    from mimirsynth.models import Proposal
    g, _ = env
    assert client.post("/api/brains", json={"slug": "ret8", "name": "R8", "graph_name": GRAPH}).status_code == 201

    async def fake_add(graph_name, name, body, source, description, reference_time, ontology=None, report=None):
        report.update({"entities": 2, "edges": 1, "ontology": False, "off_ontology": [], "untyped_entities": 0,
                       "_edges": [("ret1", "REPLACES")], "_new_edges": ["ret1"], "_nodes": []})
        return "ep9"
    monkeypatch.setattr(ingest, "add_episode", fake_add)
    monkeypatch.setattr(ingest, "_engine", lambda: ENGINE)
    monkeypatch.setattr(write_quality, "apply", lambda brain, rep, ep, judge=None: rep.pop("_new_edges", None))   # both consume the lists, as they do
    monkeypatch.setattr(vocab_apply, "apply", lambda db, brain, rep: rep.pop("_edges", None))
    with _factory()() as db:
        b = db.scalar(select(Brain).where(Brain.slug == "ret8"))
        from mimirsynth.models import User
        p = Proposal(brain_id=b.id, author_id=db.scalar(select(User.id)), name="move", body="Postmark replaced Sendgrid in March 2025.",
                     status="approved", source="text")
        db.add(p)
        db.commit()
        pid = p.id
    assert ingest.ingest_proposal(pid) == ""
    with _factory()() as db:
        rep = db.get(Proposal, pid).ingest_report
        assert rep["retirement"]["queued"][0]["entity"] == "sg" and rep["retirement"]["queued"][0]["name"] == "Sendgrid"
        r = db.get(TopicReview, rep["retirement"]["queued"][0]["review"])
        assert r.anchors[0]["proposal"] == pid and r.anchors[0]["uuid"] == "ret1"


def test_a_graph_that_is_down_never_fails_the_ingestion_and_the_report_says_so(client):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "ret5", "name": "R5"}).status_code == 201

    class Down:
        def query(self, q, params=None):
            raise RuntimeError("graph down")
    with _factory()() as db:
        b = db.scalar(select(Brain).where(Brain.slug == "ret5"))
        out = retirement.detect(db, b, {"_edges": [("x", "REPLACES")], "_new_edges": ["x"]}, 7, graph=Down())
        assert out["error"] == "RuntimeError" and out["queued"] == []   # its kind, never its text
        assert retirement.detect(db, b, {"_edges": [("x", "RUNS_ON")], "_new_edges": ["x"]}, 7, graph=Down()) is None   # nothing to read


def test_an_ingestion_with_a_retirement_fact_and_the_graph_down_is_still_ingested(client, monkeypatch):  # noqa: F811
    from mimirsynth import db as dbm, ingest, vocab_apply, write_quality
    from mimirsynth.models import Proposal
    assert client.post("/api/brains", json={"slug": "ret6", "name": "R6"}).status_code == 201

    async def fake_add(graph_name, name, body, source, description, reference_time, ontology=None, report=None):
        report.update({"entities": 2, "edges": 1, "_edges": [("x1", "REPLACES")], "_new_edges": ["x1"], "_nodes": []})
        return "ep6"

    def down(name):
        raise ConnectionError("graph down")
    monkeypatch.setattr(ingest, "add_episode", fake_add)
    monkeypatch.setattr(ingest, "_engine", lambda: ENGINE)
    monkeypatch.setattr(write_quality, "apply", lambda brain, rep, ep, judge=None: rep.pop("_new_edges", None))
    monkeypatch.setattr(vocab_apply, "apply", lambda db, brain, rep: rep.pop("_edges", None))
    monkeypatch.setattr(dbm, "graph", down)
    pid = client.post("/api/brains/ret6/proposals", json={"name": "move", "body": "Postmark replaced Sendgrid."}).json()["id"]
    with _factory()() as db:
        db.get(Proposal, pid).status = "approved"
        db.commit()
    assert ingest.ingest_proposal(pid) == ""
    with _factory()() as db:
        p = db.get(Proposal, pid)
        assert p.status == "ingested" and p.ingest_report["retirement"]["error"] == "ConnectionError"


class _Graph:
    """The new facts as the graph holds them, after the aliases were applied."""
    def __init__(self, facts):
        self.facts = facts

    def query(self, q, params=None):
        return [f for f in self.facts if f["uuid"] in (params or {}).get("u", [])]


def _edge(u: str, name: str) -> dict:
    return {"uuid": u, "name": name, "fact": f"Ops {name} the VPN", "s": "ops", "sname": "Ops", "t": "vpn", "tname": "VPN"}


def test_the_names_are_read_through_the_brain_aliases_and_a_full_review_says_so(client, monkeypatch):  # noqa: F811
    from mimirsynth import db as dbm
    from mimirsynth.models import VocabAlias
    assert client.post("/api/brains", json={"slug": "ret7", "name": "R7"}).status_code == 201
    rel = {"name": "Sunsets", "description": "One thing retires another", "retires": "target"}
    assert client.post("/api/brains/ret7/vocab/relations", json=rel).status_code == 201
    monkeypatch.setattr(tr_, "_engine", lambda: ENGINE)
    monkeypatch.setattr(dbm, "rows", lambda res: res)
    _queued_jobs(monkeypatch)
    with _factory()() as db:
        b = db.scalar(select(Brain).where(Brain.slug == "ret7"))
        db.add_all([VocabAlias(brain_id=b.id, kind="relation", alias="PHASED_OUT", canonical="SUNSETS"),
                    VocabAlias(brain_id=b.id, kind="relation", alias="RETIRED", canonical="STATUS_OF")])
        db.commit()
        out = retirement.detect(db, b, {"_edges": [("p1", "PHASED_OUT")], "_new_edges": ["p1"]}, graph=_Graph([_edge("p1", "SUNSETS")]))
        assert out["queued"][0]["entity"] == "vpn"                                      # PHASED_OUT is SUNSETS in this brain
        r = db.get(TopicReview, out["queued"][0]["review"])
        assert r.anchors[0]["relation"] == "SUNSETS" and r.anchors[0]["source"] == "Ops" and r.anchors[0]["target"] == "VPN"
        assert retirement.detect(db, b, {"_edges": [("p2", "RETIRED")], "_new_edges": ["p2"]}, graph=_Graph([_edge("p2", "STATUS_OF")])) is None
        # a review that already holds the most anchors it keeps: what does not fit is said, never reported as joined
        db.execute(tr_.update(TopicReview).where(TopicReview.id == r.id).values(anchors=[_anchor(f"z{n}") for n in range(tr_.MAX_ANCHORS)]))
        db.commit()
        out = retirement.detect(db, b, {"_edges": [("p3", "PHASED_OUT")], "_new_edges": ["p3"]}, graph=_Graph([_edge("p3", "SUNSETS")]))
        assert out["joined"] == [] and out["not_queued"][0]["why"] == "full"


def test_the_retirement_settings_are_kept_when_a_request_leaves_them_out(client):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "ret10", "name": "R10"}).status_code == 201
    url = "/api/brains/ret10/curator/settings"
    got = client.get(url).json()
    assert got["retirement_reviews"] is True and got["retirement_daily"] == 10
    assert client.put(url, json={"enabled": False, "retirement_reviews": False, "retirement_daily": 3}).status_code == 200
    assert client.put(url, json={"enabled": False, "retirement_daily": 0}).status_code == 422
    got = client.put(url, json={"enabled": True}).json()
    assert got["retirement_reviews"] is False and got["retirement_daily"] == 3
