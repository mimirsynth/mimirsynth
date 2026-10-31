"""Ratings of the recall (#110): every recall gives a short-lived `recall_id`, each item can be rated useful, irrelevant or incorrect over
HTTP and MCP, «incorrect» on a fact opens a correction only from a contributor, the query is kept as a hash unless the brain chooses
otherwise, and the quality view counts per kind and similarity range next to the total of recalls."""
from datetime import datetime, timedelta, timezone

import pytest

from test_control import client  # noqa: F401
from test_mcp import rpc

OUT = {"facts": [{"uuid": "f1", "fact": "Nextcloud corre en Notus", "score": 0.83, "status": "current"},
                 {"uuid": "f2", "fact": "Polaris está en el rack 4", "score": 0.52, "status": "current", "origin": "otro"}],
       "chunks": [{"id": 7, "text": "Migramos Nextcloud a Notus en junio", "score": 0.71}],
       "documents": [{"document_id": 3, "chunk_idx": 1, "text": "Notus: rack 2, IP 10.0.0.9", "similarity": 0.68}],
       "context": "## Hechos\n- Nextcloud corre en Notus", "chunks_state": "ok"}


@pytest.fixture()
def fake_recall(monkeypatch):
    from mimirsynth import mcp_server, memory
    monkeypatch.setattr(memory, "recall", lambda *a, **k: dict(OUT))
    monkeypatch.setattr(mcp_server, "recall", lambda *a, **k: dict(OUT))


def _tok(client, slug, role):  # noqa: F811
    return client.post(f"/api/brains/{slug}/tokens", json={"name": role, "role": role}).json()["token"]


def _log(rid):
    from mimirsynth.models import RecallLog
    from mimirsynth.store import _factory
    with _factory()() as db:
        return db.query(RecallLog).filter(RecallLog.rid == rid).one()


def test_rate_each_item_and_incorrect_opens_a_correction_only_from_a_contributor(client, fake_recall, monkeypatch):  # noqa: F811
    from mimirsynth import corrections
    from mimirsynth.models import RecallRating
    from mimirsynth.store import _factory
    made = []
    monkeypatch.setattr(corrections, "create", lambda ctx, req, body, direct=True: made.append((body.fact_uuid, body.reason, direct))
                        or type("P", (), {"id": 900 + len(made)})())
    assert client.post("/api/brains", json={"slug": "rr1", "name": "Rr1"}).status_code == 201
    out = client.post("/api/brains/rr1/recall", json={"query": "¿Dónde corre Nextcloud?"}).json()
    rid = out["recall_id"]
    assert len(rid) >= 12 and out["facts"][0]["uuid"] == "f1"
    lg = _log(rid)
    assert lg.query_text is None and lg.query_len == len("¿Dónde corre Nextcloud?") and len(lg.query_hash) == 64     # only a hash by default
    base = f"/api/brains/rr1/recall/{rid}/ratings"
    assert client.post(base, json={"kind": "doc", "id": ":3:1", "rating": "useful"}).json()["ok"]
    assert client.post(base, json={"kind": "chunk", "id": ":7", "rating": "irrelevant"}).status_code == 200
    r = client.post(base, json={"kind": "fact", "id": "f1", "rating": "incorrect", "note": "ya está en Polaris"}).json()
    assert r["proposal_id"] == 901 and made == [("f1", "Valorado como incorrecto al consultar la memoria: ya está en Polaris", False)]
    client.post(base, json={"kind": "fact", "id": "f1", "rating": "incorrect"})                  # again: no second correction
    assert len(made) == 1
    r = client.post(base, json={"kind": "fact", "id": "f2", "rating": "incorrect"}).json()       # lent: it belongs to another brain
    assert r["proposal_id"] is None and len(made) == 1
    assert client.post(base, json={"kind": "fact", "id": "nope", "rating": "useful"}).status_code == 404
    assert client.post(base, json={"kind": "fact", "id": "f1", "rating": "great"}).status_code == 422
    assert client.post("/api/brains/rr1/recall/xxxxxxxxxxxx/ratings", json={"kind": "fact", "id": "f1", "rating": "useful"}).status_code == 404
    # a reader: recorded, never a correction
    reader = _tok(client, "rr1", "reader")
    rid2 = client.post("/api/brains/rr1/recall", json={"query": "otra"}, headers={"Authorization": f"Bearer {reader}"}).json()["recall_id"]
    r = client.post(f"/api/brains/rr1/recall/{rid2}/ratings", json={"kind": "fact", "id": "f1", "rating": "incorrect"},
                    headers={"Authorization": f"Bearer {reader}"}).json()
    assert r["recorded_only"] is True and r["proposal_id"] is None and len(made) == 1
    with _factory()() as db:
        rows = {(x.kind, x.item_id, x.rating) for x in db.query(RecallRating)}
    assert {("doc", ":3:1", "useful"), ("chunk", ":7", "irrelevant"), ("fact", "f1", "incorrect"), ("fact", "f2", "incorrect")} <= rows


def test_a_recall_id_expires_and_ratings_have_a_limit(client, fake_recall, monkeypatch):  # noqa: F811
    from mimirsynth import ratings
    from mimirsynth.models import RecallLog
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "rr2", "name": "Rr2"}).status_code == 201
    rid = client.post("/api/brains/rr2/recall", json={"query": "q"}).json()["recall_id"]
    with _factory()() as db:
        db.query(RecallLog).filter(RecallLog.rid == rid).update({"created_at": datetime.now(timezone.utc) - timedelta(hours=ratings.RATE_HOURS + 1)})
        db.commit()
    assert client.post(f"/api/brains/rr2/recall/{rid}/ratings", json={"kind": "fact", "id": "f1", "rating": "useful"}).status_code == 404
    monkeypatch.setattr(ratings, "LIMIT", (1, 60.0))
    from mimirsynth import ratelimit
    ratelimit.reset()
    rid = client.post("/api/brains/rr2/recall", json={"query": "q"}).json()["recall_id"]
    assert client.post(f"/api/brains/rr2/recall/{rid}/ratings", json={"kind": "fact", "id": "f1", "rating": "useful"}).status_code == 200
    assert client.post(f"/api/brains/rr2/recall/{rid}/ratings", json={"kind": "doc", "id": ":3:1", "rating": "useful"}).status_code == 429
    ratelimit.reset()


def test_mcp_gives_the_recall_id_and_rates_by_the_text_the_agent_saw(client, fake_recall):  # noqa: F811
    from mimirsynth.models import RecallRating
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "rr3", "name": "Rr3"}).status_code == 201
    tok = _tok(client, "rr3", "reader")
    text = rpc(client, "rr3", "tools/call", {"name": "recall", "arguments": {"query": "Nextcloud"}}, token=tok).json()["result"]["content"][0]["text"]
    rid = text.rsplit("recall_id: ", 1)[1].rstrip(")")
    r = rpc(client, "rr3", "tools/call", {"name": "rate", "arguments": {"recall_id": rid, "rating": "useful", "fact": "Nextcloud corre en Notus"}}, token=tok)
    assert not r.json()["result"]["isError"] and "guardada" in r.json()["result"]["content"][0]["text"]
    r = rpc(client, "rr3", "tools/call", {"name": "rate", "arguments": {"recall_id": rid, "rating": "irrelevant", "document": 3, "chunk": 1}}, token=tok)
    assert not r.json()["result"]["isError"]
    r = rpc(client, "rr3", "tools/call", {"name": "rate", "arguments": {"recall_id": rid, "rating": "useful", "fact": "algo que no salió"}}, token=tok)
    assert r.json()["result"]["isError"]
    from mimirsynth.models import Brain
    with _factory()() as db:
        bid = db.query(Brain).filter(Brain.slug == "rr3").one().id
        assert {(x.kind, x.item_id, x.rating) for x in db.query(RecallRating).filter(RecallRating.brain_id == bid)} == {("fact", "f1", "useful"), ("doc", ":3:1", "irrelevant")}
    nore = client.post("/api/brains/rr3/tokens", json={"name": "w", "role": "contributor", "scopes": ["propose"]}).json()["token"]
    assert client.post(f"/api/brains/rr3/recall/{rid}/ratings", json={"kind": "fact", "id": "f1", "rating": "useful"},
                       headers={"Authorization": f"Bearer {nore}"}).status_code == 403                # rating needs the recall scope


def test_quality_view_query_text_and_purge(client, fake_recall):  # noqa: F811
    from mimirsynth import ratings, retention
    from mimirsynth.models import Brain, RecallLog, RecallRating
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "rr4", "name": "Rr4"}).status_code == 201
    rids = [client.post("/api/brains/rr4/recall", json={"query": f"q{i}"}).json()["recall_id"] for i in range(4)]
    for rid, (kind, item, rating) in zip(rids, [("doc", ":3:1", "useful"), ("doc", ":3:1", "irrelevant"), ("fact", "f1", "useful")]):
        client.post(f"/api/brains/rr4/recall/{rid}/ratings", json={"kind": kind, "id": item, "rating": rating})
    q = client.get("/api/brains/rr4/recall/quality").json()
    assert q["recalls"] == 4 and q["rated_recalls"] == 3 and q["ratings"] == 3                    # the total next to the ratings
    assert q["by_kind"]["doc"] == {"useful": 1, "irrelevant": 1, "incorrect": 0} and q["by_kind"]["fact"]["useful"] == 1
    assert q["buckets"]["doc"] == [{"range": "0.6–0.7", "useful": 1, "irrelevant": 1, "incorrect": 0}]
    assert q["keep_query_text"] is False
    # keeping the query text, and turning it off again drops it
    assert client.put("/api/brains/rr4/recall/settings", json={"keep_query_text": True}).json()["keep_query_text"] is True
    rid = client.post("/api/brains/rr4/recall", json={"query": "texto que se guarda"}).json()["recall_id"]
    assert _log(rid).query_text == "texto que se guarda"
    client.put("/api/brains/rr4/recall/settings", json={"keep_query_text": False})
    assert _log(rid).query_text is None
    # purge: an unrated log once it can no longer be rated; ratings by the brain's retention period
    with _factory()() as db:
        bid = db.query(Brain).filter(Brain.slug == "rr4").one().id
        db.query(RecallLog).filter(RecallLog.brain_id == bid).update({"created_at": datetime.now(timezone.utc) - timedelta(days=3)})
        db.query(RecallRating).filter(RecallRating.brain_id == bid).update({"created_at": datetime.now(timezone.utc) - timedelta(days=3)})
        db.commit()
    assert ratings.purge()["logs"] >= 2
    with _factory()() as db:
        assert db.query(RecallLog).filter(RecallLog.brain_id == bid).count() == 3                    # the three rated ones stay
    client.put("/api/brains/rr4/retention", json={"ratings_days": 1})
    assert retention.purge(bid)["ratings"] == 3
    with _factory()() as db:
        assert db.query(RecallLog).filter(RecallLog.brain_id == bid).count() == 0
