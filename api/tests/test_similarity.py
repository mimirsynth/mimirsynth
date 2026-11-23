"""How similar two facts of a brain usually are (#468): the baseline of random pairs, the pairs a curator decided are the same thing,
the calibrated «close» of the related-knowledge panel, and the thresholds shown to an administrator."""
import math
import random

from sqlalchemy import select

from test_control import _as, client  # noqa: F401  (first: it sets the test environment before mimirsynth reads its settings)

from mimirsynth import proposals, recall, similarity
from mimirsynth.main import app
from mimirsynth.models import Brain, HealthRun, Proposal, TopicReview
from mimirsynth.store import _factory

DIM = 16


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def _near(v, rnd, noise):
    return _unit([x + rnd.gauss(0, noise) for x in v])


class _Graph:
    """Facts of a brain about one subject: every embedding leans the same way (the saturation of #468), plus their own direction."""
    def __init__(self, n=60, seed=1):
        rnd = random.Random(seed)
        common = _unit([1.0] * DIM)
        self.facts = [{"uuid": f"f{i}", "s": f"e{i}", "t": f"e{i + 1}"} for i in range(n)]
        self.vec = {f["uuid"]: _unit([0.8 * c + 0.6 * x for c, x in zip(common, _unit([rnd.gauss(0, 1) for _ in range(DIM)]))]) for f in self.facts}
        # two facts a curator said are the same thing: almost one direction; and an invalidated one that keeps its embedding
        self.vec["dup"] = _near(self.vec["f0"], rnd, 0.02)
        self.queries = []

    def query(self, q, params=None):
        self.queries.append(q)
        if q == similarity._CURRENT:
            return self.facts[:params["n"]]
        return [{"uuid": u, "e": self.vec[u]} for u in params["u"] if u in self.vec]


def _brain(client, slug):  # noqa: F811
    assert client.post("/api/brains", json={"slug": slug, "name": slug}).status_code == 201
    with _factory()() as db:
        return db.scalar(select(Brain.id).where(Brain.slug == slug))


def test_the_baseline_and_the_same_thing_pairs_are_measured(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(similarity, "rows", lambda res: res)
    bid = _brain(client, "sim1")
    g = _Graph()
    with _factory()() as db:
        db.add_all([Proposal(brain_id=bid, author_id=1, name="r", body="r", status="ingested", category="curator.redundancy",
                             decision={"curator": {"keep": {"uuid": "f0"}}}, claims=[{"supersedes": "dup"}]),   # one uuid per claim, as curator.py writes it
                    Proposal(brain_id=bid, author_id=1, name="r2", body="r", status="rejected", category="curator.redundancy",   # not approved
                             decision={"curator": {"keep": {"uuid": "f1"}}}, claims=[{"supersedes": ["f2"]}]),
                    TopicReview(brain_id=bid, entity_uuid="e3", status="ready", items={"F1": {"uuid": "f3"}, "F2": {"uuid": "f4"}},
                                actions=[{"type": "merge", "facts": ["F1", "F2"], "keep": "F1", "decision": "approved"},
                                         {"type": "merge", "facts": ["F1", "F2"], "keep": "F2", "decision": "rejected"}])])
        db.commit()
        assert similarity.same_pairs(db, bid) == [("f0", "dup"), ("f3", "f4")]
        m = similarity.measure(g, db, bid, {"model": "m1", "dim": DIM})
    b = m["baseline"]
    assert m["model"] == "m1" and m["facts"] == 60 and not m["too_few"] and b["pairs"] == similarity.PAIRS
    assert 0.5 < b["p50"] < b["p95"] < b["p99"] < 1                     # unrelated facts sit high: the saturation the issue measured
    assert m["same"]["pairs"] == 2 and m["same"]["p10"] is not None
    assert m["same"]["under_p99"] == 0.5                                    # f0~dup above the baseline, f3/f4 (unrelated vectors) under it


def test_a_small_brain_is_not_measured(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(similarity, "rows", lambda res: res)
    bid = _brain(client, "sim2")
    with _factory()() as db:
        m = similarity.measure(_Graph(n=similarity.MIN_FACTS - 1), db, bid, {"model": "m1", "dim": DIM})
    assert m["too_few"] and m["baseline"] is None
    assert similarity.close_cosine(m) == similarity.CLOSE_FLOOR and similarity.standing(0.9, m) is None


def test_close_is_above_what_unrelated_facts_of_the_brain_score():
    m = {"too_few": False, "baseline": {"p50": 0.61, "p95": 0.72, "p99": 0.78}}
    assert similarity.close_cosine(m) == 0.78 and similarity.close_cosine({"too_few": False, "baseline": {"p99": 0.4}}) == similarity.CLOSE_FLOOR
    assert [similarity.standing(c, m) for c in (0.8, 0.75, 0.6, None)] == ["well_above", "above", "usual", None]


def test_the_measurement_is_kept_and_a_new_model_makes_it_stale(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(similarity, "rows", lambda res: res)
    bid = _brain(client, "sim3")
    similarity.forget(bid)
    model = {"model": "m1", "dim": DIM}
    monkeypatch.setattr(similarity, "_model", lambda: model)
    with _factory()() as db:
        b = db.get(Brain, bid)
        g = _Graph()
        first = similarity.current(db, b, g)
        n = len(g.queries)
        assert similarity.current(db, b, g) == first and len(g.queries) == n                 # from memory
        similarity.forget(bid)
        db.add(HealthRun(brain_id=bid, day=__import__("datetime").date.today(), status="done", metrics={"similarity": {**first, "facts": 999}}))
        db.commit()
        assert similarity.current(db, b, g)["facts"] == 999 and len(g.queries) == n          # from the brain's health run
        model["model"] = "m2"                                                                  # another embedding model: measured again
        assert similarity.current(db, b, g)["model"] == "m2" and len(g.queries) > n

        class Down:
            def query(self, q, params=None):
                raise ConnectionError("graph down")
        assert similarity.current(db, b, Down(), refresh=True) is None                         # the panels keep the fixed thresholds
        assert similarity.current(db, b, g)["model"] == "m2"                                   # what was measured stays in use meanwhile
        similarity.forget(bid)
        assert similarity.current(db, b, Down(), refresh=True) is None and similarity.current(db, b, g) is None   # backing off
        assert similarity.current(db, b, g, refresh=True)["model"] == "m2"                    # an administrator measures again
        assert similarity.current(db, b, g) is not None                                         # and the back-off is over
        # a measurement kept with an old health run is taken again
        similarity.forget(bid)
        old = {**first, "model": "m2", "measured_at": "2020-01-01T00:00:00+00:00", "facts": 777}
        run = db.scalar(select(HealthRun).where(HealthRun.brain_id == bid))
        run.metrics = {"similarity": old}
        db.commit()
        assert similarity.current(db, b, g)["facts"] == 60


def test_unrelated_facts_are_not_close_in_a_measured_brain(client, monkeypatch):  # noqa: F811
    """The case of the issue: the relevant fact at sim 0.88 and unrelated ones at 0.87 (cosine 0.74), all «close» before."""
    facts = [{"uuid": "rel", "fact": "El trabajo de copia en cinta se aborta por falta de espacio", "score": 0.88, "similarity": 0.76},
             {"uuid": "u1", "fact": "La tarea de la lista de la compra tiene una marca", "score": 0.87, "similarity": 0.74},
             {"uuid": "u2", "fact": "El servicio de vídeo se quedó sin memoria", "score": 0.87, "similarity": 0.74}]
    monkeypatch.setattr(recall, "recall", lambda *a, **k: {"facts": facts})
    measured = {"too_few": False, "baseline": {"p50": 0.62, "p95": 0.72, "p99": 0.75}}
    monkeypatch.setattr(proposals, "calibration", lambda brain: measured)
    bid = _brain(client, "sim4")
    with _factory()() as db:
        p = Proposal(brain_id=bid, author_id=1, name="Copia en cinta abortada", body="El trabajo de copia en cinta de anoche se abortó", status="pending")
        db.add(p)
        db.commit()
        pid = p.id
    r = client.get(f"/api/brains/sim4/proposals/{pid}/related").json()
    by = {f["uuid"]: f for f in r["facts"]}
    assert by["rel"]["relevance"] == "close" and by["rel"]["standing"] == "well_above"
    assert by["u1"]["relevance"] == "related" and by["u1"]["standing"] == "above" and by["u2"]["relevance"] == "related"
    assert r["calibration"] == {"measured": True, "close": 0.75, "usual": 0.62, "p95": 0.72, "p99": 0.75}
    monkeypatch.setattr(proposals, "calibration", lambda brain: None)                          # not measured: today's fixed threshold
    r = client.get(f"/api/brains/sim4/proposals/{pid}/related").json()
    assert {f["uuid"]: f["relevance"] for f in r["facts"]} == {"rel": "close", "u1": "close", "u2": "close"} and not r["calibration"]["measured"]


def test_repeats_keeps_reading_the_weighted_score():
    """Only «close» reads the plain similarity: «repeats» (a known duplicate) is judged as before, on recall's weighted score."""
    words = proposals._words("nas01 en sala A")
    assert proposals.relevance("nas01 en sala A del CPD", words, 0.90, plain=0.96) == "close"     # weighted down: not a repeat
    assert proposals.relevance("nas01 en sala A del CPD", words, 0.96) == "repeats"
    assert proposals.relevance("algo distinto del todo", words, 0.80, close=0.875, plain=0.86) == "related"
    assert proposals.relevance("algo distinto del todo", words, 0.80, close=0.875, plain=0.88) == "close"


def test_a_brain_with_no_usable_pairs_is_not_measured(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(similarity, "rows", lambda res: res)
    bid = _brain(client, "sim6")
    g = _Graph(n=40)
    for f in g.facts:                                       # every fact between the same two entities: no pair says anything
        f["s"], f["t"] = "a", "b"
    with _factory()() as db:
        m = similarity.measure(g, db, bid, {"model": "m1", "dim": DIM})
    assert m["too_few"] and m["reason"] == "pairs" and m["baseline"] is None and similarity.close_cosine(m) == similarity.CLOSE_FLOOR


def test_a_new_close_threshold_clears_the_pending_verdicts(client, monkeypatch):  # noqa: F811
    bid = _brain(client, "sim7")
    similarity.forget(bid)
    with _factory()() as db:
        db.add_all([Proposal(brain_id=bid, author_id=1, name="a", body="a", status="pending", related_verdict="similar"),
                    Proposal(brain_id=bid, author_id=1, name="b", body="b", status="pending", related_verdict="similar", category="curator.redundancy"),
                    Proposal(brain_id=bid, author_id=1, name="c", body="c", status="approved", related_verdict="similar")])
        db.commit()
        similarity.remember(bid, {"too_few": True, "baseline": None}, db)          # a restart with the fixed threshold: nothing moved
        assert db.scalar(select(Proposal.related_verdict).where(Proposal.brain_id == bid, Proposal.name == "a")) == "similar"
        similarity.remember(bid, {"too_few": False, "baseline": {"p50": 0.6, "p95": 0.72, "p99": 0.75}}, db)
        got = {p.name: p.related_verdict for p in db.scalars(select(Proposal).where(Proposal.brain_id == bid))}
        assert got == {"a": "", "b": "similar", "c": "similar"}                  # the curator's and decided ones keep theirs
        db.get(Proposal, db.scalar(select(Proposal.id).where(Proposal.brain_id == bid, Proposal.name == "a"))).related_verdict = "related"
        db.commit()
        similarity.remember(bid, {"too_few": False, "baseline": {"p50": 0.6, "p95": 0.72, "p99": 0.752}}, db)   # «close» did not move
        assert db.scalar(select(Proposal.related_verdict).where(Proposal.brain_id == bid, Proposal.name == "a")) == "related"


def test_the_background_verdict_reads_the_calibration(client, monkeypatch):  # noqa: F811
    facts = [{"uuid": "u1", "fact": "La copia en cinta de los domingos usa el cartucho dos", "score": 0.87, "similarity": 0.74}]
    monkeypatch.setattr(recall, "recall", lambda *a, **k: {"facts": facts})
    bid = _brain(client, "sim8")
    with _factory()() as db:
        p = Proposal(brain_id=bid, author_id=1, name="Copia en cinta abortada", body="La copia en cinta se abortó", status="pending")
        db.add(p)
        db.commit()
        pid = p.id
    monkeypatch.setattr(proposals.ingest, "enabled", lambda: True)
    monkeypatch.setattr(proposals, "calibration", lambda brain: {"too_few": False, "baseline": {"p50": 0.62, "p95": 0.72, "p99": 0.75}})
    proposals.check_related(pid)
    with _factory()() as db:
        assert db.get(Proposal, pid).related_verdict == "related"
    monkeypatch.setattr(proposals, "calibration", lambda brain: None)
    with _factory()() as db:
        db.get(Proposal, pid).related_verdict = ""
        db.commit()
    proposals.check_related(pid)
    with _factory()() as db:
        assert db.get(Proposal, pid).related_verdict == "similar"               # the fixed threshold calls it close


def test_an_administrator_sees_the_thresholds_against_the_distribution(client, monkeypatch):  # noqa: F811
    from mimirsynth import deps
    monkeypatch.setattr(similarity, "rows", lambda res: res)
    monkeypatch.setattr(similarity, "_model", lambda: {"model": "m1", "dim": DIM})
    g = _Graph()
    monkeypatch.setattr(deps, "graph", lambda name: g)
    bid = _brain(client, "sim5")
    similarity.forget(bid)
    r = client.get("/api/brains/sim5/similarity").json()
    keys = {t["key"]: t["cosine"] for t in r["thresholds"]}
    assert set(keys) == {"close", "near_duplicate", "recall_min", "distil_cover"} and keys["near_duplicate"] == 0.93
    assert r["measurement"]["baseline"]["p99"] and r["suggested_recall_min"] == round(r["measurement"]["baseline"]["p95"], 2)
    assert client.post("/api/brains/sim5/similarity/measure").status_code == 200
    client.put("/api/brains/sim5/members", json={"email": "cid@x.com", "role": "curator"})
    client.put("/api/brains/sim5/members", json={"email": "ria@x.com", "role": "reader"})
    _as("cid@x.com", "Cid")
    assert client.get("/api/brains/sim5/similarity").status_code == 200 and client.post("/api/brains/sim5/similarity/measure").status_code == 403
    _as("ria@x.com", "Ria")
    assert client.get("/api/brains/sim5/similarity").status_code == 403
    app.dependency_overrides.clear()

    def down(name):
        raise ConnectionError("graph down")
    monkeypatch.setattr(deps, "graph", down)                                                   # a graph that is down: «not measured»
    similarity.forget(bid)
    r = client.get("/api/brains/sim5/similarity")
    assert r.status_code == 200 and r.json()["measurement"] is None
    with _factory()() as db:
        assert db.get(Brain, bid) is not None


# --- against the graph ---------------------------------------------------------------------------------

import os  # noqa: E402

import pytest  # noqa: E402

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-similarity"


@pytest.mark.skipif(not FALKOR, reason="needs a disposable FalkorDB (MIMIRSYNTH_TEST_FALKOR=host)")
def test_the_measurement_reads_the_current_facts_of_the_graph(client, monkeypatch):  # noqa: F811
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.backend.cache_clear()
    c = dbm.backend()
    if GRAPH in c.list_graphs():
        c.delete_graph(GRAPH)
    g = c.graph(GRAPH)
    src = _Graph(n=40)
    for i, f in enumerate(src.facts):
        g.query("MERGE (a:Entity {uuid:$s}) MERGE (b:Entity {uuid:$t}) CREATE (a)-[:RELATES_TO {uuid:$u, fact:$u, fact_embedding:vecf32($e)}]->(b)",
                {"s": f["s"], "t": f["t"], "u": f["uuid"], "e": src.vec[f["uuid"]]})
    g.query("MATCH ()-[r:RELATES_TO {uuid:'f39'}]->() SET r.invalid_at = '2026-01-01T00:00:00Z'")   # no longer current: not sampled
    try:
        assert client.post("/api/brains", json={"slug": "simg", "name": "SG", "graph_name": GRAPH}).status_code == 201
        with _factory()() as db:
            m = similarity.measure(g, db, db.scalar(select(Brain.id).where(Brain.slug == "simg")), {"model": "m1", "dim": DIM})
        assert m["facts"] == 39 and not m["too_few"] and 0.5 < m["baseline"]["p50"] < m["baseline"]["p99"] < 1
    finally:
        c.delete_graph(GRAPH)
        dbm.backend.cache_clear()
