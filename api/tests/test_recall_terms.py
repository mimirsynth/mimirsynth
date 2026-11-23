"""The brain's common terms and the rank penalty per supersession warning in the recall (#459). Against PostgreSQL, on a synthetic brain:
test_recall_terms_pg.py."""
from datetime import timedelta

from sqlalchemy import select
from test_control import client  # noqa: F401

from mimirsynth import appsettings, index, terms
from mimirsynth import recall as R
from mimirsynth.health import _today
from mimirsynth.models import Brain, HealthRun
from mimirsynth.store import _factory


def test_common_terms_leave_the_text_query_and_do_not_count_as_shared():
    assert index._tsquery("¿Qué servidores usa Acme?") == "acme | servidores | usa"
    assert index._tsquery("¿Qué servidores usa Acme?", frozenset({"acme", "servidores"})) == "usa"
    assert index._tsquery("Acme", frozenset({"acme"})) == ""                      # nothing left: only the vector part ranks
    text = "acme servers run the nightly jobs"
    assert R.relevant(text, 0.45, R.query_terms("acme servers", frozenset()), 0.5)                 # two shared terms: let in with less
    assert not R.relevant(text, 0.45, R.query_terms("acme servers", frozenset({"acme"})), 0.5)     # the subject does not count
    assert R.relevant(text, 0.55, R.query_terms("acme servers", frozenset({"acme", "servers"})), 0.5)   # its similarity alone still does


def _run(db, bid, day, metrics):
    db.add(HealthRun(brain_id=bid, day=day, status="done", reason="test", metrics=metrics)); db.commit()


def test_the_common_terms_come_from_the_last_recent_health_run(client):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "terms1", "name": "T1"}).status_code == 201
    with _factory()() as db:
        bid = db.scalar(select(Brain.id).where(Brain.slug == "terms1"))
        terms.forget(bid)
        assert terms.common(bid) == {"chunks": frozenset(), "docs": frozenset()}             # never measured: nothing, as today
        terms.forget(bid)
        _run(db, bid, _today() - timedelta(days=terms.STORED_DAYS + 1), {"terms": {"chunks": {"texts": 90, "common": {"viejo": 0.5}}}})
        assert terms.common(bid)["chunks"] == frozenset()                                    # too old to use
        terms.forget(bid)
        _run(db, bid, _today(), {"terms": {"chunks": {"texts": 90, "common": {"acme": 0.9}}, "docs": {"texts": 3, "common": {}}}})
        assert terms.common(bid) == {"chunks": frozenset({"acme"}), "docs": frozenset()}
    terms.remember(bid, {"chunks": {"texts": 90, "common": {"nuevo": 0.4}}})                 # a fresh measurement is used at once
    assert terms.common(bid)["chunks"] == frozenset({"nuevo"})
    terms.forget(bid)


def test_the_measurement_needs_the_text_index(monkeypatch):
    monkeypatch.setattr(index, "enabled", lambda: False)
    assert terms.measure(1) == {}


def _w(i, warnings=0):
    return {"id": i, **({"superseded": [{"uuid": f"s{i}{k}"} for k in range(warnings)]} if warnings else {})}


def test_each_warning_moves_a_text_two_places_down():
    items = [_w(0, 1), _w(1), _w(2), _w(3, 3), _w(4), _w(5)]
    assert [x["id"] for x in R.rank_down(items, 4)] == [1, 0, 2, 4]       # one warning at the top stays in; three give the place away
    assert [x["id"] for x in R.rank_down([_w(0, 3), _w(1, 1)], 2)] == [1, 0]   # with nothing clean to take it, a warned text stays
    assert R.rank_down([], 3) == []


OLD = {"uuid": "old", "fact": "La wiki corre en altair", "source_uuid": "wiki", "target_uuid": "altair", "name": "RUNS_ON", "valid_at": "2026-01-01T00:00:00Z",
       "invalid_at": "2026-06-01T10:00:00Z", "expired_at": "2026-06-01T10:00:00Z", "created_at": "2026-01-01T00:00:00Z", "episodes": ["ep-old"], "status": "invalidated"}
NEW = {**OLD, "uuid": "new", "fact": "La wiki corre en vega", "target_uuid": "vega", "valid_at": "2026-06-01T10:00:00Z", "invalid_at": None,
       "expired_at": None, "episodes": ["ep-new"], "status": "current"}


def _chunk(cid, episode):
    return {"id": cid, "name": f"ep {cid}", "text": "texto", "valid_at": "2026-01-01", "episode_uuid": episode, "similarity": 0.8}


def test_a_fragment_that_gives_its_place_brings_none_of_its_facts(monkeypatch):
    monkeypatch.setattr(R, "superseded", lambda g, eps, gone, amap=None, entities=(): ([OLD] if "ep-old" in eps else [], {"old": [NEW]}))
    chunks = [_chunk(1, "ep-a"), _chunk(2, "ep-old"), _chunk(3, "ep-b")]
    out, cur, old, _ = R.mark_superseded([dict(c) for c in chunks], [], [], {None: "g"}, {}, keep=(2, 0))
    assert [c["id"] for c in out] == [1, 3] and cur == [] and old == []     # the warned one went third: what it states does not join
    out, cur, old, _ = R.mark_superseded([dict(c) for c in chunks], [], [], {None: "g"}, {}, keep=(3, 0))
    assert [c["id"] for c in out] == [1, 3, 2]                              # room for it: it stays, last as always, and brings both
    assert [f["uuid"] for f in cur] == ["new"] and [f["uuid"] for f in old] == ["old"]
    out, cur, old, _ = R.mark_superseded([dict(c) for c in chunks], [], [], {None: "g"}, {})
    assert [c["id"] for c in out] == [1, 3, 2] and [f["uuid"] for f in old] == ["old"]   # without the penalty, as before


class _Emb:
    def embed(self, xs):
        return [[0.0] * 3 for _ in xs]


def _recall(monkeypatch, **kw):
    seen = {}

    def search(bid, qvec, query, k=4, pool=40, recency=0.12, skip=frozenset()):
        seen.update(k=k, skip=skip)
        return [_chunk(i, "ep-old" if i == 0 else f"ep-{i}") for i in range(k)]
    monkeypatch.setattr(R, "search_facts", lambda *a, **k: [])
    monkeypatch.setattr(R.index, "search", search)
    monkeypatch.setattr(R, "alias_map", lambda db, bid: {})
    monkeypatch.setattr(R, "superseded", lambda g, eps, gone, amap=None, entities=(): ([OLD] if "ep-old" in eps else [], {"old": [NEW]}))
    monkeypatch.setattr(terms, "common", lambda bid: {"chunks": frozenset({"wiki"}), "docs": frozenset()})
    out = R.recall(1, "own", "dónde corre la wiki", 8, 3, 6000, embedder=_Emb(), n_docs=0, min_similarity=0, **kw)
    return seen, out


def test_the_recall_uses_both_only_when_on(client, monkeypatch):  # noqa: F811
    seen, out = _recall(monkeypatch)                                                        # the settings are off by default
    assert seen == {"k": 3, "skip": frozenset()} and [c["id"] for c in out["chunks"]] == [1, 2, 0]
    seen, out = _recall(monkeypatch, common_terms=True, superseded_rank=True)              # simulated on
    assert seen == {"k": 5, "skip": frozenset({"wiki"})}
    assert [c["id"] for c in out["chunks"]] == [1, 2, 0]                                    # one warning at the top: it stays, last
    on = ("recall_common_terms", "recall_superseded_rank")
    monkeypatch.setattr(appsettings, "get", lambda k, _get=appsettings.get: "yes" if k in on else _get(k))
    seen, _ = _recall(monkeypatch)                                                          # the settings on
    assert seen == {"k": 5, "skip": frozenset({"wiki"})}
    seen, _ = _recall(monkeypatch, common_terms=False, superseded_rank=False)              # and simulated off
    assert seen == {"k": 3, "skip": frozenset()}
