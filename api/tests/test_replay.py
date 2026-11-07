"""Replay sample (#291, first part): off by default, kept only when a brain administrator turns it on, every secret masked whatever the
brain's mode, the request's parameters and what it returned kept, bounded in number and age, and deleted when turned off."""
from datetime import datetime, timedelta, timezone

import pytest

from test_control import client  # noqa: F401
from test_mcp import rpc
from test_recall_ratings import OUT, _tok

from mimirsynth import replay
from mimirsynth.models import RecallSample
from mimirsynth.store import _factory

TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8J9k0" * 2  # shaped like a GitHub token, assembled so it is not literal in the code


@pytest.fixture()
def fake_recall(monkeypatch):
    from mimirsynth import mcp_server, memory
    monkeypatch.setattr(memory, "recall", lambda *a, **k: dict(OUT))
    monkeypatch.setattr(mcp_server, "recall", lambda *a, **k: dict(OUT))


def _samples(slug):
    from mimirsynth.models import Brain
    with _factory()() as db:
        bid = db.query(Brain).filter(Brain.slug == slug).one().id
        return db.query(RecallSample).filter(RecallSample.brain_id == bid).order_by(RecallSample.id).all()


def test_off_by_default_and_on_by_choice(client, fake_recall):  # noqa: F811
    client.post("/api/brains", json={"slug": "rp1", "name": "RP1"})
    client.post("/api/brains/rp1/recall", json={"query": "where does Nextcloud run?"})
    assert _samples("rp1") == [] and client.get("/api/brains/rp1/replay/settings").json() == {**replay.DEFAULT, "samples": 0}
    r = client.put("/api/brains/rp1/replay/settings", json={"enabled": True, "max": 10, "days": 7})
    assert r.json() == {"enabled": True, "max": 10, "days": 7, "samples": 0}
    client.post("/api/brains/rp1/recall", json={"query": f"deploy with {TOKEN} please", "facts": 3, "min_similarity": 0.6})
    s = _samples("rp1")[-1]
    assert TOKEN not in s.query and s.masked and s.via == "http"                                # always masked, whatever the mode
    assert s.params == {"facts": 3, "min_similarity": 0.6, "chunks": 4, "max_chars": 6000, "federated": True}
    assert s.items[:2] == [{"kind": "fact", "id": "f1"}, {"kind": "fact", "id": "f2"}] and len(s.items) == 4
    listed = client.get("/api/brains/rp1/replay/samples").json()["items"]
    assert listed[0]["query"] == s.query and listed[0]["items"] == 4


def test_mcp_and_the_limits(client, fake_recall):  # noqa: F811
    client.post("/api/brains", json={"slug": "rp2", "name": "RP2"})
    client.put("/api/brains/rp2/replay/settings", json={"enabled": True, "max": 10, "days": 7})
    tok = _tok(client, "rp2", "contributor")
    rpc(client, "rp2", "tools/call", {"name": "recall", "arguments": {"query": "via mcp"}}, token=tok)
    assert _samples("rp2")[-1].via == "mcp"
    for n in range(12):
        client.post("/api/brains/rp2/recall", json={"query": f"q{n}"})
    kept = _samples("rp2")
    assert len(kept) == 10 and kept[-1].query == "q11" and kept[0].query == "q2"             # the oldest went first
    with _factory()() as db:
        old = db.get(RecallSample, kept[0].id)
        old.created_at = datetime.now(timezone.utc) - timedelta(days=8)
        db.commit()
    assert replay.purge() >= 1 and len(_samples("rp2")) == 9                                  # past `days`
    assert client.put("/api/brains/rp2/replay/settings", json={"enabled": False}).json()["samples"] == 0   # off deletes them


def test_only_brain_administrators(client, fake_recall):  # noqa: F811
    client.post("/api/brains", json={"slug": "rp3", "name": "RP3"})
    tok = _tok(client, "rp3", "curator")
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/brains/rp3/replay/settings", headers=h).status_code == 403
    assert client.put("/api/brains/rp3/replay/settings", headers=h, json={"enabled": True}).status_code == 403
    assert client.get("/api/brains/rp3/replay/samples", headers=h).status_code == 403
    assert client.put("/api/brains/rp3/replay/settings", json={"enabled": True, "max": 5}).status_code == 422   # at least 10
