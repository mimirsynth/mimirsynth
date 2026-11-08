"""Memory health score (#292): coverage, staleness and noise from recalls, redundancy between the same entities, one run per brain
and day (a restart never measures twice), a part that fails does not lose the others, curators read the history and measure again,
and the last measurement is a Prometheus gauge per brain."""
import os
from datetime import timedelta

import pytest

from test_control import _as, client  # noqa: F401
from test_metrics import _scrape, _value, token  # noqa: F401

from mimirsynth import health as H, recall as R
from mimirsynth.main import app
from mimirsynth.models import Brain, HealthRun, Job
from mimirsynth.store import _factory

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
GRAPH = "zz-test-health"


# --- the numbers --------------------------------------------------------------------------------

def test_a_repeat_says_the_same_thing_with_the_same_numbers():
    a = {"fact": "Vaultwarden runs on altair", "embedding": [1.0, 0.0, 0.0]}
    assert H.near_duplicate(a, {"fact": "  vaultwarden RUNS on altair ", "embedding": None})            # same text, no embedding needed
    assert H.near_duplicate(a, {"fact": "Vaultwarden is hosted on altair", "embedding": [0.99, 0.05, 0.0]})
    assert not H.near_duplicate(a, {"fact": "Vaultwarden was moved off altair", "embedding": [0.6, 0.8, 0.0]})   # far apart
    v14 = {"fact": "The wiki uses PostgreSQL 14", "embedding": [1.0, 0.0, 0.0]}
    assert not H.near_duplicate(v14, {"fact": "The wiki uses PostgreSQL 16", "embedding": [1.0, 0.0, 0.0]})  # a change, not a repeat
    assert not H.near_duplicate(a, {"fact": "Vaultwarden is hosted on altair", "embedding": None})       # no embedding: only the text


def test_repeats_count_all_but_one_of_each_cluster():
    same = [{"fact": "X runs on Y"}, {"fact": "x runs on y"}, {"fact": "X RUNS ON Y"}, {"fact": "Y backs up X nightly"}]
    assert H.repeats(same) == 2
    assert H.repeats([{"fact": "a b"}, {"fact": "c d"}]) == 0
    facts = [{"uuid": "1", "source_uuid": "x", "target_uuid": "y"}, {"uuid": "2", "source_uuid": "y", "target_uuid": "x"},
             {"uuid": "3", "source_uuid": "x", "target_uuid": "z"}]
    assert [[f["uuid"] for f in g] for g in H._groups(facts)] == [["1", "2"]]   # the same two entities, in either direction


def _out(facts=(), chunks=(), docs=(), context=""):
    return {"facts": list(facts), "chunks": list(chunks), "documents": list(docs), "context": context}


def test_outdated_items_are_the_ones_marked_and_not_the_history():
    out = _out([{"fact": "a", "status": "current", "stale_since": "2026-01-01"}, {"fact": "b", "status": "invalidated", "stale_since": "x"},
                {"fact": "c", "status": "current"}], [{"text": "f", "superseded": [{"uuid": "u"}]}, {"text": "g", "superseded": []}],
               [{"text": "p", "superseded": [{"uuid": "v"}]}])
    assert H.outdated(out) == 3
    assert H.size(out | {"context": "12345"}) == (6, 5)


def test_probes_measure_coverage_staleness_and_noise():
    answers = {
        "where does vaultwarden run?": _out([{"fact": "Vaultwarden runs on altair", "status": "current"}], context="x" * 40),
        "dns port": _out(chunks=[{"text": "the DNS resolver port is 5353", "superseded": [{"uuid": "old"}]}], context="y" * 30),
        "nothing expected here": _out(context=""),
    }

    def recall(text):
        if text == "boom":
            raise RuntimeError("embedding engine down")
        return answers.get(text, _out([{"fact": "noise", "status": "current"}], context="z" * 10) if text == "hola" else _out())
    queries = [{"id": 1, "query": "where does vaultwarden run?", "expect": [{"text": "altair", "kind": "fact"}, {"text": "port 22"}]},
               {"id": 2, "query": "dns port", "expect": [{"text": "port is 5353"}]},
               {"id": 3, "query": "nothing expected here", "expect": [], "avoid": [{"text": "altair"}]},
               {"id": 4, "query": "boom", "expect": [{"text": "x"}]}]
    m = H.probes(recall, queries)
    assert (m["expected"], m["found"], m["coverage"]) == (3, 2, 0.6667)          # the failed query adds nothing
    assert (m["stale_results"], m["staleness"]) == (1, round(1 / 3, 4))          # of the three reference queries that ran
    assert m["noise_queries"] == len(H.VAGUE) + 1                                 # the vague set and the query that expects nothing
    assert m["noise"] == round(1 / m["noise_queries"], 2) and m["noise_empty"] == round((m["noise_queries"] - 1) / m["noise_queries"], 4)
    assert m["probe_errors"] == 1 and m["reference_queries"] == 4


def test_without_reference_queries_only_the_noise_is_measured():
    m = H.probes(lambda text: _out(), [])
    assert m["coverage"] is None and m["staleness"] is None and m["noise"] == 0 and m["noise_empty"] == 1


# --- runs, schedule and API -------------------------------------------------------------------

@pytest.fixture()
def fakes(monkeypatch):
    def fake_recall(bid, graph, query, *a, **k):
        return _out([{"fact": "Vaultwarden runs on altair", "status": "current"}] if "vaultwarden" in query.lower() else [], context="c")
    monkeypatch.setattr(R, "recall", fake_recall)
    monkeypatch.setattr(H, "redundancy", lambda g: {"redundancy": 0.05, "redundant_facts": 5, "current_facts": 100,
                                                    "redundancy_sampled": False, "facts_truncated": False})


def _brain(client, slug):  # noqa: F811
    client.post("/api/brains", json={"slug": slug, "name": slug.upper()})
    with _factory()() as db:
        return db.query(Brain).filter(Brain.slug == slug).one().id


def test_a_curator_measures_and_reads_the_history(client, fakes):  # noqa: F811
    bid = _brain(client, "hs1")
    client.post("/api/brains/hs1/refqueries", json={"query": "Where does Vaultwarden run?", "expect": [{"text": "altair"}]})
    assert client.get("/api/brains/hs1/health").json() == {"items": [], "latest": None, "measuring": False}
    assert client.post("/api/brains/hs1/health/run").status_code == 202
    h = client.get("/api/brains/hs1/health").json()
    m = h["latest"]["metrics"]
    assert h["latest"]["status"] == "done" and h["latest"]["reason"] == "manual" and h["latest"]["day"] == H._today().isoformat()
    assert m["coverage"] == 1.0 and m["staleness"] == 0 and m["redundancy"] == 0.05 and m["failed"] == []
    assert m["contradictions"] is None and m["stale_facts"] is None              # no functional relation, no shelf life: not measured
    client.post("/api/brains/hs1/health/run")                                    # again the same day: replaces it, never a second row
    with _factory()() as db:
        assert db.query(HealthRun).filter(HealthRun.brain_id == bid).count() == 1
    client.put("/api/brains/hs1/members", json={"email": "colab-hs@x.com", "role": "contributor"})
    _as("colab-hs@x.com", "Colab")
    assert client.get("/api/brains/hs1/health").status_code == 403
    assert client.post("/api/brains/hs1/health/run").status_code == 403
    app.dependency_overrides.clear()


def test_a_part_that_fails_does_not_lose_the_others(client, fakes, monkeypatch):  # noqa: F811
    _brain(client, "hs2")

    def broken(g):
        raise RuntimeError("graph down")
    monkeypatch.setattr(H, "redundancy", broken)
    client.post("/api/brains/hs2/health/run")
    m = client.get("/api/brains/hs2/health").json()["latest"]["metrics"]
    assert m["failed"] == ["redundancy"] and m["redundancy"] is None and m["noise"] == 0


def test_one_run_per_brain_and_day(client, fakes):  # noqa: F811
    bid = _brain(client, "hs3")
    H.due()
    with _factory()() as db:
        assert db.query(HealthRun).filter(HealthRun.brain_id == bid, HealthRun.day == H._today()).one().status == "done"
    assert bid not in [db_r for db_r in _brains_of(H.due())]                      # measured today: not again, also after a restart
    with _factory()() as db:                                                     # a run cut by a restart: its job is no longer alive
        r = db.query(HealthRun).filter(HealthRun.brain_id == bid).one()
        r.status = "running"
        db.get(Job, r.job_id).status = "failed"
        db.commit()
    assert bid in _brains_of(H.due())
    tomorrow = H._today() + timedelta(days=1)
    assert bid in _brains_of(H.due(tomorrow))                                     # a new day, a new run


def _brains_of(run_ids):
    with _factory()() as db:
        return [db.get(HealthRun, r).brain_id for r in run_ids]


def test_the_last_measurement_is_a_gauge_per_brain(client, fakes, token):  # noqa: F811
    _brain(client, "hs4")
    client.post("/api/brains/hs4/refqueries", json={"query": "Where does Vaultwarden run?", "expect": [{"text": "nowhere"}]})
    client.post("/api/brains/hs4/health/run")
    fams = _scrape(client, token)
    assert _value(fams["mimirsynth_health_coverage"], "mimirsynth_health_coverage", brain="hs4") == 0
    assert _value(fams["mimirsynth_health_redundancy"], "mimirsynth_health_redundancy", brain="hs4") == 0.05
    assert _value(fams["mimirsynth_health_contradictions"], "mimirsynth_health_contradictions", brain="hs4") is None   # not measured


@needs_falkor
def test_redundancy_on_a_real_graph(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.backend.cache_clear()
    c = dbm.backend()
    if GRAPH in c.list_graphs():
        c.delete_graph(GRAPH)
    g = c.graph(GRAPH)
    try:
        g.query("CREATE (:Entity {uuid:'vw', name:'Vaultwarden'}), (:Entity {uuid:'al', name:'altair'}), "
                "(:Entity {uuid:'pg', name:'PostgreSQL'})")
        for uuid, src, dst, fact, vec, invalid in (
                ("a", "vw", "al", "Vaultwarden runs on altair", [1, 0, 0], None),
                ("b", "vw", "al", "Vaultwarden is hosted on altair", [0.99, 0.05, 0], None),
                ("c", "al", "vw", "altair hosts Vaultwarden", [0.98, 0.1, 0], None),
                ("d", "vw", "al", "Vaultwarden is backed up from altair", [0.2, 0.9, 0], None),
                ("e", "vw", "al", "Vaultwarden runs on altair", [1, 0, 0], "2026-01-01T00:00:00Z"),   # no longer true: not counted
                ("f", "vw", "pg", "Vaultwarden stores its data in PostgreSQL", [0, 0, 1], None)):
            g.query("MATCH (a:Entity {uuid:$s}), (b:Entity {uuid:$d}) CREATE (a)-[:RELATES_TO {uuid:$u, name:'X', fact:$f, "
                    "fact_embedding: vecf32($v), invalid_at:$i, created_at:'2026-11-01T00:00:00Z'}]->(b)",
                    {"s": src, "d": dst, "u": uuid, "f": fact, "v": vec, "i": invalid})
        out = H.redundancy(g)
        assert out == {"redundancy": 0.4, "redundant_facts": 2, "current_facts": 5, "redundancy_sampled": False, "facts_truncated": False}
        sampled = H.redundancy(g, max_sample=2)                                   # half the candidates read: one repeat, estimated two
        assert sampled["redundant_facts"] == 2 and sampled["redundancy_sampled"] is True
    finally:
        c.delete_graph(GRAPH)


# --- notification on a threshold ---------------------------------------------------------------

def test_a_coverage_drop_counts_only_the_texts_in_both_runs(monkeypatch):
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "health_coverage_drop", 0.05)
    prev = {"coverage_items": {"a": 1, "b": 1, "c": 1, "d": 1}}
    added = {"coverage_items": {"a": 1, "b": 1, "c": 1, "d": 1, "new1": 0, "new2": 0}}   # two new queries not found yet: no drop
    assert H.coverage_drop(added, prev) == (1.0, 1.0, 4) and H.crossings(added, prev) == []
    lost = {"coverage_items": {"a": 1, "b": 1, "c": 1, "d": 0}}
    assert H.coverage_drop(lost, prev) == (1.0, 0.75, 4)
    assert H.crossings(lost, prev) == ["la cobertura ha bajado del 100 % al 75 % sobre los 4 textos esperados que estaban en las dos mediciones"]
    assert H.crossings(lost, None) == [] and H.coverage_drop({"coverage_items": {"x": 1}}, prev) is None
    monkeypatch.setattr(settings, "health_coverage_drop", 0.0)                       # 0: never
    assert H.crossings(lost, prev) == []


def test_absolute_thresholds_are_off_until_set(monkeypatch):
    from mimirsynth.config import settings
    m = {"coverage": 0.5, "staleness": 0.3, "redundancy": 0.2, "noise": 2.5}
    assert H.crossings(m, None) == []
    for k, v in (("health_coverage_min", 0.8), ("health_staleness_max", 0.25), ("health_redundancy_max", 0.1), ("health_noise_max", 1.0)):
        monkeypatch.setattr(settings, k, v)
    assert H.crossings(m, None) == ["la cobertura es del 50 %, por debajo del 80 %",
                                    "el 30 % de las consultas de referencia trae algo desactualizado, más del 25 %",
                                    "el 20 % de los hechos vigentes repite otro, más del 10 %",
                                    "una pregunta vaga trae de media 2.5 elementos, más de 1"]
    assert H.crossings({"coverage": None, "staleness": None, "redundancy": None, "noise": None}, None) == []   # not measured


def test_a_measurement_that_degrades_notifies_and_one_that_recovers_closes_it(client, fakes, monkeypatch):  # noqa: F811
    from mimirsynth.config import settings
    from mimirsynth.models import Notification
    monkeypatch.setattr(settings, "health_coverage_drop", 0.05)
    bid = _brain(client, "hs5")
    client.post("/api/brains/hs5/refqueries", json={"query": "Where does Vaultwarden run?", "expect": [{"text": "altair"}]})
    client.post("/api/brains/hs5/health/run")                                     # today: found
    with _factory()() as db:                                                     # it becomes yesterday's measurement
        r = db.query(HealthRun).filter(HealthRun.brain_id == bid).one()
        r.day = H._today() - timedelta(days=1)
        db.commit()
    monkeypatch.setattr(R, "recall", lambda *a, **k: _out())                      # today the recall stops finding it
    client.post("/api/brains/hs5/health/run")
    with _factory()() as db:
        n = db.query(Notification).filter(Notification.event == "health.degraded", Notification.key == "health:hs5").one()
        assert n.resolved_at is None and n.brain_id == bid and "100 % al 0 %" in n.body and "HS5" in n.title
    monkeypatch.setattr(R, "recall", lambda *a, **k: _out([{"fact": "Vaultwarden runs on altair", "status": "current"}]))
    client.post("/api/brains/hs5/health/run")                                     # measured again today: back to normal
    with _factory()() as db:
        assert db.query(Notification).filter(Notification.event == "health.degraded", Notification.key == "health:hs5").one().resolved_at
