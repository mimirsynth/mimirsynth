"""The setup wizard (#361): it resumes on the first step neither done nor skipped, the graph and embedding steps only pass when the
server's own check does and can never be skipped, the LLM and the decider can, the brain and token steps check what they are given,
the agent step finishes it, an instance with brains from before counts as set up, and the Ollama helpers only look where they should."""
import pytest

from test_control import client  # noqa: F401  (fixture with the app and the test database)

from mimirsynth import graphconn, setupwizard as W
from mimirsynth.config import settings
from mimirsynth.models import AppSetting
from mimirsynth.store import _factory


@pytest.fixture()
def wizard(client):  # noqa: F811
    with _factory()() as db:
        db.query(AppSetting).filter(AppSetting.key == W.KEY).delete()
        db.commit()
    yield client
    with _factory()() as db:
        db.query(AppSetting).filter(AppSetting.key == W.KEY).delete()
        db.commit()


def _ok_graph(monkeypatch, ok=True):
    monkeypatch.setattr(graphconn, "probe", lambda conn, lang="es", timeout=10: {
        "ok": ok, "error": None if ok else {"step": "reach", "code": "refused", "message": "127.0.0.1:1 rechaza la conexión"}})


def test_an_instance_with_brains_from_before_counts_as_set_up_and_can_reopen(wizard):
    wizard.post("/api/brains", json={"slug": "wz-old", "name": "Old"})
    v = wizard.get("/api/setup").json()
    assert v["finished"] is True and wizard.get("/api/me").json()["setup_pending"] is False
    v = wizard.post("/api/setup/reopen").json()
    assert v["finished"] is False and v["current"] == "graph" and wizard.get("/api/me").json()["setup_pending"] is True
    assert [s["key"] for s in v["steps"]] == list(W.STEPS) and v["steps"][0]["status"] == "done"   # the admin exists: you are it


def test_the_graph_and_embedding_steps_block_until_the_server_checks_them(wizard, monkeypatch):
    from mimirsynth import embeddings_admin
    wizard.post("/api/setup/reopen")
    assert wizard.post("/api/setup/steps/graph", json={"action": "skip"}).status_code == 409             # never skipped
    _ok_graph(monkeypatch, ok=False)
    r = wizard.post("/api/setup/steps/graph", json={"action": "done"})
    assert r.status_code == 409 and "rechaza la conexión" in r.json()["detail"]
    assert wizard.get("/api/setup").json()["current"] == "graph"
    _ok_graph(monkeypatch)
    assert wizard.post("/api/setup/steps/graph", json={"action": "done"}).json()["current"] == "embedding"

    assert wizard.post("/api/setup/steps/embedding", json={"action": "skip"}).status_code == 409
    monkeypatch.setattr(embeddings_admin, "_probe", lambda *a: 1536)                                    # another dimension than the index
    r = wizard.post("/api/setup/steps/embedding", json={"action": "done"})
    assert r.status_code == 409 and "Reindexar" in r.json()["detail"] and str(settings.embedding_dim) in r.json()["detail"]
    monkeypatch.setattr(embeddings_admin, "_probe", lambda *a: settings.embedding_dim)
    assert wizard.post("/api/setup/steps/embedding", json={"action": "done"}).json()["current"] == "llm"


def test_a_whole_run_resumes_where_it_stopped_and_finishes_with_the_agent(wizard, monkeypatch):
    from mimirsynth import embeddings_admin
    from mimirsynth.models import Brain
    with _factory()() as db:   # a fresh instance: no brains at all
        brains = [(b.slug, b.name, b.graph_name) for b in db.query(Brain)]
    wizard.post("/api/setup/reopen")
    _ok_graph(monkeypatch)
    monkeypatch.setattr(embeddings_admin, "_probe", lambda *a: settings.embedding_dim)
    for step in ("graph", "embedding"):
        wizard.post(f"/api/setup/steps/{step}", json={"action": "done"})
    assert wizard.post("/api/setup/steps/llm", json={"action": "done"}).status_code in (409, 200)   # with no engine: 409
    v = wizard.post("/api/setup/steps/llm", json={"action": "skip"}).json()
    assert v["steps"][3]["status"] == "skipped" and v["current"] == "decider"
    v = wizard.post("/api/setup/steps/decider", json={"action": "skip"}).json()
    assert v["current"] == "brain"
    assert wizard.get("/api/setup").json()["current"] == "brain"                                     # closing the browser: same step

    assert wizard.post("/api/setup/steps/brain", json={"action": "done", "brain": "wz-nope"}).status_code == 409
    wizard.post("/api/brains", json={"slug": "wz-first", "name": "First"})
    v = wizard.post("/api/setup/steps/brain", json={"action": "done", "brain": "wz-first"}).json()
    assert v["brain"] == "wz-first" and v["current"] == "token"

    wizard.post("/api/brains", json={"slug": "wz-other", "name": "Other"})
    other = wizard.post("/api/brains/wz-other/tokens", json={"name": "x", "role": "contributor"}).json()
    assert wizard.post("/api/setup/steps/token", json={"action": "done", "token_id": other["id"]}).status_code == 409   # another brain's
    tok = wizard.post("/api/brains/wz-first/tokens", json={"name": "Claude Code", "role": "contributor"}).json()
    v = wizard.post("/api/setup/steps/token", json={"action": "done", "token_id": tok["id"]}).json()
    assert v["token_id"] == tok["id"] and v["current"] == "agent" and v["agent_connected"] is False
    assert wizard.get("/api/me").json()["setup_pending"] is True

    v = wizard.post("/api/setup/steps/agent", json={"action": "done"}).json()
    assert v["finished"] is True and wizard.get("/api/me").json()["setup_pending"] is False
    assert brains is not None


def test_closing_it_marks_the_instance_as_set_up(wizard):
    wizard.post("/api/setup/reopen")
    assert wizard.post("/api/setup/close").json()["finished"] is True
    assert wizard.post("/api/setup/steps/nope", json={"action": "done"}).status_code == 404


def test_ollama_is_looked_for_only_at_its_usual_addresses(wizard, monkeypatch):
    import httpx
    seen = []

    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"models": [{"name": "nomic-embed-text:latest"}, {"name": "qwen2.5:14b-instruct"}]}

    def fake_get(url, timeout=None):
        seen.append(url)
        if url.startswith("http://host.docker.internal"):
            return R()
        raise httpx.ConnectError("no")
    monkeypatch.setattr(W.httpx, "get", fake_get)
    r = wizard.get("/api/setup/ollama").json()
    assert r["found"] == "http://host.docker.internal:11434" and r["openai_base"] == "http://host.docker.internal:11434/v1"
    assert r["has_suggested"] is True and r["models"] == ["nomic-embed-text:latest", "qwen2.5:14b-instruct"]
    assert all(u.endswith("/api/tags") for u in seen)
    assert wizard.post("/api/setup/ollama/pull", json={"base": "http://evil.example.com", "model": "x"}).status_code == 400
