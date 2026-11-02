"""Prometheus metrics (#131): `/metrics` only exists with a token and only answers with it; the labels are a closed list and carry no
text of the memories; recalls, jobs and calls to AI engines are counted where they happen, and what is stored is read on each scrape."""
import os

import pytest
from prometheus_client.parser import text_string_to_metric_families
from test_control import client  # noqa: F401

TOKEN = "metrics-token-for-tests"
FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


@pytest.fixture()
def token(monkeypatch):
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "metrics_token", TOKEN)
    return {"Authorization": f"Bearer {TOKEN}"}


def _scrape(client, headers) -> dict[str, list]:  # noqa: F811
    r = client.get("/metrics", headers=headers)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    return {f.name: f.samples for f in text_string_to_metric_families(r.text)}


def _value(samples, name: str, **labels) -> float | None:
    hit = [s.value for s in samples if s.name == name and all(s.labels.get(k) == v for k, v in labels.items())]
    return hit[0] if hit else None


def _brain(client, slug: str) -> int:  # noqa: F811
    from mimirsynth.models import Brain
    from mimirsynth.store import _factory
    client.post("/api/brains", json={"slug": slug, "name": slug})
    with _factory()() as db:
        return db.query(Brain).filter(Brain.slug == slug).one().id


def test_metrics_need_their_token(client, monkeypatch):  # noqa: F811
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "metrics_token", "")
    assert client.get("/metrics").status_code == 404                                    # off: as if it did not exist
    assert client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 404
    monkeypatch.setattr(settings, "metrics_token", TOKEN)
    r = client.get("/metrics")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert "mimirsynth_" not in r.text
    for bad in ("Bearer otro", f"Basic {TOKEN}", TOKEN, f"Bearer {TOKEN}x"):
        assert client.get("/metrics", headers={"Authorization": bad}).status_code == 401
    assert client.get("/metrics", headers={"Authorization": f"bearer {TOKEN}"}).status_code == 200
    assert client.get("/api/metrics").status_code != 200                                # only at /metrics, not under /api


def test_a_session_does_not_open_the_metrics(client, token):  # noqa: F811
    """Signed in as the instance administrator (auth off in the tests), the route still asks for its token."""
    assert client.get("/api/me").status_code == 200
    assert client.get("/metrics").status_code == 401


def test_recall_jobs_and_engines_are_counted(client, token, monkeypatch):  # noqa: F811
    from mimirsynth import jobs, recall, usage
    bid = _brain(client, "metrics-a")

    class Embedder:
        def embed(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]
    monkeypatch.setattr(recall, "search_facts", lambda *a, **k: [{"fact": "f", "status": "current", "uuid": "u", "name": "R",
                                                                     "valid_at": None, "created_at": None}])
    monkeypatch.setattr(recall.index, "search", lambda *a, **k: [])
    monkeypatch.setattr(recall, "search_documents", lambda *a, **k: ([], "ok"))
    secret_query = "¿dónde vive la contraseña de Ana García?"
    before = _scrape(client, token)
    n0 = _value(before.get("mimirsynth_recall_seconds", []), "mimirsynth_recall_seconds_count", brain="metrics-a", part="total") or 0
    recall.recall(bid, "metrics-a", secret_query, embedder=Embedder())
    recall.recall(bid, "metrics-a", secret_query, embedder=Embedder(), n_docs=0)

    @jobs.register("zz.metrics", "Prueba de métricas")
    def _fails(ctx, params):
        raise RuntimeError("no")
    jobs.submit("zz.metrics", bid, {}, "x")

    usage.record("llm", "modelo-x", 200, 120, 30, brain_id=bid, purpose="ingest")
    usage.record("llm", "modelo-x", 429, brain_id=bid, purpose="ingest")
    usage.record("embedding", "emb-x", 503, brain_id=bid, purpose="recall")

    m = _scrape(client, token)
    rs = m["mimirsynth_recall_seconds"]
    assert _value(rs, "mimirsynth_recall_seconds_count", brain="metrics-a", part="total") == n0 + 2
    for part in ("embed", "facts", "chunks", "documents"):
        assert _value(rs, "mimirsynth_recall_seconds_count", brain="metrics-a", part=part), part
    docs = m["mimirsynth_recall_documents"]
    assert _value(docs, "mimirsynth_recall_documents_total", brain="metrics-a", state="ok") >= 1
    assert _value(docs, "mimirsynth_recall_documents_total", brain="metrics-a", state="off") >= 1
    assert _value(m["mimirsynth_job_seconds"], "mimirsynth_job_seconds_count", kind="zz.metrics", status="failed") == 1
    calls = m["mimirsynth_ai_requests"]
    assert _value(calls, "mimirsynth_ai_requests_total", kind="llm", model="modelo-x", outcome="ok") >= 1
    assert _value(calls, "mimirsynth_ai_requests_total", kind="llm", model="modelo-x", outcome="rate_limited") >= 1
    assert _value(calls, "mimirsynth_ai_requests_total", kind="embedding", model="emb-x", outcome="server_error") >= 1
    tokens = m["mimirsynth_ai_tokens"]
    assert _value(tokens, "mimirsynth_ai_tokens_total", kind="llm", model="modelo-x", direction="in") >= 120
    assert _value(tokens, "mimirsynth_ai_tokens_total", kind="llm", model="modelo-x", direction="out") >= 30
    text = client.get("/metrics", headers=token).text
    assert "contraseña" not in text and "Ana" not in text                                      # nothing of the query


def test_engine_time_comes_from_the_http_answer(client, token):  # noqa: F811
    import httpx

    from mimirsynth import usage

    def answer(request):
        return httpx.Response(200, json={"usage": {"prompt_tokens": 7, "completion_tokens": 3}})
    with httpx.Client(transport=httpx.MockTransport(answer), event_hooks=usage.hooks("decision", "decisor-x")) as c:
        c.post("http://engine.test/v1/chat/completions", json={"messages": []})
    m = _scrape(client, token)
    assert _value(m["mimirsynth_ai_request_seconds"], "mimirsynth_ai_request_seconds_count", kind="decision", model="decisor-x") == 1


def test_what_is_stored_is_read_on_each_scrape(client, token):  # noqa: F811
    from datetime import timedelta

    from mimirsynth.models import (
        DocSource,
        Document,
        Job,
        Notification,
        NotifyChannel,
        NotifyDelivery,
        Proposal,
        User,
        now,
    )
    from mimirsynth.store import _factory
    bid = _brain(client, "metrics-b")
    with _factory()() as db:
        uid = db.query(User).first().id
        for status in ("pending", "pending", "rejected"):
            db.add(Proposal(brain_id=bid, author_id=uid, name="p", body="Ana García vive en Calle Falsa 1", status=status,
                            created_at=now() - timedelta(hours=2)))
        db.add(Job(brain_id=bid, kind="zz.waiting", status="queued", created_at=now() - timedelta(minutes=5)))
        src = DocSource(brain_id=bid, kind="upload", name="s")
        db.add(src); db.flush()
        db.add(Document(brain_id=bid, source_id=src.id, external_id="x", title="Nóminas de Ana", status="error"))
        db.add(Document(brain_id=bid, source_id=src.id, external_id="y", title="borrado", status="deleted"))
        ch = NotifyChannel(name="c", kind="ntfy", config={})
        n = Notification(event="job.failed", severity="warning", title="t")
        db.add_all([ch, n]); db.flush()
        db.add(NotifyDelivery(notification_id=n.id, channel_id=ch.id, kind="alert", status="failed"))
        db.commit()
    m = _scrape(client, token)
    props = m["mimirsynth_proposals"]
    assert _value(props, "mimirsynth_proposals", brain="metrics-b", status="pending") == 2
    assert _value(props, "mimirsynth_proposals", brain="metrics-b", status="rejected") == 1
    assert _value(m["mimirsynth_proposals_oldest_pending_seconds"], "mimirsynth_proposals_oldest_pending_seconds", brain="metrics-b") >= 7000
    assert _value(m["mimirsynth_jobs"], "mimirsynth_jobs", kind="zz.waiting", status="queued") == 1
    assert _value(m["mimirsynth_jobs_oldest_queued_seconds"], "mimirsynth_jobs_oldest_queued_seconds", kind="zz.waiting") >= 290
    docs = m["mimirsynth_documents"]
    assert _value(docs, "mimirsynth_documents", brain="metrics-b", status="error") == 1
    assert _value(docs, "mimirsynth_documents", brain="metrics-b", status="deleted") is None
    assert _value(m["mimirsynth_notify_deliveries"], "mimirsynth_notify_deliveries", status="failed") >= 1
    assert _value(m["mimirsynth_info"], "mimirsynth_info") == 1
    text = client.get("/metrics", headers=token).text
    assert "Ana" not in text and "Falsa" not in text and "Nóminas" not in text


def test_labels_are_a_closed_list(client, token, monkeypatch):  # noqa: F811
    """Every label of every metric is in metrics.LABELS (plus `le` of the histograms): a new one has to be added there on purpose."""
    from mimirsynth import metrics, usage
    _brain(client, "metrics-c")
    usage.record("llm", "m", 200, 1, 1)
    metrics.recall_done(0, {"total": 0.01}, "off")
    metrics.job_done("x", "done", 1.0)
    seen = set()
    for samples in _scrape(client, token).values():
        for s in samples:
            seen |= set(s.labels)
    assert seen - {"le"} <= metrics.LABELS, seen - metrics.LABELS
    assert {"brain", "kind", "model", "status"} <= seen


def test_a_metric_that_fails_does_not_break_what_it_measures(client, token, monkeypatch):  # noqa: F811
    from mimirsynth import metrics, usage
    monkeypatch.setattr(metrics, "_slug", lambda b: (_ for _ in ()).throw(RuntimeError("bd caída")))
    metrics.recall_done(1, {"total": 0.1}, "ok")                                                # no exception
    monkeypatch.setattr(metrics.AI_CALLS, "labels", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    usage.record("llm", "m", 200, 1, 1)                                                          # still counted for the AI usage

    def down():
        raise RuntimeError("PostgreSQL caído")
    monkeypatch.setattr(metrics, "_factory", lambda: down)
    r = client.get("/metrics", headers=token)
    assert r.status_code == 200 and "mimirsynth_info" in r.text and "caído" not in r.text


@needs_falkor
def test_graph_sizes(client, token, monkeypatch):  # noqa: F811
    from mimirsynth import db as dbm
    from mimirsynth import metrics
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.client.cache_clear()
    graph = "zz-test-metrics"
    c = dbm.client()
    if graph in c.list_graphs():
        c.select_graph(graph).delete()
    g = c.select_graph(graph)
    g.query("CREATE (a:Entity {uuid:'a'}), (b:Entity {uuid:'b'}), (:Episodic {uuid:'e'}),"
            " (a)-[:RELATES_TO {uuid:'r1'}]->(b), (a)-[:RELATES_TO {uuid:'r2', invalid_at:'2020-01-01'}]->(b)")
    client.post("/api/brains", json={"slug": graph, "name": graph})
    monkeypatch.setattr(metrics, "_GRAPH", (0.0, {}))
    try:
        m = _scrape(client, token)
        assert _value(m["mimirsynth_brain_entities"], "mimirsynth_brain_entities", brain=graph) == 2
        assert _value(m["mimirsynth_brain_episodes"], "mimirsynth_brain_episodes", brain=graph) == 1
        assert _value(m["mimirsynth_brain_facts"], "mimirsynth_brain_facts", brain=graph, state="current") == 1
        assert _value(m["mimirsynth_brain_facts"], "mimirsynth_brain_facts", brain=graph, state="invalidated") == 1
        g.query("CREATE (:Entity {uuid:'c'})")
        assert _value(_scrape(client, token)["mimirsynth_brain_entities"], "mimirsynth_brain_entities", brain=graph) == 2   # cached
    finally:
        g.delete()
