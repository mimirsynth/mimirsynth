"""Search in every brain (#129): only the brains the person can read (no federation, nothing about the others), the query's vector
computed once, a slow or failing brain marked without stopping the rest, and not for API tokens."""
import time

import pytest

from test_control import client  # noqa: F401


@pytest.fixture()
def fake_recall(monkeypatch):
    """Recall without FalkorDB nor an embedding engine: each brain answers with a fact named after its graph."""
    from mimirsynth import embed, recall, usage
    import threading
    calls = {"embed": 0, "scope": [], "held": threading.Event()}   # a brain named «…-held» waits until the test sets it

    class Embedder:
        def embed(self, texts):
            calls["embed"] += 1
            calls["scope"].append(usage.current())   # whose AI consumption the embedding counts in
            return [[0.1, 0.2, 0.3] for _ in texts]

    def facts(graph_name, qvec, limit, amap=None):
        if graph_name.endswith("-slow"):
            time.sleep(1.0)
        if graph_name.endswith("-held"):
            calls["held"].wait(10)
        if graph_name.endswith("-broken"):
            raise ConnectionError("grafo caído")
        return [{"uuid": f"u-{graph_name}", "fact": f"hecho de {graph_name}", "status": "current", "name": "R", "source": "a", "target": "b",
                 "source_uuid": "a", "target_uuid": "b", "valid_at": None, "created_at": None, "score": 0.9}]
    monkeypatch.setattr(embed, "get_embedder", lambda: Embedder())
    monkeypatch.setattr(recall, "search_facts", facts)
    monkeypatch.setattr(recall.index, "search", lambda *a, **k: [])
    monkeypatch.setattr(recall, "search_documents", lambda *a, **k: ([], "ok"))
    yield calls
    calls["held"].set()   # whatever happened in the test, no held brain outlives it


def _signed_in(uid: int):
    """A dependency that acts as the person `uid`, with a session that is closed at once: one left open per request would hold a
    database connection until the garbage collector runs, and enough of them exhaust the pool for the tests that follow (#177)."""
    from mimirsynth.models import User
    from mimirsynth.store import _factory

    def who():
        with _factory()() as db:
            user = db.get(User, uid)
            db.expunge(user)
            return user
    return who


def _person(slugs_roles: dict[str, str], other: list[str]) -> int:
    """A person with a role in some new brains, and other new brains they have nothing to do with."""
    from mimirsynth.models import Brain, Membership, User
    from mimirsynth.store import _factory
    with _factory()() as db:
        u = User(email=f"{'-'.join(slugs_roles)}@example.com", name="s", status="active")
        db.add(u); db.flush()
        for slug in [*slugs_roles, *other]:
            b = Brain(slug=slug, name=slug.upper(), graph_name=slug)
            db.add(b); db.flush()
            if slug in slugs_roles:
                db.add(Membership(user_id=u.id, brain_id=b.id, role=slugs_roles[slug]))
        db.commit()
        return u.id


def _as(uid: int):
    from mimirsynth.deps import current_user
    from mimirsynth.main import app
    app.dependency_overrides[current_user] = _signed_in(uid)


def test_only_the_brains_the_person_can_read(client, fake_recall):  # noqa: F811
    from mimirsynth.main import app
    uid = _person({"sr1-a": "reader", "sr1-b": "curator"}, other=["sr1-secret"])
    _as(uid)
    try:
        r = client.post("/api/search", json={"query": "dónde está nextcloud"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    d = r.json()
    assert [b["slug"] for b in d["brains"]] == ["sr1-a", "sr1-b"]
    assert "sr1-secret" not in r.text and "SR1-SECRET" not in r.text            # not even its name or a count
    a = d["brains"][0]
    assert a["state"] == "ok" and a["role"] == "reader" and a["facts"][0]["fact"] == "hecho de sr1-a" and "context" not in a
    assert fake_recall["embed"] == 1                                            # one vector for every brain


def test_a_slow_or_broken_brain_does_not_stop_the_others(client, fake_recall, monkeypatch):  # noqa: F811
    from mimirsynth import search
    from mimirsynth.main import app
    monkeypatch.setattr(search, "WAIT_SECONDS", 0.3)
    uid = _person({"sr2-ok": "reader", "sr2-slow": "reader", "sr2-broken": "reader"}, other=[])
    _as(uid)
    try:
        t0 = time.monotonic()
        d = client.post("/api/search", json={"query": "x"}).json()
        took = time.monotonic() - t0
    finally:
        app.dependency_overrides.clear()
    states = {b["slug"]: b["state"] for b in d["brains"]}
    assert states == {"sr2-ok": "ok", "sr2-slow": "timeout", "sr2-broken": "error"}
    assert took < 0.9                                                           # it did not wait for the slow one
    assert d["brains"][0]["slug"] == "sr2-ok"                                   # brains with results first
    assert "grafo caído" not in str(d)


def test_not_for_api_tokens(client, fake_recall):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "sr3", "name": "SR3"}).status_code == 201
    tok = client.post("/api/brains/sr3/tokens", json={"name": "t", "role": "reader"}).json()["token"]
    r = client.post("/api/search", json={"query": "x"}, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_without_brains_or_without_embeddings(client, fake_recall, monkeypatch):  # noqa: F811
    from mimirsynth import embed
    from mimirsynth.main import app
    uid = _person({}, other=["sr4-x"])
    _as(uid)
    try:
        assert client.post("/api/search", json={"query": "x"}).json()["brains"] == []
    finally:
        app.dependency_overrides.clear()

    class Down:
        def embed(self, texts):
            raise ConnectionError("ollama apagado")
    monkeypatch.setattr(embed, "get_embedder", lambda: Down())
    assert client.post("/api/brains", json={"slug": "sr4-y", "name": "Y"}).status_code == 201
    assert client.post("/api/search", json={"query": "x"}).status_code == 502
    assert client.post("/api/search", json={"query": ""}).status_code == 422


def _bid(slug: str) -> int:
    from mimirsynth.models import Brain
    from mimirsynth.store import _factory
    with _factory()() as db:
        return db.query(Brain).filter_by(slug=slug).one().id


def test_a_slow_search_does_not_hold_up_the_next_ones(client, fake_recall, monkeypatch):  # noqa: F811
    """#176: a brain past its time keeps running in its own search's pool; the instance's cap answers 429 instead of queueing."""
    import threading

    from mimirsynth import search
    from mimirsynth.main import app
    monkeypatch.setattr(search, "WAIT_SECONDS", 0.2)
    monkeypatch.setattr(search, "_INFLIGHT", threading.BoundedSemaphore(2))
    held = _person({"sr5-held": "reader"}, other=[])
    fast = _person({"sr5-fast": "reader"}, other=[])
    try:
        _as(held)
        assert client.post("/api/search", json={"query": "x"}).json()["brains"][0]["state"] == "timeout"   # still running behind
        _as(fast)
        assert client.post("/api/search", json={"query": "x"}).json()["brains"][0]["state"] == "ok"        # not stuck behind it
        _as(held)
        client.post("/api/search", json={"query": "x"})                                                      # a second one held
        assert client.post("/api/search", json={"query": "x"}).status_code == 429                          # both slots in use
        fake_recall["held"].set()                                                                            # they finish
        for _ in range(50):
            if search._INFLIGHT.acquire(blocking=False):
                search._INFLIGHT.release()
                break
            time.sleep(0.05)
        _as(fast)
        assert client.post("/api/search", json={"query": "x"}).json()["brains"][0]["state"] == "ok"        # their slots came back
    finally:
        fake_recall["held"].set()
        app.dependency_overrides.clear()


def test_searches_per_person_and_hour(client, fake_recall, monkeypatch):  # noqa: F811
    from mimirsynth import ratelimit, search
    from mimirsynth.main import app
    real = search.appsettings.get
    monkeypatch.setattr(search.appsettings, "get", lambda k: 2 if k == "search_per_hour" else real(k))
    ratelimit.reset()
    uid = _person({"sr6": "reader"}, other=[])
    _as(uid)
    try:
        assert [client.post("/api/search", json={"query": "x"}).status_code for _ in range(3)] == [200, 200, 429]
    finally:
        app.dependency_overrides.clear()
    other = _person({"sr6-b": "reader"}, other=[])                                                     # per person
    _as(other)
    try:
        assert client.post("/api/search", json={"query": "x"}).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_the_embedding_counts_in_the_open_brain_unless_its_budget_is_paused(client, fake_recall, monkeypatch):  # noqa: F811
    from mimirsynth import usage
    from mimirsynth.main import app
    uid = _person({"sr7-a": "reader", "sr7-b": "reader"}, other=[])
    a, b = _bid("sr7-a"), _bid("sr7-b")
    paused: set[int] = set()
    monkeypatch.setattr(usage, "_check_budget", lambda bid, force=False: {"paused": bid in paused})
    _as(uid)
    try:
        client.post("/api/search", json={"query": "x", "brain": "sr7-b"})
        assert fake_recall["scope"][-1] == (b, "recall")                                                # the open brain
        client.post("/api/search", json={"query": "x"})
        assert fake_recall["scope"][-1] == (a, "recall")                                                # none open: the first
        paused.add(b)
        d = client.post("/api/search", json={"query": "x", "brain": "sr7-b"}).json()
        assert fake_recall["scope"][-1] == (a, "recall") and len(d["brains"]) == 2                     # paused: the next one pays
        paused.add(a)
        n = fake_recall["embed"]
        assert client.post("/api/search", json={"query": "x"}).status_code == 429                      # every brain paused
        assert fake_recall["embed"] == n
    finally:
        app.dependency_overrides.clear()

