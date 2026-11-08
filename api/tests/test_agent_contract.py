"""The shared client library against a test instance (#369): a real server on a local port, a brain and one token per role, and the same
checks run by the Python library and by its TypeScript port. A plugin's own end-to-end tests can use the `agent_instance` fixture too
(docs/AGENT_CLIENT.md, «Contract tests»).

Only `news` needs a graph (MIMIRSYNTH_TEST_FALKOR); recall answers from a stand-in, because a test instance has no embedding model."""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_control import client  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
TS = ROOT / "integrations" / "shared" / "typescript"
sys.path.insert(0, str(ROOT / "integrations" / "shared" / "python"))
import mimirsynth_agent as lib  # noqa: E402
from mimirsynth_agent import capture  # noqa: E402

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GITHUB = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def agent_instance(client, monkeypatch):  # noqa: F811
    """A MimirSynth on http://127.0.0.1:<port> with a fresh brain and a token per role: reader (recall only), contributor, curator and
    a contributor that can only propose. `seen` holds every recall query the server received."""
    import uvicorn
    from mimirsynth import memory
    from mimirsynth.main import app
    seen = []

    def fake_recall(brain_id, graph_name, query, *a, **k):
        seen.append(query)
        return {"context": f"## Facts\n- the contract brain answers: {query[:40]}", "facts": [], "chunks": [], "documents": []}
    monkeypatch.setattr(memory, "recall", fake_recall)
    slug = f"contract-{uuid.uuid4().hex[:8]}"
    assert client.post("/api/brains", json={"slug": slug, "name": "Contract"}).status_code == 201

    def token(name, role, **body):
        r = client.post(f"/api/brains/{slug}/tokens", json={"name": name, "role": role, **body})
        assert r.status_code == 201, r.text
        return r.json()["token"]
    tokens = {"reader": token("reader", "reader", scopes=["recall"]), "contributor": token("contributor", "contributor"),
              "curator": token("curator", "curator"), "propose_only": token("propose-only", "contributor", scopes=["propose"])}
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="off", log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started, "the test instance did not start"
    yield SimpleNamespace(url=f"http://127.0.0.1:{port}", brain=slug, tokens=tokens, seen=seen, client=client)
    server.should_exit = True
    thread.join(10)


def _conf(tmp_path, inst, **over) -> lib.Config:
    data = {"url": inst.url, "brain": inst.brain, "token": inst.tokens["reader"], "write_token": inst.tokens["contributor"], "timeout": 10,
            **over}
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    return lib.Config(path=tmp_path / "config.json", env={})


def _proposals(inst) -> int:
    r = inst.client.get(f"/api/brains/{inst.brain}/proposals", headers={"Authorization": f"Bearer {inst.tokens['curator']}"})
    return r.json()["total"]


def test_recall_and_whoami_against_a_test_instance(agent_instance, tmp_path):
    c = lib.Client(_conf(tmp_path, agent_instance))
    who = c.whoami()
    assert who["role"] == "reader" and who["brain"] == agent_instance.brain and who["token"]["scopes"] == ["recall"]
    assert c.whoami(agent_instance.tokens["contributor"])["role"] == "contributor"
    r = c.recall("where does the production database run?")
    assert "the contract brain answers: where does the production database" in r["context"]
    assert agent_instance.seen == ["where does the production database run?"]


def test_what_the_server_says_when_a_token_cannot_and_fail_open_when_it_is_away(agent_instance, tmp_path):
    c = lib.Client(_conf(tmp_path, agent_instance, token=agent_instance.tokens["propose_only"]))
    value, err = lib.fail_open(c.recall, "where does the production database run?")
    assert value is None and err.status == 403 and err.auth and err.detail
    c = lib.Client(_conf(tmp_path, agent_instance, token="mst_" + "not-a-real-token"))
    value, err = lib.fail_open(c.recall, "where does the production database run?")
    assert value is None and err.status == 401 and err.auth
    away = lib.Client(_conf(tmp_path, agent_instance, url=f"http://127.0.0.1:{_free_port()}", timeout=2))
    started = time.monotonic()
    assert lib.fail_open(away.recall, "where does the production database run?") == (None, None)
    assert time.monotonic() - started < 5


def test_remember_proposes_redacted_into_quarantine(agent_instance, tmp_path):
    c = lib.Client(_conf(tmp_path, agent_instance))
    r = c.remember("Deploy key moved", f"The deploy key now lives in Vaultwarden; the old one {GITHUB} was revoked.", confidence=0.8,
                   source_description="contract")
    assert r["status"] == "pending"
    p = agent_instance.client.get(f"/api/brains/{agent_instance.brain}/proposals/{r['id']}",
                                  headers={"Authorization": f"Bearer {agent_instance.tokens['curator']}"}).json()
    assert GITHUB not in p["body"] and lib.MARKER in p["body"] and p["origin"] == "agent" and p["confidence"] == 0.8


def test_capture_sends_one_quarantined_proposal_only_with_a_contributor_token(agent_instance, tmp_path):
    store = capture.Sessions(tmp_path / "sessions")
    rec = {"session": "s1", "files": ["ops/deploy.sh"], "turns": 3, "started": time.time(), "ended": True, "sent": None, "project": "infra",
           "first_prompt": "rotate the deploy key", "last_message": "Done: the key lives in Vaultwarden."}
    before = _proposals(agent_instance)
    curator = lib.Client(_conf(tmp_path, agent_instance, write_token=agent_instance.tokens["curator"]))
    with pytest.raises(lib.ApiError) as e:
        capture.send(curator, store, rec, "Contract", "contract")
    assert e.value.status == 403 and "contributor" in e.value.detail and not rec["sent"] and _proposals(agent_instance) == before
    r = capture.send(lib.Client(_conf(tmp_path, agent_instance)), store, rec, "Contract", "contract")
    assert r["status"] == "pending" and store.load("s1")["sent"]["id"] == r["id"] and _proposals(agent_instance) == before + 1
    p = agent_instance.client.get(f"/api/brains/{agent_instance.brain}/proposals/{r['id']}",
                                  headers={"Authorization": f"Bearer {agent_instance.tokens['curator']}"}).json()
    assert p["origin"] == "auto" and p["confidence"] == 0.3 and p["source_description"] == "contract session" and "ops/deploy.sh" in p["body"]


@pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_news_against_a_test_instance(agent_instance, tmp_path):
    r = lib.Client(_conf(tmp_path, agent_instance)).news()
    assert r["added"] == 0 and r["gone"] == 0 and r["text"]


def _node():
    node = shutil.which("node")
    if not node:
        return None
    m = re.match(r"v(\d+)\.(\d+)", subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip())
    return node if m and (int(m[1]), int(m[2])) >= (22, 6) else None


@pytest.mark.skipif(not _node(), reason="the TypeScript port needs Node 22.6 or later")
def test_the_typescript_port_against_a_test_instance(agent_instance):
    env = {**os.environ, "MIMIRSYNTH_CONTRACT_URL": agent_instance.url, "MIMIRSYNTH_CONTRACT_BRAIN": agent_instance.brain,
           **{f"MIMIRSYNTH_CONTRACT_{k.upper()}": v for k, v in agent_instance.tokens.items()},
           "MIMIRSYNTH_CONTRACT_NEWS": "1" if FALKOR else ""}
    r = subprocess.run([_node(), "--experimental-strip-types", "--no-warnings", "--test", "test/live.test.ts"], cwd=TS, env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=180)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert re.search(r"^# pass [1-9]", out, re.M) and re.search(r"^# fail 0", out, re.M), out
    assert agent_instance.seen, "the TypeScript port never reached the instance"
