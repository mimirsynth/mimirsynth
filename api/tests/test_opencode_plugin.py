"""The OpenCode plugin (#371) against a test instance (the `agent_instance` fixture of test_agent_contract.py), in two ways:

- its hooks, as OpenCode calls them (integrations/opencode/test/live.test.ts): recall into the prompt, a proposal into quarantine, the
  capture off by default, fail open. It needs the plugin's dependencies (`npm ci` in integrations/opencode) and Node 22.6 or later.
- OpenCode itself, with the plugin loaded from this folder and a stand-in model (integrations/opencode/test/mock-llm.mjs) that records
  what reached it. Only with MIMIRSYNTH_TEST_OPENCODE set to an `opencode` program (1.x), and with the plugin built (`npm run build`).

The api job of CI skips both; the plugin-opencode workflow installs what they need and runs them."""
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from test_agent_contract import FALKOR, _free_port, _node, agent_instance  # noqa: F401
from test_control import client  # noqa: F401

PLUGIN = Path(__file__).resolve().parents[2] / "integrations" / "opencode"
OPENCODE = os.environ.get("MIMIRSYNTH_TEST_OPENCODE", "")


def _contract_env(inst) -> dict:
    return {**os.environ, "MIMIRSYNTH_CONTRACT_URL": inst.url, "MIMIRSYNTH_CONTRACT_BRAIN": inst.brain,
            **{f"MIMIRSYNTH_CONTRACT_{k.upper()}": v for k, v in inst.tokens.items()}, "MIMIRSYNTH_CONTRACT_NEWS": "1" if FALKOR else ""}


@pytest.mark.skipif(not _node(), reason="the plugin's tests need Node 22.6 or later")
@pytest.mark.skipif(not (PLUGIN / "node_modules" / "@opencode-ai" / "plugin").exists(),
                    reason="npm ci in integrations/opencode first (the plugin-opencode workflow does)")
def test_the_opencode_plugin_hooks_against_a_test_instance(agent_instance):  # noqa: F811
    r = subprocess.run([_node(), "--experimental-strip-types", "--no-warnings", "--test", "test/live.test.ts"], cwd=PLUGIN,
                       env=_contract_env(agent_instance), capture_output=True, text=True, encoding="utf-8", timeout=180)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert re.search(r"^# pass [1-9]", out, re.M) and re.search(r"^# fail 0", out, re.M), out
    assert any("opencode" in q for q in agent_instance.seen), "the plugin never recalled from the instance"


@pytest.mark.skipif(not OPENCODE, reason="needs OpenCode: MIMIRSYNTH_TEST_OPENCODE=<the opencode program>")
def test_opencode_with_the_plugin_against_a_test_instance(agent_instance, tmp_path, monkeypatch):  # noqa: F811
    """Recall and what changed reach the model with the prompt, the MCP server's and the plugin's tools are offered, a session that wrote a
    file becomes one quarantined proposal at the next start (capture `send`), a command's output reaches the model, and with MimirSynth
    away the prompt goes on. What changed is a stand-in, as recall is: a test instance has no model to learn facts with."""
    assert (PLUGIN / "dist" / "index.js").exists(), "build the plugin first: npm run build in integrations/opencode"
    from mimirsynth import mcp_tools

    def news(ctx, request, body, lang, counts=None):
        if counts is not None:
            counts.update(added=1, gone=0)
        return "## Learned since your last session\n- the backups moved to the NAS"
    monkeypatch.setattr(mcp_tools, "whats_new", news)
    port, log, proj, home = _free_port(), tmp_path / "model.jsonl", tmp_path / "project", tmp_path / "home"
    proj.mkdir()
    log.write_text("")
    conf = {"url": agent_instance.url, "brain": agent_instance.brain, "token": agent_instance.tokens["reader"],
            "write_token": agent_instance.tokens["contributor"], "capture": "send", "timeout": 10}
    mimir = tmp_path / "mimirsynth" / "config.json"
    mimir.parent.mkdir()
    mimir.write_text(json.dumps(conf))
    # OpenCode on its own: its folders under tmp_path, no provider from the environment and no hosted model, only the stand-in
    env = {k: v for k, v in os.environ.items() if not k.startswith("MIMIRSYNTH_") and not k.endswith(("_API_KEY", "_AUTH_TOKEN"))}
    env.update(XDG_CONFIG_HOME=str(home / "config"), XDG_DATA_HOME=str(home / "data"), XDG_CACHE_HOME=str(home / "cache"),
               XDG_STATE_HOME=str(home / "state"), PWD=str(proj), OPENCODE_CONFIG=str(proj / "opencode.json"),
               OPENCODE_DISABLE_AUTOUPDATE="1", OPENCODE_DISABLE_LSP_DOWNLOAD="1", MIMIRSYNTH_CONFIG=str(mimir))
    only_the_stand_in = {"enabled_providers": ["mock"], "disabled_providers": ["opencode"], "autoupdate": False, "share": "disabled"}
    (home / "config" / "opencode").mkdir(parents=True)
    (home / "config" / "opencode" / "opencode.json").write_text(json.dumps(only_the_stand_in))
    (proj / "opencode.json").write_text(json.dumps({
        **only_the_stand_in, "plugin": [PLUGIN.as_uri()], "model": "mock/echo", "small_model": "mock/echo",
        "provider": {"mock": {"npm": "@ai-sdk/openai-compatible", "name": "Stand-in",
                              "options": {"baseURL": f"http://127.0.0.1:{port}/v1", "apiKey": "none"},
                              "models": {"echo": {"name": "Echo", "tool_call": True}}}},
        "permission": {"edit": "allow"},
    }))
    opencode = shutil.which(OPENCODE) or OPENCODE

    def run(*args):
        r = subprocess.run([opencode, "run", "--dir", str(proj), "-m", "mock/echo", *args], cwd=proj, env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=300)
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-4000:]

    def sent_since(n: int) -> str:
        lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()][n:]
        return json.dumps([q["body"] for q in lines])

    def proposals() -> dict:
        return agent_instance.client.get(f"/api/brains/{agent_instance.brain}/proposals",
                                         headers={"Authorization": f"Bearer {agent_instance.tokens['curator']}"}).json()

    def count() -> int:
        return len(log.read_text(encoding="utf-8").splitlines())

    model = subprocess.Popen(["node", str(PLUGIN / "test" / "mock-llm.mjs"), str(port), str(log), proj.as_posix()])
    try:
        time.sleep(1)
        models = subprocess.run([opencode, "models"], cwd=proj, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
        assert [m.strip() for m in models.stdout.splitlines() if "/" in m] == ["mock/echo"], models.stdout + models.stderr
        before = proposals()["total"]

        run("where does the production database run? opencode WRITE_FILE")
        first = sent_since(0)
        assert "<mimirsynth-memory brain=" in first and "the contract brain answers: " in first
        assert "<mimirsynth-news brain=" in first and "the backups moved to the NAS" in first
        for tool in ("mimirsynth_recall", "mimirsynth_whats_new", "mimirsynth_propose_memory", "mimirsynth_send_draft"):
            assert f'"name": "{tool}"' in first, tool
        assert (proj / "notes.md").exists(), "the stand-in's write never ran"
        records = [json.loads(p.read_text()) for p in (mimir.parent / "state" / "opencode" / "sessions").glob("*.json")]
        assert len(records) == 1 and records[0]["files"] == ["notes.md"] and records[0]["ended"] is True, records
        assert proposals()["total"] == before, "nothing leaves the machine before the next session start"

        run("second task: check the backups")
        after = proposals()
        assert after["total"] == before + 1
        p = next(i for i in after["items"] if i.get("source_description") == "opencode session")
        p = agent_instance.client.get(f"/api/brains/{agent_instance.brain}/proposals/{p['id']}",
                                      headers={"Authorization": f"Bearer {agent_instance.tokens['curator']}"}).json()
        assert p["status"] == "pending" and p["origin"] == "auto" and p["confidence"] == 0.3 and "notes.md" in p["body"]

        n = count()
        run("--command", "mimirsynth-status")
        status = sent_since(n)
        assert "Recall token: " in status and "role reader, scopes recall" in status, status[-3000:]

        conf["url"] = f"http://127.0.0.1:{_free_port()}"
        mimir.write_text(json.dumps(conf))
        n = count()
        run("where does the production database run? with MimirSynth away")
        away = sent_since(n)
        assert "with MimirSynth away" in away and "<mimirsynth-memory" not in away
    finally:
        model.terminate()
