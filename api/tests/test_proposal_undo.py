"""Undoing a person's decision on a proposal: a rejection can be reopened; an approval waits UNDO_SECONDS queued before ingestion and can be
taken back until ingestion starts, never after."""
from sqlalchemy import select

from test_control import client  # noqa: F401


def _brain(client, slug):  # noqa: F811
    client.post("/api/brains", json={"slug": slug, "name": slug})
    mk = lambda role: {"Authorization": "Bearer " + client.post(f"/api/brains/{slug}/tokens", json={"name": role, "role": role}).json()["token"]}
    return mk("contributor"), mk("curator")


def _propose(client, slug, headers):  # noqa: F811
    r = client.post(f"/api/brains/{slug}/proposals", json={"name": "Dato", "body": "Nextcloud está en Helios"}, headers=headers)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    return r.json()["id"]


def _job(pid):
    from mimirsynth.models import Job
    from mimirsynth.store import _factory
    with _factory()() as db:
        return db.scalars(select(Job).where(Job.dedupe_key == f"proposal.ingest:{pid}").order_by(Job.id.desc())).first()


def test_rejection_can_be_reopened(client):  # noqa: F811
    contrib, curator = _brain(client, "undo-r")
    pid = _propose(client, "undo-r", contrib)
    url = f"/api/brains/undo-r/proposals/{pid}"
    assert client.post(f"{url}/reject", json={"note": "no aporta"}, headers=curator).json()["status"] == "rejected"
    assert client.post(f"{url}/undo", headers=contrib).status_code == 403  # only a curator takes a decision back
    r = client.post(f"{url}/undo", headers=curator)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "pending" and d["review_kind"] == "" and d["review_note"] == "" and d["reviewed_at"] is None
    assert client.post(f"{url}/undo", headers=curator).status_code == 409  # pending: nothing to undo
    events = [e["action"] for e in client.get("/api/audit").json()]
    assert "proposal.reopened" in events


def test_approval_waits_and_can_be_undone_until_ingestion_starts(client, monkeypatch):  # noqa: F811
    from mimirsynth import ingest, jobs, proposals
    from mimirsynth.models import Job
    from mimirsynth.store import _factory
    ran = []
    monkeypatch.setattr(ingest, "enabled", lambda: True)
    monkeypatch.setattr(ingest, "ingest_proposal", lambda pid, ctx: ran.append(pid))
    contrib, curator = _brain(client, "undo-a")
    pid = _propose(client, "undo-a", contrib)
    url = f"/api/brains/undo-a/proposals/{pid}"

    r = client.post(f"{url}/approve", json={}, headers=curator).json()
    assert r["status"] == "approved" and r["undo_seconds"] == proposals.UNDO_SECONDS
    first = _job(pid)
    assert first.status == "queued" and ran == []  # waits the grace period instead of starting at once

    r = client.post(f"{url}/undo", headers=curator)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert _job(pid).status == "cancelled"
    jobs._run(first.id)  # the timer firing afterwards finds it cancelled: nothing reaches the graph
    assert ran == []

    client.post(f"{url}/approve", json={}, headers=curator)
    second = _job(pid)
    assert second.id != first.id and second.status == "queued"
    with _factory()() as db:  # ingestion has started
        db.get(Job, second.id).status = "running"
        db.commit()
    r = client.post(f"{url}/undo", headers=curator)
    assert r.status_code == 409  # what reached the graph is corrected by invalidating facts, not by undoing
    assert _job(pid).status == "running"  # and the running ingestion is left alone
    assert client.get(url, headers=curator).json()["status"] == "approved"


def test_running_claim_beats_a_late_cancel(client):  # noqa: F811
    """jobs._run claims a job in one conditional update, so a job cancelled while it waited never starts."""
    from mimirsynth import jobs
    from mimirsynth.models import Job
    from mimirsynth.store import _factory
    ran = []

    @jobs.register("test.undo-claim", "prueba", limit=1, resume=False)
    def _fn(ctx, p):
        ran.append(p)
        return {}

    jid = jobs.submit("test.undo-claim", None, {"x": 1}, "prueba", delay=5)
    with _factory()() as db:
        assert db.get(Job, jid).status == "queued"
        db.get(Job, jid).status = "cancelled"
        db.commit()
    jobs._run(jid)
    assert ran == []
    jid = jobs.submit("test.undo-claim", None, {"x": 2}, "prueba", delay=5)
    jobs._run(jid)
    assert ran == [{"x": 2}]


def test_nothing_to_undo_once_ingested(client):  # noqa: F811
    from mimirsynth.models import Proposal
    from mimirsynth.store import _factory
    contrib, curator = _brain(client, "undo-i")
    pid = _propose(client, "undo-i", contrib)
    with _factory()() as db:
        db.get(Proposal, pid).status = "ingested"
        db.commit()
    assert client.post(f"/api/brains/undo-i/proposals/{pid}/undo", headers=curator).status_code == 409
