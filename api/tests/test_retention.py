"""Retention periods per brain (#137): nothing is purged without a period, a period purges what is older than it on the next run, the
instance's period applies when the brain has none, and every change is audited and only for the owner."""
from datetime import datetime, timedelta, timezone

from test_control import client  # noqa: F401


def _seed(slug: str) -> dict:
    """Rejected proposals and finished jobs of several ages."""
    from mimirsynth.models import Brain, Job, Proposal, User
    from mimirsynth.store import _factory
    now = datetime.now(timezone.utc)
    with _factory()() as db:
        b = db.query(Brain).filter(Brain.slug == slug).one()
        u = db.query(User).first()
        ids = {}
        for key, status, days in (("old", "rejected", 40), ("recent", "rejected", 10), ("pending", "pending", 400), ("approved", "ingested", 400)):
            p = Proposal(brain_id=b.id, author_id=u.id, name=f"{key} name", body=f"{key} body with something private", status=status,
                         source_description="src", review_note="no", decision={"reason": "dice algo"}, reviewed_at=now - timedelta(days=days))
            db.add(p)
            db.flush()
            ids[key] = p.id
        for key, status, days in (("job_old", "done", 20), ("job_recent", "failed", 5), ("job_running", "running", 50)):
            j = Job(brain_id=b.id, kind="doc.scan", title=key, status=status, finished_at=now - timedelta(days=days) if status != "running" else None,
                    created_at=now - timedelta(days=days))
            db.add(j)
            db.flush()
            ids[key] = j.id
        db.commit()
        return ids


def test_without_a_period_nothing_is_purged(client):  # noqa: F811
    from mimirsynth import retention
    from mimirsynth.models import Brain
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "rt1", "name": "Rt1"}).status_code == 201
    _seed("rt1")
    r = client.get("/api/brains/rt1/retention").json()
    assert r["rejected_days"] is None and r["jobs_days"] is None and r["effective"] == {"rejected_days": 0, "jobs_days": 0, "ratings_days": 0}
    assert client.post("/api/brains/rt1/retention/run").status_code == 409
    with _factory()() as db:
        bid = db.query(Brain).filter(Brain.slug == "rt1").one().id
    assert retention.purge(bid) == {"proposals": 0, "jobs": 0, "ratings": 0, "rejected_days": 0, "jobs_days": 0, "ratings_days": 0}


def test_a_period_purges_what_is_older_and_is_audited(client):  # noqa: F811
    from mimirsynth.models import Audit, Job, Proposal
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "rt2", "name": "Rt2"}).status_code == 201
    ids = _seed("rt2")
    r = client.put("/api/brains/rt2/retention", json={"rejected_days": 30, "jobs_days": 10})
    assert r.status_code == 200 and r.json()["effective"] == {"rejected_days": 30, "jobs_days": 10, "ratings_days": 0}
    assert client.put("/api/brains/rt2/retention", json={"rejected_days": -1}).status_code == 422
    assert client.post("/api/brains/rt2/retention/run").status_code == 202
    last = client.get("/api/brains/rt2/retention").json()["last_run"]
    assert last["status"] == "done" and last["result"]["proposals"] == 1 and last["result"]["jobs"] == 1
    with _factory()() as db:
        old, recent, pending, approved = (db.get(Proposal, ids[k]) for k in ("old", "recent", "pending", "approved"))
        assert old.purged_at and (old.name, old.body, old.source_description, old.review_note, old.decision) == ("", "", "", "", None)
        assert old.status == "rejected" and old.author_id and old.reviewed_at                 # the row and its dates stay
        assert recent.body.startswith("recent") and not recent.purged_at
        assert pending.body.startswith("pending") and approved.body.startswith("approved")    # only rejected proposals
        assert db.get(Job, ids["job_old"]) is None and db.get(Job, ids["job_recent"]) and db.get(Job, ids["job_running"])
        a = db.query(Audit).filter(Audit.action == "brain.retention", Audit.brain_id == old.brain_id).one()
        assert a.detail == {"rejected_days": {"from": None, "to": 30}, "jobs_days": {"from": None, "to": 10}}
    d = client.get(f"/api/brains/rt2/proposals/{ids['old']}").json()
    assert d["purged_at"] and d["body"] == ""
    # the same values again change nothing and are not audited twice
    client.put("/api/brains/rt2/retention", json={"rejected_days": 30, "jobs_days": 10})
    with _factory()() as db:
        assert db.query(Audit).filter(Audit.action == "brain.retention", Audit.brain_id == db.get(Proposal, ids["old"]).brain_id).count() == 1


def test_the_instance_period_applies_unless_the_brain_sets_its_own(client, monkeypatch):  # noqa: F811
    from mimirsynth import jobs, retention
    from mimirsynth.config import settings
    from mimirsynth.models import Brain, Job, Proposal
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "rt3", "name": "Rt3"}).status_code == 201
    assert client.post("/api/brains", json={"slug": "rt4", "name": "Rt4"}).status_code == 201
    a, b = _seed("rt3"), _seed("rt4")
    monkeypatch.setattr(settings, "retention_rejected_days", 5)
    client.put("/api/brains/rt4/retention", json={"rejected_days": 0})              # 0 in the brain: no period, whatever the instance says
    r = client.get("/api/brains/rt3/retention").json()
    assert r["defaults"]["rejected_days"] == 5 and r["effective"]["rejected_days"] == 5
    monkeypatch.setattr(jobs, "submit", lambda kind, brain_id, *a, **k: brain_id)
    with _factory()() as db:
        want = {db.query(Brain).filter(Brain.slug == "rt3").one().id}
        rt4 = db.query(Brain).filter(Brain.slug == "rt4").one().id
    started = set(retention.run_all())
    assert want <= started and rt4 not in started
    for bid in want:
        retention.purge(bid)
    retention.purge(rt4)
    with _factory()() as db:
        assert db.get(Proposal, a["old"]).purged_at and db.get(Proposal, a["recent"]).purged_at   # both older than 5 days
        assert not db.get(Proposal, b["old"]).purged_at
        assert db.get(Job, a["job_old"])                                                         # jobs: still no period


def test_only_the_owner_sets_the_periods(client):  # noqa: F811
    from mimirsynth.deps import current_user
    from mimirsynth.main import app
    from mimirsynth.models import Brain, Membership, User
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "rt5", "name": "Rt5"}).status_code == 201
    with _factory()() as db:
        u = User(email="admin-rt5@example.com", name="Adm", status="active")
        db.add(u)
        db.flush()
        db.add(Membership(user_id=u.id, brain_id=db.query(Brain).filter(Brain.slug == "rt5").one().id, role="admin"))
        db.commit()
        uid = u.id
    app.dependency_overrides[current_user] = lambda: _factory()().get(User, uid)
    try:
        assert client.get("/api/brains/rt5/retention").status_code == 403
        assert client.put("/api/brains/rt5/retention", json={"jobs_days": 1}).status_code == 403
    finally:
        app.dependency_overrides.pop(current_user)
