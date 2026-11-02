"""Periodic summary (#128): a person subscribes per brain, daily or weekly, at their hour and zone; the email has counts and links,
never text of the memories; a brain with nothing new and the same waiting counters is left out, and an email with nothing is not sent."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from test_control import client  # noqa: F401

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
UTC = timezone.utc


@pytest.fixture()
def outbox(monkeypatch):
    from mimirsynth import digest
    sent = []
    monkeypatch.setattr(digest.mail, "configured", lambda: True)
    monkeypatch.setattr(digest.mail, "send", lambda to, subject, body: sent.append({"to": to, "subject": subject, "body": body}))
    real = digest.appsettings.get
    monkeypatch.setattr(digest.appsettings, "get", lambda k: "https://memory.example.com/" if k == "public_url" else real(k))
    monkeypatch.setattr(digest, "_graph_counts", lambda brain, since: {"facts_new": 0, "facts_gone": 0})
    monkeypatch.setattr("mimirsynth.attention._conflicts", lambda ctx: 0)
    monkeypatch.setattr("mimirsynth.attention._stale", lambda ctx: 0)
    return sent


def _person(email: str, slug: str, role: str, frequency: str = "daily", last: datetime | None = None, **prefs) -> tuple[int, int]:
    """A person with `role` in a new brain `slug`, subscribed to it; returns (user id, brain id)."""
    from mimirsynth.models import Brain, DigestSubscription, Membership, User
    from mimirsynth.store import _factory
    with _factory()() as db:
        b = Brain(slug=slug, name=slug.upper(), graph_name=slug)
        u = User(email=email, name=email.split("@")[0], status="active", **prefs)
        db.add_all([b, u]); db.flush()
        db.add(Membership(user_id=u.id, brain_id=b.id, role=role))
        db.add(DigestSubscription(user_id=u.id, brain_id=b.id, frequency=frequency, last_sent_at=last))
        db.commit()
        return u.id, b.id


def _pending(bid: int, n: int, days_old: int = 0, kind: str = "memory") -> None:
    from mimirsynth.models import Proposal, User
    from mimirsynth.store import _factory
    with _factory()() as db:
        uid = db.query(User).first().id
        for _ in range(n):
            db.add(Proposal(brain_id=bid, author_id=uid, name="p", body="Ana García vive en la Calle Falsa 1", kind=kind, status="pending",
                            created_at=datetime.now(UTC) - timedelta(days=days_old)))
        db.commit()


def _mine(sent, email):
    return [m for m in sent if m["to"] == email]


def test_last_slot_follows_the_person_hour_day_and_zone():
    from mimirsynth.digest import last_slot
    from mimirsynth.models import User
    u = User(digest_hour=8, digest_weekday=0, timezone="Europe/Madrid")      # 08:00 in Madrid = 07:00 UTC in November
    at = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)                             # a Wednesday
    assert last_slot(at, u, "daily") == datetime(2026, 11, 4, 7, 0, tzinfo=UTC)
    assert last_slot(datetime(2026, 11, 4, 6, 59, tzinfo=UTC), u, "daily") == datetime(2026, 11, 3, 7, 0, tzinfo=UTC)
    assert last_slot(at, u, "weekly") == datetime(2026, 11, 2, 7, 0, tzinfo=UTC)          # Monday
    assert last_slot(datetime(2026, 11, 2, 6, 0, tzinfo=UTC), u, "weekly") == datetime(2026, 10, 26, 7, 0, tzinfo=UTC)
    assert last_slot(at, User(digest_hour=8, digest_weekday=0, timezone=""), "daily") == datetime(2026, 11, 4, 8, 0, tzinfo=UTC)
    assert last_slot(at, User(digest_hour=8, digest_weekday=0, timezone="Mars/Olympus"), "daily").hour == 8   # unknown zone: UTC


def test_a_due_summary_has_counts_and_links_never_memory_text(client, outbox):  # noqa: F811
    from mimirsynth import digest
    from mimirsynth.models import DigestSubscription
    from mimirsynth.store import _factory
    at = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
    uid, bid = _person("cur-dg1@example.com", "dg1", "curator", last=at - timedelta(days=2))
    _pending(bid, 3, days_old=4)
    _pending(bid, 1, kind="correction")
    digest.run_due(at)
    [m] = _mine(outbox, "cur-dg1@example.com")
    assert "DG1" in m["body"] and "Propuestas por revisar: 3 (la más antigua, de hace 4 días)" in m["body"]
    assert "Correcciones por revisar: 1" in m["body"]
    assert "https://memory.example.com/propuestas?brain=dg1" in m["body"] and "resumen: https://memory.example.com/cuenta?seccion=resumen\n" in m["body"]
    assert "Ana" not in m["body"] and "Falsa" not in m["body"] and "Ana" not in m["subject"]
    with _factory()() as db:
        sub = db.query(DigestSubscription).filter_by(user_id=uid).one()
        assert sub.last_counts["proposals"] == 3 and sub.last_sent_at is not None
    digest.run_due(at + timedelta(hours=1))                                    # already sent for this slot
    assert len(_mine(outbox, "cur-dg1@example.com")) == 1


def test_nothing_new_nothing_sent(client, outbox, monkeypatch):  # noqa: F811
    from mimirsynth import digest
    from mimirsynth.models import DigestSubscription
    from mimirsynth.store import _factory
    at = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
    uid, bid = _person("cur-dg2@example.com", "dg2", "curator", last=at - timedelta(days=1, hours=2))
    digest.run_due(at)                                                         # an empty brain: no email
    assert _mine(outbox, "cur-dg2@example.com") == []
    with _factory()() as db:
        assert db.query(DigestSubscription).filter_by(user_id=uid).one().last_sent_at is not None   # but the slot is done
    _pending(bid, 2)
    digest.run_due(at + timedelta(days=1))
    assert len(_mine(outbox, "cur-dg2@example.com")) == 1
    digest.run_due(at + timedelta(days=2))                                     # the same two still waiting: already told
    assert len(_mine(outbox, "cur-dg2@example.com")) == 1
    monkeypatch.setattr(digest, "_graph_counts", lambda brain, since: {"facts_new": 5, "facts_gone": 1})
    digest.run_due(at + timedelta(days=3))                                     # something new in the period
    last = _mine(outbox, "cur-dg2@example.com")[-1]["body"]
    assert len(_mine(outbox, "cur-dg2@example.com")) == 2 and "Hechos nuevos: 5 · invalidados: 1" in last
    assert "https://memory.example.com/hechos?brain=dg2" in last


def test_a_reader_sees_what_changed_but_not_what_waits_for_curators(client, outbox, monkeypatch):  # noqa: F811
    from mimirsynth import digest
    at = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
    _, bid = _person("reader-dg3@example.com", "dg3", "reader", last=at - timedelta(days=2))
    _pending(bid, 4)
    digest.run_due(at)
    assert _mine(outbox, "reader-dg3@example.com") == []                      # proposals are not news for a reader
    monkeypatch.setattr(digest, "_graph_counts", lambda brain, since: {"facts_new": 2, "facts_gone": 0})
    digest.run_due(at + timedelta(days=1))
    [m] = _mine(outbox, "reader-dg3@example.com")
    assert "Hechos nuevos: 2" in m["body"] and "Propuestas" not in m["body"]


def test_weekly_at_the_person_weekday_and_one_email_for_several_brains(client, outbox, monkeypatch):  # noqa: F811
    from mimirsynth import digest
    from mimirsynth.models import Brain, DigestSubscription, Membership
    from mimirsynth.store import _factory
    monkeypatch.setattr(digest, "_graph_counts", lambda brain, since: {"facts_new": 1, "facts_gone": 0})
    wed = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
    uid, _ = _person("weekly-dg4@example.com", "dg4", "reader", frequency="weekly", last=wed - timedelta(days=1), digest_weekday=4, digest_hour=8)
    with _factory()() as db:
        b = Brain(slug="dg4b", name="DG4B", graph_name="dg4b")
        db.add(b); db.flush()
        db.add(Membership(user_id=uid, brain_id=b.id, role="reader"))
        db.add(DigestSubscription(user_id=uid, brain_id=b.id, frequency="weekly", last_sent_at=wed - timedelta(days=1)))
        db.commit()
    digest.run_due(wed)                                                        # it is Wednesday: Friday's has not come
    assert _mine(outbox, "weekly-dg4@example.com") == []
    digest.run_due(wed + timedelta(days=2))                                    # Friday 09:00
    [m] = _mine(outbox, "weekly-dg4@example.com")
    assert "## DG4\n" in m["body"] and "## DG4B\n" in m["body"]


def test_lost_access_removes_the_subscription_and_no_email_waits(client, outbox):  # noqa: F811
    from mimirsynth import digest
    from mimirsynth.models import DigestSubscription, Membership
    from mimirsynth.store import _factory
    at = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
    uid, bid = _person("gone-dg5@example.com", "dg5", "curator", last=at - timedelta(days=2))
    _pending(bid, 1)
    with _factory()() as db:
        db.query(Membership).filter_by(user_id=uid).delete()
        db.commit()
    digest.run_due(at)
    assert _mine(outbox, "gone-dg5@example.com") == []
    with _factory()() as db:
        assert db.query(DigestSubscription).filter_by(user_id=uid).count() == 0


def test_a_failed_email_is_tried_again(client, outbox, monkeypatch):  # noqa: F811
    from mimirsynth import digest
    at = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
    _, bid = _person("smtp-dg6@example.com", "dg6", "curator", last=at - timedelta(days=2))
    _pending(bid, 1)
    real = digest.mail.send

    def down(to, subject, body):
        if to == "smtp-dg6@example.com":
            raise ConnectionError("smtp caído")
        real(to, subject, body)
    monkeypatch.setattr(digest.mail, "send", down)
    digest.run_due(at)
    monkeypatch.setattr(digest.mail, "send", real)
    digest.run_due(at + timedelta(minutes=10))
    assert len(_mine(outbox, "smtp-dg6@example.com")) == 1


def test_without_email_nothing_is_sent(client, outbox, monkeypatch):  # noqa: F811
    from mimirsynth import digest
    at = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
    _, bid = _person("off-dg7@example.com", "dg7", "curator", last=at - timedelta(days=2))
    _pending(bid, 1)
    monkeypatch.setattr(digest.mail, "configured", lambda: False)
    assert digest.run_due(at) == 0 and _mine(outbox, "off-dg7@example.com") == []


def test_english_summary(client, outbox):  # noqa: F811
    from mimirsynth import digest
    at = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
    _, bid = _person("en-dg8@example.com", "dg8", "curator", last=at - timedelta(days=2), locale="en")
    _pending(bid, 2)
    digest.run_due(at)
    [m] = _mine(outbox, "en-dg8@example.com")
    assert "Proposals to review: 2" in m["body"] and "Propuestas" not in m["body"] and "brains" in m["subject"]


def test_my_account_settings_and_preview(client, outbox):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "dg9", "name": "DG9"}).status_code == 201
    d = client.get("/api/me/digest").json()
    assert d["mail"] is True and d["hour"] == 8 and d["weekday"] == 0
    assert next(b for b in d["brains"] if b["slug"] == "dg9")["frequency"] == "never"
    assert client.get("/api/me/digest/preview").status_code == 409                        # nothing subscribed
    r = client.put("/api/me/digest", json={"hour": 7, "weekday": 4, "timezone": "Europe/Madrid", "brains": {"dg9": "weekly"}})
    assert r.status_code == 200
    d = r.json()
    assert (d["hour"], d["weekday"], d["timezone"]) == (7, 4, "Europe/Madrid")
    assert next(b for b in d["brains"] if b["slug"] == "dg9")["frequency"] == "weekly"
    p = client.get("/api/me/digest/preview").json()
    assert "DG9" in p["body"] and p["subject"]
    assert client.put("/api/me/digest", json={"timezone": "Mars/Olympus"}).status_code == 422
    assert client.put("/api/me/digest", json={"brains": {"dg9": "hourly"}}).status_code == 422
    assert client.put("/api/me/digest", json={"brains": {"no-such-brain": "daily"}}).status_code == 404
    assert client.put("/api/me/digest", json={"hour": 24}).status_code == 422
    d = client.put("/api/me/digest", json={"hour": 7, "weekday": 4, "timezone": "Europe/Madrid", "brains": {"dg9": "never"}}).json()
    assert next(b for b in d["brains"] if b["slug"] == "dg9")["frequency"] == "never"


@needs_falkor
def test_graph_counts_of_the_period(client, monkeypatch):  # noqa: F811
    from mimirsynth import db as dbm
    from mimirsynth import digest
    from mimirsynth.config import settings
    from mimirsynth.models import Brain
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.client.cache_clear()
    name = "zz-test-digest"
    c = dbm.client()
    if name in c.list_graphs():
        c.select_graph(name).delete()
    g = c.select_graph(name)
    old, new = "2026-10-01T10:00:00.000000Z", "2026-11-03T10:00:00.000000Z"
    g.query("CREATE (a:Entity {uuid:'a'}), (b:Entity {uuid:'b'}),"
            " (a)-[:RELATES_TO {uuid:'r1', created_at:$old}]->(b),"
            " (a)-[:RELATES_TO {uuid:'r2', created_at:$new}]->(b),"
            " (a)-[:RELATES_TO {uuid:'r3', created_at:$old, invalid_at:$new, expired_at:$new}]->(b)", {"old": old, "new": new})
    try:
        n = digest._graph_counts(Brain(graph_name=name), datetime(2026, 11, 1, tzinfo=UTC))
        assert n == {"facts_new": 1, "facts_gone": 1}
    finally:
        g.delete()


def test_what_changed_for_the_overview(client, monkeypatch):  # noqa: F811
    from mimirsynth import digest
    from mimirsynth.deps import current_user
    from mimirsynth.main import app
    from mimirsynth.models import Brain, Document, DocSource, Membership, Proposal, User
    from mimirsynth.store import _factory
    seen = []
    monkeypatch.setattr(digest, "_graph_counts", lambda brain, since: seen.append(since) or {"facts_new": 4, "facts_gone": 2})
    assert client.post("/api/brains", json={"slug": "dg10", "name": "DG10"}).status_code == 201
    old = datetime.now(UTC) - timedelta(days=10)
    with _factory()() as db:
        bid = db.query(Brain).filter_by(slug="dg10").one().id
        uid = db.query(User).first().id
        db.add_all([Proposal(brain_id=bid, author_id=uid, name="p", body="x", status="pending"),
                    Proposal(brain_id=bid, author_id=uid, name="p", body="x", status="approved", reviewed_at=datetime.now(UTC)),
                    Proposal(brain_id=bid, author_id=uid, name="p", body="x", status="rejected", created_at=old, reviewed_at=old)])
        src = DocSource(brain_id=bid, kind="upload", name="s")
        db.add(src); db.flush()
        db.add_all([Document(brain_id=bid, source_id=src.id, external_id="a", status="active"),
                    Document(brain_id=bid, source_id=src.id, external_id="b", status="active", first_seen_at=old)])
        reader = User(email="reader-dg10@example.com", name="r", status="active")
        db.add(reader); db.flush()
        db.add(Membership(user_id=reader.id, brain_id=bid, role="reader"))
        db.commit()
        rid = reader.id
    d = client.get("/api/brains/dg10/changes").json()
    assert (d["days"], d["facts_new"], d["facts_gone"], d["docs_new"]) == (7, 4, 2, 1)
    assert (d["proposals_new"], d["proposals_decided"]) == (2, 1)
    assert abs((datetime.now(UTC) - seen[-1]).total_seconds() - 7 * 86400) < 60
    assert client.get("/api/brains/dg10/changes", params={"days": 31}).json()["proposals_new"] == 3
    assert client.get("/api/brains/dg10/changes", params={"days": 32}).status_code == 422
    app.dependency_overrides[current_user] = lambda: _factory()().get(User, rid)
    try:
        assert client.get("/api/brains/dg10/changes").status_code == 403                  # curators and above
    finally:
        app.dependency_overrides.pop(current_user)
