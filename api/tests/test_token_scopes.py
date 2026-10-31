"""API tokens with expiry, fine scope and rotation (#133): old tokens keep working, an expired one says so, a token without
`documents` gets no passages over REST, MCP or federation, rotation keeps both working during the grace period, and the instance can
cap the life of new tokens."""
import importlib.util
import io
import json
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from test_control import client  # noqa: F401
from test_mcp import rpc

HOOK = Path(__file__).resolve().parents[2] / "integrations" / "claude-code" / "mimirsynth_recall.py"


def _tok(client, slug, **body):  # noqa: F811
    r = client.post(f"/api/brains/{slug}/tokens", json={"name": "t", "role": "contributor", **body})
    assert r.status_code == 201, r.text
    return r.json()


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def _set(token_id: int, **cols) -> None:
    from mimirsynth.models import ApiToken
    from mimirsynth.store import _factory
    with _factory()() as db:
        t = db.get(ApiToken, token_id)
        for k, v in cols.items():
            setattr(t, k, v)
        db.commit()


@pytest.fixture()
def spy(monkeypatch):
    """What the recall was asked for, without a graph or an index behind it."""
    from mimirsynth import mcp_server, memory
    seen = []

    def fake(brain_id, graph_name, query, *a, n_docs=None, sources=None, **k):
        seen.append({"n_docs": n_docs, "sources": [s.slug for s in sources or []]})
        return {"context": "ctx", "facts": [], "chunks": [], "documents": []}
    monkeypatch.setattr(memory, "recall", fake)
    monkeypatch.setattr(mcp_server, "recall", fake)
    return seen


def test_existing_tokens_keep_working_and_a_new_one_shows_its_scope(client, spy):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "tk1", "name": "Tk1"}).status_code == 201
    old = _tok(client, "tk1")                                                   # as before: no scope and no expiry
    assert old["all_scopes"] and old["scopes"] == ["recall", "documents", "propose"] and old["expires_at"] is None
    assert client.post("/api/brains/tk1/recall", json={"query": "algo"}, headers=_h(old["token"])).status_code == 200
    assert spy[-1]["n_docs"] is None                                            # the instance's default number of passages
    new = _tok(client, "tk1", scopes=["recall", "propose"], days=30)
    assert new["scopes"] == ["recall", "propose"] and not new["all_scopes"]
    exp = datetime.fromisoformat(new["expires_at"])
    assert timedelta(days=29) < exp - datetime.now(timezone.utc) <= timedelta(days=30)
    same = _tok(client, "tk1", scopes=["propose", "documents", "recall"])          # all three is the same as none listed
    assert same["all_scopes"]
    assert client.post("/api/brains/tk1/tokens", json={"name": "x", "scopes": ["admin"]}).status_code == 400
    assert client.post("/api/brains/tk1/tokens", json={"name": "x", "scopes": []}).status_code == 400
    listed = {t["id"]: t for t in client.get("/api/brains/tk1/tokens").json()}
    assert listed[new["id"]]["mine"] and listed[old["id"]]["expires_at"] is None
    mine = {t["id"]: t for t in client.get("/api/me/tokens").json()}
    assert mine[new["id"]]["scopes"] == ["recall", "propose"] and mine[new["id"]]["brain_slug"] == "tk1"


def test_an_expired_token_answers_401_saying_so(client, spy):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "tk2", "name": "Tk2"}).status_code == 201
    t = _tok(client, "tk2", days=30)
    _set(t["id"], expires_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    r = client.post("/api/brains/tk2/recall", json={"query": "algo"}, headers=_h(t["token"]))
    assert r.status_code == 401 and "token caducado el 2026-01-02" in r.json()["detail"]
    r = client.post("/api/brains/tk2/recall", json={"query": "algo"}, headers={**_h(t["token"]), "Accept-Language": "en"})
    assert r.status_code == 401 and "token expired on 2026-01-02" in r.json()["detail"]
    assert rpc(client, "tk2", "tools/list", token=t["token"]).status_code == 401
    assert client.get("/api/brains/tk2/tokens").json()[0]["expired"] is True


def test_without_documents_no_passages_over_rest_mcp_or_federation(client, spy, monkeypatch):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "tk3", "name": "Tk3"}).status_code == 201
    assert client.post("/api/brains", json={"slug": "tk3l", "name": "Lent"}).status_code == 201
    assert client.post("/api/brains/tk3l/grants", json={"target": "tk3", "scope": "both"}).status_code == 201
    full, nodocs = _tok(client, "tk3")["token"], _tok(client, "tk3", scopes=["recall", "propose"])["token"]
    # REST
    assert client.post("/api/brains/tk3/recall", json={"query": "algo", "docs": 3}, headers=_h(full)).status_code == 200
    assert spy[-1] == {"n_docs": 3, "sources": ["tk3l"]}
    assert client.post("/api/brains/tk3/recall", json={"query": "algo", "docs": 3}, headers=_h(nodocs)).status_code == 200
    assert spy[-1] == {"n_docs": 0, "sources": ["tk3l"]}                        # the lent graph still comes, its documents do not
    for path in ("/docs", "/docs/search?q=rack", "/docs/1/text", "/docs/mentions?entity=x"):
        r = client.get(f"/api/brains/tk3{path}", headers=_h(nodocs))
        assert r.status_code == 403 and "documents" in r.json()["detail"], path
    assert client.get("/api/brains/tk3/docs", headers=_h(full)).status_code == 200
    # MCP
    tools = [t["name"] for t in rpc(client, "tk3", "tools/list", token=nodocs).json()["result"]["tools"]]
    assert "get_document" not in tools and "recall" in tools and "remember" in tools
    r = rpc(client, "tk3", "tools/call", {"name": "get_document", "arguments": {"document": 1}}, token=nodocs).json()["result"]
    assert r["isError"] and "documents" in r["content"][0]["text"]
    rpc(client, "tk3", "tools/call", {"name": "recall", "arguments": {"query": "algo"}}, token=nodocs)
    assert spy[-1]["n_docs"] == 0
    rpc(client, "tk3", "tools/call", {"name": "recall", "arguments": {"query": "algo"}}, token=full)
    assert spy[-1]["n_docs"] is None
    # federation: with no passages asked for, not even the lent brain's documents are searched
    from mimirsynth import recall as R
    called = []
    monkeypatch.setattr(R, "search_documents", lambda *a, **k: called.append(1) or ([], "ok"))
    monkeypatch.setattr(R, "search_facts", lambda *a, **k: [])
    monkeypatch.setattr(R, "_federated_graph", lambda *a, **k: ([], []))
    emb = type("E", (), {"embed": lambda self, t: [[0.1] * 4 for _ in t]})()
    out = R.recall(1, "zz-none", "q", 2, 0, 2000, embedder=emb, n_docs=0, sources=[R.Source(2, "g", "tk3l", "Lent", "both")])
    assert called == [] and out["documents"] == []


def test_without_propose_or_recall(client, spy):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "tk4", "name": "Tk4"}).status_code == 201
    read = _tok(client, "tk4", scopes=["recall"])["token"]
    write = _tok(client, "tk4", scopes=["propose"])["token"]
    prop = {"name": "n", "body": "Polaris está en el rack 4"}
    r = client.post("/api/brains/tk4/proposals", json=prop, headers=_h(read))
    assert r.status_code == 403 and "propose" in r.json()["detail"]
    r = rpc(client, "tk4", "tools/call", {"name": "remember", "arguments": prop}, token=read).json()["result"]
    assert r["isError"] and "propose" in r["content"][0]["text"]
    assert client.post("/api/brains/tk4/proposals", json=prop, headers=_h(write)).status_code == 201
    assert client.post("/api/brains/tk4/recall", json={"query": "algo"}, headers=_h(write)).status_code == 403
    assert client.get("/api/brains/tk4/facts", headers=_h(write)).status_code == 403
    assert [t["name"] for t in rpc(client, "tk4", "tools/list", token=write).json()["result"]["tools"]] == ["remember", "correct"]


def test_a_token_cannot_manage_tokens(client):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "tk5", "name": "Tk5"}).status_code == 201
    t = _tok(client, "tk5", days=7)
    for method, path, body in (("POST", "/tokens", {"name": "otro"}), ("GET", "/tokens", None), ("POST", f"/tokens/{t['id']}/rotate", {})):
        r = client.request(method, f"/api/brains/tk5{path}", json=body, headers=_h(t["token"]))
        assert r.status_code == 403 and "sesión" in r.json()["detail"], path


def test_rotation_keeps_both_during_the_grace_period(client, spy):  # noqa: F811
    from mimirsynth.models import Audit, Membership, User
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "tk6", "name": "Tk6"}).status_code == 201
    old = _tok(client, "tk6", scopes=["recall"], days=90)
    r = client.post(f"/api/brains/tk6/tokens/{old['id']}/rotate", json={"grace_hours": 24})
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["token"] != old["token"] and new["name"] == old["name"] and new["scopes"] == ["recall"]
    assert timedelta(days=89) < datetime.fromisoformat(new["expires_at"]) - datetime.now(timezone.utc) <= timedelta(days=90)   # same lifetime
    assert timedelta(hours=23) < datetime.fromisoformat(new["old_expires_at"]) - datetime.now(timezone.utc) <= timedelta(hours=24)
    for tok in (old["token"], new["token"]):                                    # both work during the grace period
        assert client.post("/api/brains/tk6/recall", json={"query": "algo"}, headers=_h(tok)).status_code == 200
    listed = {t["id"]: t for t in client.get("/api/brains/tk6/tokens").json()}
    assert listed[old["id"]]["replaced_by"] == new["id"]
    assert client.post(f"/api/brains/tk6/tokens/{old['id']}/rotate", json={}).status_code == 409   # already rotated
    _set(old["id"], expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))                 # the grace period is over
    assert client.post("/api/brains/tk6/recall", json={"query": "algo"}, headers=_h(old["token"])).status_code == 401
    assert client.post("/api/brains/tk6/recall", json={"query": "algo"}, headers=_h(new["token"])).status_code == 200
    # no grace: the old one stops at once; and only its owner rotates it
    r = client.post(f"/api/brains/tk6/tokens/{new['id']}/rotate", json={"grace_hours": 0})
    assert r.status_code == 201
    assert client.post("/api/brains/tk6/recall", json={"query": "algo"}, headers=_h(new["token"])).status_code == 401
    with _factory()() as db:
        other = User(email="other-tk6@example.com", name="Other", status="active")
        db.add(other)
        db.flush()
        from mimirsynth.models import ApiToken, Brain
        bid = db.query(Brain).filter(Brain.slug == "tk6").one().id
        db.add(Membership(user_id=other.id, brain_id=bid, role="reader"))
        foreign = ApiToken(user_id=other.id, brain_id=bid, name="ajeno", role="reader", prefix="mst_x", token_hash="f" * 64)
        db.add(foreign)
        db.commit()
        fid = foreign.id
        assert db.query(Audit).filter(Audit.action == "token.rotate").count() == 2
    assert client.post(f"/api/brains/tk6/tokens/{fid}/rotate", json={}).status_code == 404   # an administrator does not get someone else's


def test_the_instance_caps_the_life_of_new_tokens(client, monkeypatch):  # noqa: F811
    from mimirsynth.config import settings
    assert client.post("/api/brains", json={"slug": "tk7", "name": "Tk7"}).status_code == 201
    forever = _tok(client, "tk7")
    monkeypatch.setattr(settings, "token_max_days", 30)
    assert client.get("/api/config").json()["token_max_days"] == 30
    for days in (None, 90):
        r = client.post("/api/brains/tk7/tokens", json={"name": "x", "days": days})
        assert r.status_code == 400 and "30" in r.json()["detail"]
    assert _tok(client, "tk7", days=30)["expires_at"]
    rotated = client.post(f"/api/brains/tk7/tokens/{forever['id']}/rotate", json={}).json()   # a token that never expired gets the maximum
    assert timedelta(days=29) < datetime.fromisoformat(rotated["expires_at"]) - datetime.now(timezone.utc) <= timedelta(days=30)


def test_a_token_about_to_expire_is_announced_once(client):  # noqa: F811
    from mimirsynth import memory
    from mimirsynth.models import Notification
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "tk8", "name": "Tk8"}).status_code == 201
    soon, later = _tok(client, "tk8", days=3, name="pronto"), _tok(client, "tk8", days=60, name="luego")
    gone = _tok(client, "tk8", days=3, name="rotado")
    repl = client.post(f"/api/brains/tk8/tokens/{gone['id']}/rotate", json={}).json()
    assert memory.check_expiring() >= 2 and memory.check_expiring() == 0         # once per token
    with _factory()() as db:
        n = db.query(Notification).filter(Notification.event == "token.expiring", Notification.key == f"token:{soon['id']}").one()
        assert "pronto" in n.title and soon["token"] not in n.body and soon["token"][:10] in n.body
        announced = {x.key for x in db.query(Notification).filter(Notification.event == "token.expiring")}
        assert f"token:{repl['id']}" in announced                                 # the replacement, which also expires in 3 days
        assert f"token:{gone['id']}" not in announced and f"token:{later['id']}" not in announced


def test_the_recall_hook_says_why_a_token_stopped_working(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("mimirsynth_recall_hook", HOOK)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    for k, v in {"MIMIRSYNTH_URL": "https://m.example", "MIMIRSYNTH_TOKEN": "mst_x", "MIMIRSYNTH_BRAIN": "b"}.items():
        monkeypatch.setenv(k, v)
    detail = "token caducado el 2026-01-02: crea uno nuevo, o rótalo antes de que caduque"

    def expired(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(json.dumps({"detail": detail}).encode()))
    monkeypatch.setattr(hook.urllib.request, "urlopen", expired)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "¿dónde corre Nextcloud ahora?"})))
    assert hook.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"systemMessage": f"MimirSynth no ha podido recordar: {detail}"}

    def down(req, timeout=None):
        raise urllib.error.URLError("refused")
    monkeypatch.setattr(hook.urllib.request, "urlopen", down)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "¿dónde corre Nextcloud ahora?"})))
    assert hook.main() == 0 and capsys.readouterr().out == ""                   # anything else still fails open, silently
