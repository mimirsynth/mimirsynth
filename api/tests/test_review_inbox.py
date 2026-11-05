"""The review inbox: the queue's risk order, the decided history, a person's own proposals and decisions on several at once."""
from test_control import client  # noqa: F401


def _brain(client, slug):  # noqa: F811
    client.post("/api/brains", json={"slug": slug, "name": slug})
    mk = lambda role: {"Authorization": "Bearer " + client.post(f"/api/brains/{slug}/tokens", json={"name": role, "role": role}).json()["token"]}
    return mk("contributor"), mk("curator")


def _propose(client, slug, headers, name, confidence=None):  # noqa: F811
    body = {"name": name, "body": f"{name}: texto"}
    if confidence is not None:
        body["confidence"] = confidence
    r = client.post(f"/api/brains/{slug}/proposals", json=body, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


def _set(pid, **values):
    from mimirsynth.models import Proposal
    from mimirsynth.store import _factory
    with _factory()() as db:
        p = db.get(Proposal, pid)
        for k, v in values.items():
            setattr(p, k, v)
        db.commit()


def test_risk_order_decided_and_mine(client):  # noqa: F811
    contrib, curator = _brain(client, "inbox-o")
    old = _propose(client, "inbox-o", contrib, "antigua", 0.9)
    low = _propose(client, "inbox-o", contrib, "poca confianza", 0.3)
    secret = _propose(client, "inbox-o", contrib, "con secreto", 0.9)
    fix = _propose(client, "inbox-o", contrib, "corrección", 0.9)
    newer = _propose(client, "inbox-o", contrib, "reciente", 0.95)
    _set(secret, secret_findings=[{"rule": "password", "start": 0, "end": 3, "action": "flagged"}])
    _set(fix, kind="correction")
    url = "/api/brains/inbox-o/proposals"

    ids = lambda **params: [p["id"] for p in client.get(url, params={"status": "pending", "limit": 50, **params}, headers=curator).json()["items"]]
    assert ids(sort="risk", order="asc") == [fix, secret, low, old, newer]  # risk groups first, oldest first inside a group
    assert ids(sort="risk", order="desc") == [newer, old, low, secret, fix]

    from mimirsynth.models import User
    from mimirsynth.store import _factory
    with _factory()() as db:  # tokens belong to whoever created them: give the contributor's proposals an author of their own
        other = User(email="otra@example.org", name="Otra")
        db.add(other)
        db.commit()
        other_id = other.id
    for pid in (old, low, secret, fix, newer):
        _set(pid, author_id=other_id)
    mine = _propose(client, "inbox-o", curator, "mía")  # a curator's own is approved on submission
    client.post(f"{url}/{old}/reject", json={}, headers=curator)
    decided = {p["id"] for p in client.get(url, params={"status": "decided"}, headers=curator).json()["items"]}
    assert decided == {old, mine}
    assert [p["id"] for p in client.get(url, params={"mine": True}, headers=curator).json()["items"]] == [mine]
    counts = client.get(f"{url}/counts", headers=curator).json()
    assert counts["decided"] == 2 and counts["pending"] == 4
    assert client.get(f"{url}/counts", params={"mine": True}, headers=curator).json()["all"] == 1
    assert client.get(url, params={"status": "bogus"}, headers=curator).status_code == 400


def test_bulk_decisions(client, monkeypatch):  # noqa: F811
    from mimirsynth import ingest, proposals
    monkeypatch.setattr(ingest, "enabled", lambda: True)
    monkeypatch.setattr(ingest, "ingest_proposal", lambda pid, ctx: None)
    contrib, curator = _brain(client, "inbox-b")
    a = _propose(client, "inbox-b", contrib, "a")
    b = _propose(client, "inbox-b", contrib, "b")
    secret = _propose(client, "inbox-b", contrib, "secreto")
    fix = _propose(client, "inbox-b", contrib, "corrección")
    _set(secret, secret_findings=[{"rule": "token", "start": 0, "end": 3, "action": "flagged"}])
    _set(fix, kind="correction")
    url = "/api/brains/inbox-b/proposals"

    assert client.post(f"{url}/bulk", json={"verb": "approve", "ids": [a]}, headers=contrib).status_code == 403
    assert client.post(f"{url}/bulk", json={"verb": "delete", "ids": [a]}, headers=curator).status_code == 422
    r = client.post(f"{url}/bulk", json={"verb": "approve", "ids": [a, b, secret, fix, a, 99999], "note": "lote"}, headers=curator).json()
    assert r["done"] == [a, b] and r["undo_seconds"] == proposals.UNDO_SECONDS
    assert {s["id"]: s["reason"] for s in r["skipped"]} == {secret: "secret", fix: "correction", 99999: "not_found"}
    got = client.get(f"{url}/{a}", headers=curator).json()
    assert got["status"] == "approved" and got["review_note"] == "lote" and got["review_kind"] == "human"

    r = client.post(f"{url}/bulk", json={"verb": "reject", "ids": [a, secret, fix]}, headers=curator).json()
    assert r["done"] == [secret, fix] and r["skipped"] == [{"id": a, "reason": "not_pending"}] and "undo_seconds" not in r
    for pid in (a, b):  # each approval in the batch can still be undone, as a single one
        assert client.post(f"{url}/{pid}/undo", headers=curator).json()["status"] == "pending"


def test_related_facts_for_the_reviewer(client, monkeypatch):  # noqa: F811
    from mimirsynth import ratings, recall
    calls, logged = [], []

    def fake_recall(brain_id, graph, query, n_facts, n_chunks, max_chars, n_docs=None, **kw):
        calls.append((query, n_facts, n_chunks, n_docs))
        return {"facts": [{"uuid": "f1", "fact": "nas01 is in room A", "name": "LOCATED_AT", "source": "nas01", "target": "Room A",
                           "valid_at": "2026-01-01T00:00:00Z", "invalid_at": None, "score": 0.8, "extra": "dropped"}]}
    monkeypatch.setattr(recall, "recall", fake_recall)
    monkeypatch.setattr(ratings, "log", lambda *a, **k: logged.append(a))
    contrib, curator = _brain(client, "inbox-rel")
    pid = _propose(client, "inbox-rel", contrib, "NAS movido")
    url = f"/api/brains/inbox-rel/proposals/{pid}/related"
    assert client.get(url, headers=contrib).status_code == 403  # a reviewer's read
    r = client.get(url, headers=curator).json()
    assert r["facts"] == [{"uuid": "f1", "fact": "nas01 is in room A", "name": "LOCATED_AT", "source": "nas01", "target": "Room A", "source_uuid": None,
                           "target_uuid": None, "valid_at": "2026-01-01T00:00:00Z", "invalid_at": None, "status": None, "score": 0.8}]
    assert calls[0][0].startswith("NAS movido") and calls[0][1:] == (5, 0, 0)  # facts only: no fragments, no documents
    assert logged == []  # not an agent's recall: nothing for the recall ratings
    _set(pid, purged_at=__import__("datetime").datetime.now())
    assert client.get(url, headers=curator).json() == {"facts": []}
