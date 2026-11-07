"""Ranking by source trust and decay by relation type (#298): the origin a client says can only lower what its token allows, a missing
origin is the lowest tier, a person's approval or a verified probe is the highest, the weighting and the decay are off by default and
change the order only when turned on (or simulated), and every fact says its tier."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from test_control import client  # noqa: F401

from mimirsynth import trust as T
from mimirsynth.config import settings


def test_the_token_caps_what_the_client_says():
    agent, hook = SimpleNamespace(max_trust="agent"), SimpleNamespace(max_trust="auto")
    assert T.effective_origin(None, None) == "person"                  # a person in the application
    assert T.effective_origin("agent", agent) == "agent"
    assert T.effective_origin(None, agent) == "auto"                   # saying nothing is the lowest tier
    assert T.effective_origin("agent", hook) == "auto"                 # the field never raises it above the token
    assert T.effective_origin("auto", agent) == "auto"                 # but can lower it
    assert T.proposal_tier("agent", "human") == "human" and T.proposal_tier("agent", "decider") == "agent"
    assert T.proposal_tier("", "decider") is None                     # before #298: no tier


def test_decay_goes_from_one_to_the_stale_weight():
    assert T.decay(0, 100, 0.6) == 1.0 and T.decay(50, 100, 0.6) == 0.8 and T.decay(100, 100, 0.6) == 0.6 and T.decay(400, 100, 0.6) == 0.6
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    facts = [{"uuid": "a", "name": "HAS_IP", "status": "current", "score": 0.9, "valid_at": (now - timedelta(days=90)).isoformat()},
             {"uuid": "b", "name": "HAS_IP", "status": "current", "score": 0.8, "valid_at": (now - timedelta(days=1)).isoformat()},
             {"uuid": "c", "name": "OWNED_BY", "status": "current", "score": 0.85, "valid_at": None}]
    lives = {"HAS_IP": 100}
    assert [f["uuid"] for f in T.apply_decay([dict(f) for f in facts], lives, {}, now=now)] == ["a", "b", "c"]   # off by default
    out = T.apply_decay([dict(f) for f in facts], lives, {}, on=True, now=now)
    assert [f["uuid"] for f in out] == ["c", "b", "a"] and out[2]["score"] == round(0.9 * T.decay(90, 100, 0.6), 4)
    confirmed = {"a": now - timedelta(days=2)}                          # confirmed two days ago: it counts from then
    assert T.apply_decay([dict(f) for f in facts], lives, confirmed, on=True, now=now)[0]["uuid"] == "a"


def _proposal(client, slug, token, origin):  # noqa: F811
    h = {"Authorization": f"Bearer {token}"}
    body = {"name": "x", "body": "y", **({"origin": origin} if origin else {})}
    return client.post(f"/api/brains/{slug}/proposals", headers=h, json=body).json()


def test_origin_is_recorded_and_capped_by_the_token(client, monkeypatch):  # noqa: F811
    from mimirsynth import ingest
    monkeypatch.setattr(ingest, "enabled", lambda: False)
    client.post("/api/brains", json={"slug": "tr1", "name": "TR1"})
    agent = client.post("/api/brains/tr1/tokens", json={"name": "a", "role": "contributor"}).json()
    hook = client.post("/api/brains/tr1/tokens", json={"name": "h", "role": "contributor", "max_trust": "auto"}).json()
    assert agent["max_trust"] == "agent" and hook["max_trust"] == "auto"
    assert _proposal(client, "tr1", agent["token"], "agent")["origin"] == "agent"
    assert _proposal(client, "tr1", agent["token"], None)["origin"] == "auto"
    assert _proposal(client, "tr1", hook["token"], "agent")["origin"] == "auto"
    assert client.post("/api/brains/tr1/proposals", json={"name": "x", "body": "y"}).json()["origin"] == "person"


def test_facts_say_their_tier_and_weigh_by_it_when_turned_on(client, monkeypatch):  # noqa: F811
    from mimirsynth.models import Brain, Proposal, User
    from mimirsynth.store import _factory
    client.post("/api/brains", json={"slug": "tr2", "name": "TR2"})
    with _factory()() as db:
        bid = db.query(Brain).filter(Brain.slug == "tr2").one().id
        uid = db.query(User).first().id
        for ep, origin, kind in (("e-auto", "auto", "decider"), ("e-agent", "agent", "decider"), ("e-human", "agent", "human"), ("e-old", "", "decider")):
            db.add(Proposal(brain_id=bid, author_id=uid, name=ep, body="b", status="ingested", episode_uuid=ep, origin=origin, review_kind=kind))
        db.commit()
    facts = lambda: [{"uuid": "1", "score": 0.9, "episodes": ["e-auto"]}, {"uuid": "2", "score": 0.88, "episodes": ["e-agent"]},  # noqa: E731
                     {"uuid": "3", "score": 0.86, "episodes": ["e-auto", "e-human"]}, {"uuid": "4", "score": 0.84, "episodes": ["e-old"]},
                     {"uuid": "5", "score": 0.8, "episodes": ["e-auto"], "verification": {"state": "verified"}}]
    out = T.mark(bid, facts())
    assert [f.get("trust") for f in out] == ["auto", "agent", "human", None, "verified"] and [f["uuid"] for f in out] == ["1", "2", "3", "4", "5"]
    out = T.mark(bid, facts(), trust=True)                              # simulated on: auto 0.85, agent 0.95
    assert [f["uuid"] for f in out] == ["3", "4", "2", "5", "1"] and out[-1]["score"] == round(0.9 * settings.recall_trust_auto, 4)
    monkeypatch.setattr(settings, "recall_trust", "yes")
    assert T.mark(bid, facts())[0]["uuid"] == "3"
