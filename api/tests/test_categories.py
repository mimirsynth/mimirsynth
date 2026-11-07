"""Curation by category (#299): pending proposals grouped by what produced them, a whole category decided after looking at a sample
(flagged secrets left out), and an auto-approval tier that only a measured precision earns, that approves the category's proposals
without a person and switches itself back to manual (and notifies) when its precision drops."""
from datetime import datetime, timedelta, timezone

import pytest

from test_control import client  # noqa: F401

from mimirsynth import categories as K


@pytest.fixture()
def brain(client, monkeypatch):  # noqa: F811
    from mimirsynth import ingest
    from mimirsynth.models import Brain, User
    from mimirsynth.store import _factory
    monkeypatch.setattr(ingest, "enabled", lambda: False)
    slug = f"ca{datetime.now().microsecond}"
    client.post("/api/brains", json={"slug": slug, "name": slug.upper()})
    with _factory()() as db:
        return slug, db.query(Brain).filter(Brain.slug == slug).one().id, db.query(User).first().id


def _add(bid, uid, n, category="curator.contradictions", status="pending", review_kind="", secret=False, verdict=""):
    from mimirsynth.models import Proposal
    from mimirsynth.store import _factory
    ids = []
    with _factory()() as db:
        for i in range(n):
            p = Proposal(brain_id=bid, author_id=uid, name=f"p{i}", body="b", status=status, category=category, review_kind=review_kind,
                         related_verdict=verdict, reviewed_at=datetime.now(timezone.utc) - timedelta(minutes=i) if review_kind else None,
                         secret_findings=[{"rule": "x", "start": 0, "end": 1, "action": "flagged"}] if secret else None)
            db.add(p)
            db.commit()
            ids.append(p.id)
    return ids


def test_the_queue_by_category_and_deciding_one_after_a_sample(client, brain):  # noqa: F811
    slug, bid, uid = brain
    _add(bid, uid, 3)
    _add(bid, uid, 1, secret=True)
    _add(bid, uid, 2, category="", verdict="duplicate")
    _add(bid, uid, 1, category="")
    items = {c["category"]: c for c in client.get(f"/api/brains/{slug}/review/categories").json()["items"]}
    assert {k: v["pending"] for k, v in items.items()} == {"curator.contradictions": 4, "duplicate": 2, "new": 1}
    cur = items["curator.contradictions"]
    assert cur["flagged"] == 1 and len(cur["sample"]) == 4 and cur["precision"]["precision"] is None
    url = f"/api/brains/{slug}/review/categories/curator.contradictions/decide"
    assert client.post(url, json={"verb": "approve", "seen": [999999]}).status_code == 409          # a sample of another category
    r = client.post(url, json={"verb": "approve", "seen": [cur["sample"][0]["id"]]}).json()
    assert len(r["done"]) == 3 and r["skipped"][0]["reason"] == "secret"
    pr = K.precision
    from mimirsynth.store import _factory
    with _factory()() as db:
        assert pr(db, bid, "curator.contradictions") == {"decided": 3, "approved": 3, "precision": 1.0}     # a person's decisions count


def test_a_tier_is_earned_works_and_falls_back(client, brain):  # noqa: F811
    from mimirsynth.models import Brain, Notification, Proposal
    from mimirsynth.store import _factory
    slug, bid, uid = brain
    url = f"/api/brains/{slug}/review/categories/verifier.refuted/auto"
    _add(bid, uid, 19, category="verifier.refuted", status="ingested", review_kind="human")
    r = client.put(url, json={"enabled": True, "bar": 0.95, "min": 20})
    assert r.status_code == 409 and "19" in r.json()["detail"]                                     # not enough decisions yet
    _add(bid, uid, 1, category="verifier.refuted", status="ingested", review_kind="human")
    assert client.put(url, json={"enabled": True, "bar": 0.95, "min": 20}).json()["auto"]["enabled"] is True
    waiting = _add(bid, uid, 2, category="verifier.refuted")
    flagged = _add(bid, uid, 1, category="verifier.refuted", secret=True)
    other = _add(bid, uid, 1, category="curator.contradictions")
    assert K.run_tiers() == 2
    with _factory()() as db:
        assert [db.get(Proposal, i).review_kind for i in waiting] == ["auto", "auto"]
        assert db.get(Proposal, flagged[0]).status == "pending" and db.get(Proposal, other[0]).status == "pending"
    with _factory()() as db:                                                                     # the automatic ones never count
        assert K.precision(db, bid, "verifier.refuted")["decided"] == 20
    _add(bid, uid, 3, category="verifier.refuted", status="rejected", review_kind="human")      # curators disagree: 20/23 < 0.95
    _add(bid, uid, 1, category="verifier.refuted")
    assert K.run_tiers() == 0
    with _factory()() as db:
        assert db.get(Brain, bid).auto_approve["verifier.refuted"]["enabled"] is False
        assert db.query(Notification).filter(Notification.event == "autoapprove.disabled", Notification.brain_id == bid).count() == 1
    assert client.put(url, json={"enabled": False}).status_code == 200                           # switching off is always possible


def test_tiers_are_for_administrators(client, brain):  # noqa: F811
    slug, _, _ = brain
    tok = client.post(f"/api/brains/{slug}/tokens", json={"name": "c", "role": "curator"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.put(f"/api/brains/{slug}/review/categories/new/auto", headers=h, json={"enabled": False}).status_code == 403
    assert client.get(f"/api/brains/{slug}/review/categories", headers=h).status_code == 200
