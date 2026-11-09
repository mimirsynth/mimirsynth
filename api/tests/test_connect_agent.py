"""The «Connect an agent» panel (#362): it watches one token until an agent makes its first authenticated call with it, then shows what a
recall with that token brings. Both read what every call already records (`api_tokens.last_used_at`, `recall_logs.token_id`); the test
recall is a preview and is never logged."""
from test_control import client  # noqa: F401
from test_onboarding import _admin, _as, _bearer, _done
from test_recall_ratings import fake_recall  # noqa: F401


def _new(client, slug, role="contributor", **kw):  # noqa: F811
    r = client.post(f"/api/brains/{slug}/tokens", json={"name": f"agente {role}", "role": role, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _activity(client, slug, tid):  # noqa: F811
    r = client.get(f"/api/brains/{slug}/tokens/{tid}/activity")
    assert r.status_code == 200, r.text
    return r.json()


def test_first_authenticated_call_is_seen_and_a_recall_is_counted(client, fake_recall):  # noqa: F811
    _admin()
    assert client.post("/api/brains", json={"slug": "con-a", "name": "Con A"}).status_code == 201
    tok = _new(client, "con-a")
    a = _activity(client, "con-a", tok["id"])
    assert a == {"id": tok["id"], "name": "agente contributor", "connected": False, "last_used_at": None, "recalls": 0, "last_recall_at": None}

    # any authenticated call counts as the first one: the plugins' `status` asks /whoami before anything else
    assert client.get("/api/brains/con-a/whoami", headers=_bearer(tok["token"])).status_code == 200
    a = _activity(client, "con-a", tok["id"])
    assert a["connected"] is True and a["last_used_at"] and a["recalls"] == 0

    seen = a["last_used_at"]
    assert client.post("/api/brains/con-a/recall", json={"query": "¿dónde corre?"}, headers=_bearer(tok["token"])).status_code == 200
    a = _activity(client, "con-a", tok["id"])
    assert a["recalls"] == 1 and a["last_recall_at"] and a["last_used_at"] >= seen
    assert "agent_recall" in _done(client)  # the same record ticks the getting-started checklist

    # a call over MCP is a call too
    other = _new(client, "con-a", "reader")
    mcp = client.post("/api/brains/con-a/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                      headers={**_bearer(other["token"]), "Accept": "application/json, text/event-stream"})
    assert mcp.status_code == 200, mcp.text
    assert _activity(client, "con-a", other["id"])["connected"] is True


def test_a_first_recall_over_mcp_in_an_empty_brain_counts(client, monkeypatch):  # noqa: F811
    """#421: the beginner's first recall lands in a new, empty brain and finds nothing; it still ticks the checklist and the wizard."""
    from mimirsynth import mcp_server
    from test_mcp import rpc
    monkeypatch.setattr(mcp_server, "recall", lambda *a, **k: {"facts": [], "chunks": [], "documents": [], "context": "", "chunks_state": "ok"})
    _admin()
    assert client.post("/api/brains", json={"slug": "con-empty", "name": "Con Empty"}).status_code == 201
    tok = _new(client, "con-empty")
    r = rpc(client, "con-empty", "tools/call", {"name": "recall", "arguments": {"query": "¿qué sabes de este proyecto?"}}, token=tok["token"],
            headers={"Accept": "application/json, text/event-stream"})
    assert r.status_code == 200, r.text
    assert "recall_id" not in r.text  # nothing to rate
    a = _activity(client, "con-empty", tok["id"])
    assert a["recalls"] == 1 and a["last_recall_at"]
    assert "agent_recall" in _done(client)


def test_a_failed_call_with_a_wrong_token_does_not_connect(client):  # noqa: F811
    _admin()
    assert client.post("/api/brains", json={"slug": "con-b", "name": "Con B"}).status_code == 201
    tok = _new(client, "con-b")
    assert client.get("/api/brains/con-b/whoami", headers=_bearer(tok["token"] + "x")).status_code == 401
    assert _activity(client, "con-b", tok["id"])["connected"] is False


def test_only_its_owner_or_an_admin_of_the_brain_watches_a_token(client):  # noqa: F811
    _admin()
    assert client.post("/api/brains", json={"slug": "con-c", "name": "Con C"}).status_code == 201
    for email, role in (("ana@con.test", "contributor"), ("bea@con.test", "contributor"), ("carla@con.test", "admin")):
        assert client.put("/api/brains/con-c/members", json={"email": email, "role": role}).status_code == 200
    _as("ana@con.test", "Ana")
    mine = _new(client, "con-c")
    assert _activity(client, "con-c", mine["id"])["connected"] is False
    _as("bea@con.test", "Bea")
    assert client.get(f"/api/brains/con-c/tokens/{mine['id']}/activity").status_code == 404
    assert client.post(f"/api/brains/con-c/tokens/{mine['id']}/test-recall", json={"query": "x"}).status_code == 404
    _as("carla@con.test", "Carla")
    assert client.get(f"/api/brains/con-c/tokens/{mine['id']}/activity").status_code == 200
    # another brain's path does not reach it
    _admin()
    assert client.post("/api/brains", json={"slug": "con-d", "name": "Con D"}).status_code == 201
    assert client.get(f"/api/brains/con-d/tokens/{mine['id']}/activity").status_code == 404
    # nor does an agent: tokens are managed from a session
    assert client.get(f"/api/brains/con-c/tokens/{mine['id']}/activity", headers=_bearer(mine["token"])).status_code == 403
    # a revoked token is gone
    _as("ana@con.test", "Ana")
    assert client.delete(f"/api/brains/con-c/tokens/{mine['id']}").status_code == 200
    assert client.get(f"/api/brains/con-c/tokens/{mine['id']}/activity").status_code == 404
    _admin()


def test_the_test_recall_uses_the_tokens_scopes_and_is_not_logged(client, monkeypatch):  # noqa: F811
    from mimirsynth import memory
    from mimirsynth.models import RecallLog
    from mimirsynth.store import _factory
    calls = []
    monkeypatch.setattr(memory, "recall", lambda *a, **k: calls.append((a, k)) or {"context": "## Hechos\n- algo", "facts": [{"fact": "algo"}], "chunks": [], "documents": []})
    _admin()
    assert client.post("/api/brains", json={"slug": "con-e", "name": "Con E"}).status_code == 201
    full = _new(client, "con-e")
    no_docs = _new(client, "con-e", scopes=["recall"])
    write_only = _new(client, "con-e", scopes=["propose"])
    with _factory()() as db:
        before = db.query(RecallLog).count()

    r = client.post(f"/api/brains/con-e/tokens/{full['id']}/test-recall", json={"query": "¿qué sabes?"})
    assert r.status_code == 200 and r.json()["facts"] == [{"fact": "algo"}]
    assert calls[-1][0][2] == "¿qué sabes?" and calls[-1][1]["n_docs"] is None  # the instance's passages
    assert client.post(f"/api/brains/con-e/tokens/{no_docs['id']}/test-recall", json={"query": "x"}).status_code == 200
    assert calls[-1][1]["n_docs"] == 0  # without the documents scope, no passages, as the agent would get
    r = client.post(f"/api/brains/con-e/tokens/{write_only['id']}/test-recall", json={"query": "x"})
    assert r.status_code == 403 and "recall" in r.json()["detail"]
    assert client.post(f"/api/brains/con-e/tokens/{full['id']}/test-recall", json={"query": ""}).status_code == 422

    with _factory()() as db:
        assert db.query(RecallLog).count() == before  # a preview: neither the agent's recall nor a question in Ask
    assert _activity(client, "con-e", full["id"])["connected"] is False  # and it does not count as the agent's call
