"""The getting-started checklist (#363): each step ticks itself from what happens in the person's brains (an agent's recall, its proposal,
an approval, a document, a question in Ask, a second agent or person), stays ticked once seen, and the card goes for good when it is
complete or closed."""
from test_control import client  # noqa: F401
from test_recall_ratings import fake_recall  # noqa: F401

from mimirsynth.deps import current_user
from mimirsynth.main import app


def _as(email: str, name: str):
    """Acts as this person, an active account (added as a member, they would still be invited: their tokens would not work)."""
    from mimirsynth.models import User
    with _db() as db:
        u = db.query(User).filter(User.email == email).one_or_none() or User(email=email, name=name)
        u.status = "active"
        db.add(u); db.commit(); db.refresh(u)
        db.expunge(u)
    app.dependency_overrides[current_user] = lambda: u
    return u


def _admin():
    """Back to the local administrator of the test instance; with no override, a bearer token is read as its owner again."""
    app.dependency_overrides.pop(current_user, None)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _done(client) -> set[str]:  # noqa: F811
    return {s["key"] for s in client.get("/api/onboarding").json()["steps"] if s["done"]}


def _token(client, slug, role) -> str:  # noqa: F811
    r = client.post(f"/api/brains/{slug}/tokens", json={"name": f"agente {role}", "role": role})
    assert r.status_code in (200, 201), r.text
    return r.json()["token"]


def _db():
    from mimirsynth.store import _factory
    return _factory()()


def _bid(slug: str) -> int:
    from mimirsynth.models import Brain
    with _db() as db:
        return db.query(Brain).filter(Brain.slug == slug).one().id


def test_each_step_ticks_itself_when_it_happens_and_stays(client, fake_recall):  # noqa: F811
    from mimirsynth.models import ApiToken, DocSource, Document, RecallLog
    _admin()
    assert client.post("/api/brains", json={"slug": "onb-a", "name": "Onb A"}).status_code == 201
    assert client.put("/api/brains/onb-a/members", json={"email": "olga@onb.test", "role": "admin"}).status_code == 200
    _as("olga@onb.test", "Olga")
    r = client.get("/api/onboarding").json()
    assert [s["key"] for s in r["steps"]] == ["agent_recall", "proposal_received", "proposal_approved", "document", "ask", "second"]
    assert r["done"] == 0 and r["total"] == 6 and r["show"] is True and r["dismissed"] is False
    assert all(s["done_at"] is None for s in r["steps"])
    agent = _token(client, "onb-a", "contributor")  # one agent: not yet a second one
    assert _done(client) == set()

    assert client.post("/api/brains/onb-a/recall", json={"query": "¿dónde corre?"}).status_code == 200  # Ask, from a session
    assert _done(client) == {"ask"}

    _admin()
    assert client.post("/api/brains/onb-a/recall", json={"query": "contexto"}, headers=_bearer(agent)).status_code == 200
    with _db() as db:
        assert db.query(RecallLog).filter(RecallLog.brain_id == _bid("onb-a"), RecallLog.token_id.is_not(None)).count() == 1
    r = client.post("/api/brains/onb-a/proposals", json={"name": "web", "body": "web corre en notus"}, headers=_bearer(agent))
    assert r.status_code == 201 and r.json()["status"] == "pending"
    pid = r.json()["id"]
    _as("olga@onb.test", "Olga")
    assert _done(client) == {"ask", "agent_recall", "proposal_received"}

    assert client.post(f"/api/brains/onb-a/proposals/{pid}/approve", json={}).status_code == 200
    assert _done(client) == {"ask", "agent_recall", "proposal_received", "proposal_approved"}

    with _db() as db:  # the uploads source alone is not a document yet; a document in it is
        src = DocSource(brain_id=_bid("onb-a"), kind="upload", name="Subidas")
        db.add(src); db.commit()
        src_id = src.id
    assert "document" not in _done(client)
    with _db() as db:
        db.add(Document(brain_id=_bid("onb-a"), source_id=src_id, external_id="manual.pdf", title="Manual"))
        db.commit()
    assert "document" in _done(client)

    _token(client, "onb-a", "reader")  # a second agent
    r = client.get("/api/onboarding").json()
    assert r["done"] == 6 and r["show"] is False and r["dismissed"] is False and all(s["done_at"] for s in r["steps"])

    with _db() as db:  # what showed the steps goes (retention, revoked tokens): they stay ticked
        db.query(RecallLog).filter(RecallLog.brain_id == _bid("onb-a")).delete()
        db.query(ApiToken).filter(ApiToken.brain_id == _bid("onb-a")).update({"revoked": True})
        db.commit()
    assert client.get("/api/onboarding").json()["done"] == 6
    _admin()


def test_only_the_persons_brains_and_questions_count_and_closing_is_for_good(client, fake_recall):  # noqa: F811
    _admin()
    for slug in ("onb-b", "onb-c"):
        assert client.post("/api/brains", json={"slug": slug, "name": slug}).status_code == 201
    client.put("/api/brains/onb-b/members", json={"email": "pia@onb.test", "role": "curator"})
    client.put("/api/brains/onb-b/members", json={"email": "quim@onb.test", "role": "reader"})
    outsider = _token(client, "onb-c", "contributor")  # an agent in a brain Pía does not belong to
    client.post("/api/brains/onb-c/recall", json={"query": "x"}, headers=_bearer(outsider))
    client.post("/api/brains/onb-c/proposals", json={"name": "a", "body": "b"}, headers=_bearer(outsider))

    _as("pia@onb.test", "Pía")
    assert _done(client) == {"second"}  # two people in onb-b
    r = client.post("/api/brains/onb-b/proposals", json={"name": "mía", "body": "la propongo yo"})
    assert r.status_code == 201 and r.json()["status"] == "approved"  # a curator's own, approved as sent: neither received nor reviewed
    assert _done(client) == {"second"}

    _as("quim@onb.test", "Quim")
    assert client.post("/api/brains/onb-b/recall", json={"query": "pregunta de Quim"}).status_code == 200
    assert "ask" in _done(client)
    _as("pia@onb.test", "Pía")
    assert _done(client) == {"second"}  # Quim's question is his

    r = client.post("/api/onboarding/dismiss").json()
    assert r["dismissed"] is True and r["show"] is False and r["done"] == 1
    client.post("/api/brains/onb-b/recall", json={"query": "ahora pregunto yo"})
    r = client.get("/api/onboarding").json()
    assert r["dismissed"] is True and r["show"] is False and r["done"] == 1  # closed: nothing more is looked up, nothing brings it back
    assert client.post("/api/onboarding/dismiss").json()["dismissed"] is True
    _admin()


def test_an_instance_administrator_counts_every_brain(client, fake_recall):  # noqa: F811
    from mimirsynth.models import User
    _admin()
    assert client.post("/api/brains", json={"slug": "onb-d", "name": "onb-d"}).status_code == 201
    agent = _token(client, "onb-d", "reader")
    client.post("/api/brains/onb-d/recall", json={"query": "x"}, headers=_bearer(agent))
    admin = _as("ines@onb.test", "Inés")
    with _db() as db:
        db.query(User).filter(User.id == admin.id).update({"is_admin": True})
        db.commit()
    admin.is_admin = True
    done = _done(client)
    assert "agent_recall" in done and "ask" not in done  # a brain they are not a member of; no question of their own
    _admin()
