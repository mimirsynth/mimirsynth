"""AI consumption per brain (#132): every call to an engine is counted for the brain and purpose it was made for, with its tokens,
its 429/5xx errors and its pace; prices give an estimated cost; a budget warns at 80 % and 100 % and can pause the brain's ingestion
without losing proposals."""
import asyncio
import json

import httpx
import pytest

from test_control import client  # noqa: F401


def _bid(slug: str) -> int:
    from mimirsynth.models import Brain
    from mimirsynth.store import _factory
    with _factory()() as db:
        return db.query(Brain).filter(Brain.slug == slug).one().id


def _rows(brain_id: int) -> list:
    from mimirsynth.models import AiUsage
    from mimirsynth.store import _factory
    with _factory()() as db:
        return [{c.key: getattr(r, c.key) for c in AiUsage.__table__.columns} for r in db.query(AiUsage).filter(AiUsage.brain_id == brain_id)]


def _answer(status: int, usage: dict | None = None):
    def handler(request):
        if status != 200:
            return httpx.Response(status, json={"error": "x"})
        return httpx.Response(200, json={"data": [{"embedding": [0.1], "index": 0}], **({"usage": usage} if usage else {})})
    return httpx.MockTransport(handler)


def test_each_call_counts_for_its_brain_and_purpose(client):  # noqa: F811
    from mimirsynth import usage
    assert client.post("/api/brains", json={"slug": "au1", "name": "Au1"}).status_code == 201
    bid = _bid("au1")
    with usage.scope(bid, "recall"):
        with httpx.Client(transport=_answer(200, {"prompt_tokens": 12, "total_tokens": 12}), event_hooks=usage.hooks("embedding", "m-emb")) as c:
            c.post("http://e/embeddings", json={"input": ["hola"]})
            c.post("http://e/embeddings", json={"input": ["adiós"]})
        with httpx.Client(transport=_answer(200), event_hooks=usage.hooks("embedding", "m-emb")) as c:  # no `usage`: estimated
            c.post("http://e/embeddings", content=b"x" * 40)
        for status in (429, 503, 400):
            with httpx.Client(transport=_answer(status), event_hooks=usage.hooks("embedding", "m-emb")) as c:
                c.post("http://e/embeddings", json={})
    with usage.scope(bid, "documents"):
        with httpx.Client(transport=_answer(200, {"input_tokens": 5, "output_tokens": 0}), event_hooks=usage.hooks("embedding", "m-emb")) as c:
            c.post("http://e/embeddings", json={})
    rows = {r["purpose"]: r for r in _rows(bid)}
    rec = rows["recall"]
    assert (rec["calls"], rec["prompt_tokens"], rec["estimated_calls"]) == (6, 24 + 10, 1)
    assert (rec["errors_429"], rec["errors_5xx"], rec["errors_other"]) == (1, 1, 1) and rec["peak_rpm"] >= 6
    assert rows["documents"]["prompt_tokens"] == 5 and rows["documents"]["kind"] == "embedding" and rows["documents"]["model"] == "m-emb"
    assert usage.live_rpm()["embedding:m-emb"] >= 7


def test_the_async_client_of_the_extraction_counts_too(client):  # noqa: F811
    from mimirsynth import usage
    assert client.post("/api/brains", json={"slug": "au2", "name": "Au2"}).status_code == 201
    bid = _bid("au2")

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 100, "completion_tokens": 20}})

    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), event_hooks=usage.async_hooks("llm", "m-llm")) as c:
            await c.post("http://l/chat/completions", json={})
    with usage.scope(bid, "extraction"):
        asyncio.run(call())                                                   # the context reaches the event loop, as in ingestion
    [r] = _rows(bid)
    assert (r["kind"], r["purpose"], r["prompt_tokens"], r["completion_tokens"]) == ("llm", "extraction", 100, 20)


def test_the_decider_is_counted(client, monkeypatch):  # noqa: F811
    from mimirsynth import decider, usage
    assert client.post("/api/brains", json={"slug": "au3", "name": "Au3"}).status_code == 201
    bid = _bid("au3")
    body = {"choices": [{"message": {"content": "A"}, "logprobs": {"content": [{"top_logprobs": [{"token": "A", "logprob": 0.0}]}]}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 1}}
    monkeypatch.setattr(httpx, "post", lambda url, **k: httpx.Response(200, json=body, request=httpx.Request("POST", url, json=k.get("json"))))
    with usage.scope(bid, "decider"):
        assert decider.decide("http://d", "m-dec", "", "estado", "¿?", ["Sí", "No"])["letter"] == "A"
    [r] = _rows(bid)
    assert (r["kind"], r["model"], r["purpose"], r["prompt_tokens"], r["completion_tokens"]) == ("decision", "m-dec", "decider", 50, 1)


def test_prices_budget_warnings_and_pause(client, monkeypatch):  # noqa: F811
    from mimirsynth import ingest, usage
    from mimirsynth.models import Audit, Notification, Proposal, User
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "au4", "name": "Au4"}).status_code == 201
    bid = _bid("au4")
    usage.record("llm", "m-pay", 200, 600_000, 100_000, brain_id=bid, purpose="extraction")
    usage.record("embedding", "m-free", 200, 400_000, 0, brain_id=bid, purpose="recall")
    assert client.put("/api/ai-usage/prices", json={"kind": "llm", "model": "m-pay", "price_in": 2.0, "price_out": 10.0}).status_code == 200
    out = client.get("/api/brains/au4/ai-usage", params={"days": 7}).json()
    pay = next(r for r in out["rows"] if r["model"] == "m-pay")
    assert pay["cost"] == pytest.approx(0.6 * 2 + 0.1 * 10) and pay["priced"]
    assert not next(r for r in out["rows"] if r["model"] == "m-free")["priced"] and len(out["series"]) == 7
    # a budget in tokens: 1.1M used of 1.25M is 88 %: warns once at 80 %
    r = client.put("/api/brains/au4/ai-budget", json={"limit": 1_250_000, "unit": "tokens", "pause": True})
    assert r.status_code == 200 and r.json()["pct"] == 88.0 and not r.json()["paused"]
    usage._check_budget(bid, force=True)
    with _factory()() as db:
        keys = {n.key for n in db.query(Notification).filter(Notification.event == "ai.budget")}
        assert any(k.endswith(":80") for k in keys) and not any(k.endswith(":100") for k in keys)
        assert db.query(Audit).filter(Audit.action == "brain.ai_budget").count() == 1
    # spent: it warns at 100 % and the brain's ingestion waits, without losing the proposal
    usage.record("llm", "m-pay", 200, 200_000, 0, brain_id=bid, purpose="extraction")
    assert usage.paused(bid)
    with _factory()() as db:
        assert any(n.key.endswith(":100") and n.severity == "critical" for n in db.query(Notification).filter(Notification.event == "ai.budget"))
        p = Proposal(brain_id=bid, author_id=db.query(User).first().id, name="n", body="b", status="approved")
        db.add(p)
        db.commit()
        pid = p.id
    monkeypatch.setattr(ingest, "add_episode", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe ingerir")))
    assert ingest.ingest_proposal(pid) == ""
    with _factory()() as db:
        p = db.get(Proposal, pid)
        assert p.status == "approved" and p.ingest_error == usage.PAUSED
    queued = []
    monkeypatch.setattr(ingest, "submit_ingest", lambda pid, bid, name, uid=None: queued.append(pid))
    assert usage.resume() == 0 and queued == []                                     # still spent
    client.put("/api/brains/au4/ai-budget", json={"limit": 5_000_000, "unit": "tokens", "pause": True})
    assert usage.resume() == 1 and queued == [pid]                                  # raised: it goes on by itself
    with _factory()() as db:
        assert db.get(Proposal, pid).ingest_error == ""
    # in cost, with a model without a price, the status says which ones are not counted
    st = client.put("/api/brains/au4/ai-budget", json={"limit": 100.0, "unit": "cost", "pause": False}).json()
    assert st["unit"] == "cost" and st["used"] == pytest.approx(0.6 * 2 + 0.1 * 10 + 0.2 * 2) and st["unpriced"] == ["embedding:m-free"]
    assert client.put("/api/brains/au4/ai-budget", json={"limit": None}).json()["limit"] is None


def test_who_sees_the_consumption(client):  # noqa: F811
    from mimirsynth import usage
    from mimirsynth.deps import current_user
    from mimirsynth.main import app
    from mimirsynth.models import Brain, Membership, User
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "au5", "name": "Au5"}).status_code == 201
    usage.record("llm", "m-x", 429, brain_id=_bid("au5"), purpose="extraction")
    inst = client.get("/api/ai-usage").json()
    assert any(b["slug"] == "au5" and b["errors_429"] == 1 for b in inst["brains"])
    eng = next(e for e in inst["engines"] if e["model"] == "m-x")
    assert eng["errors_429"] >= 1 and eng["rpm_now"] >= 1
    with _factory()() as db:
        u = User(email="cur-au5@example.com", name="Cur", status="active")
        db.add(u)
        db.flush()
        db.add(Membership(user_id=u.id, brain_id=db.query(Brain).filter(Brain.slug == "au5").one().id, role="curator"))
        db.commit()
        uid = u.id
    app.dependency_overrides[current_user] = lambda: _factory()().get(User, uid)
    try:
        assert client.get("/api/brains/au5/ai-usage").status_code == 403
        assert client.get("/api/ai-usage").status_code == 403
        assert client.put("/api/ai-usage/prices", json={"kind": "llm", "model": "m", "price_in": 1}).status_code == 403
    finally:
        app.dependency_overrides.pop(current_user)
    assert json.dumps(inst)                                                         # serializable as is
