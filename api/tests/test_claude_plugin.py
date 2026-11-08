"""The Claude Code plugin (issue 105): its manifest and hooks hang together, it carries the server's own secret detector, recall fails open
and says when the token is no longer valid, the capture is off by default and then nothing is written or sent, and when it is on a session
becomes at most one quarantined proposal, redacted, only with a contributor token. And the two routes it uses: /whoami and /news."""
import importlib
import io
import json
import os
import sys
import urllib.error
from pathlib import Path

import pytest

from test_control import client  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "integrations" / "claude-code" / "plugin"
FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
GITHUB = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"


@pytest.fixture()
def plugin(monkeypatch, tmp_path):
    """The plugin's modules, configured by environment, with its state in a temporary folder and every request recorded."""
    monkeypatch.syspath_prepend(str(PLUGIN / "scripts"))
    for m in [m for m in sys.modules if m.split(".")[0] in ("mimir", "hook", "cli", "mimirsynth_agent")]:
        sys.modules.pop(m, None)
    mimir = importlib.import_module("mimir")
    monkeypatch.setattr(mimir, "CONFIG", tmp_path / "config.json")
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)   # no real ~/.claude/settings.json
    for k in ("URL", "BRAIN", "TOKEN", "WRITE_TOKEN", "CAPTURE", "NEWS", "RECALL"):
        monkeypatch.delenv(f"MIMIRSYNTH_{k}", raising=False)
    calls, answers = [], {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        path = req.full_url.split("/api", 1)[1].split("?")[0]
        calls.append({"method": req.get_method(), "path": path, "auth": req.headers.get("Authorization"),
                      "body": json.loads(req.data) if req.data else None})
        a = answers.get(path)
        if isinstance(a, Exception):
            raise a
        return Resp(json.dumps(a if a is not None else {}).encode())
    monkeypatch.setattr(mimir.urllib.request, "urlopen", urlopen)
    hook = importlib.import_module("hook")
    return type("P", (), {"mimir": mimir, "hook": hook, "calls": calls, "answers": answers, "tmp": tmp_path})


def _run(p, event, data, capsys):
    monkey = io.StringIO(json.dumps(data))
    sys.stdin = monkey
    try:
        assert p.hook.main(["hook.py", event]) == 0
    finally:
        sys.stdin = sys.__stdin__
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else {}


def _configure(monkeypatch, **extra):
    env = {"URL": "https://mimir.test", "BRAIN": "b1", "TOKEN": "mst_reader", "WRITE_TOKEN": "mst_writer", **extra}
    for k, v in env.items():
        monkeypatch.setenv(f"MIMIRSYNTH_{k.upper()}", v)


def test_the_plugin_hangs_together_and_carries_the_servers_detector():
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert market["plugins"][0]["name"] == manifest["name"] == "mimirsynth"
    assert (ROOT / market["plugins"][0]["source"]).resolve() == PLUGIN.resolve()
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    events = {h["command"].rsplit(" ", 1)[-1] for groups in hooks.values() for g in groups for h in g["hooks"]}
    src = (PLUGIN / "scripts" / "hook.py").read_text(encoding="utf-8")
    assert events == {"session-start", "prompt", "tool", "stop", "session-end"} and all(f'"{e}"' in src for e in events)
    assert {p.stem for p in (PLUGIN / "commands").glob("*.md")} == {"setup", "status", "search", "remember"}
    # the same module on both sides: a rule added to the server reaches the plugin only by copying the file again
    assert (PLUGIN / "scripts" / "mimirsynth_agent" / "secretscan.py").read_bytes() == (ROOT / "api" / "mimirsynth" / "secretscan.py").read_bytes()


def test_redaction_removes_tokens_passwords_headers_and_url_credentials(plugin):
    text = (f"token {GITHUB} · Authorization: Bearer abcdefghijklmnop123 · postgres://app:S3cr3tPassw0rd@db02/x · "
            "db_password = Xk9#mQ2$vL7pW4zR")
    out = plugin.mimir.redact(text)
    for secret in (GITHUB, "abcdefghijklmnop123", "S3cr3tPassw0rd", "Xk9#mQ2$vL7pW4zR"):
        assert secret not in out
    assert out.count("[secret removed]") == 4


def test_recall_fails_open_and_says_when_the_token_is_not_valid(plugin, monkeypatch, capsys):
    _configure(monkeypatch)
    plugin.answers["/brains/b1/recall"] = {"context": "## Facts\n- db runs on db02"}
    out = _run(plugin, "prompt", {"prompt": "where does the database run now?", "session_id": "s1"}, capsys)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert ctx.startswith('<mimirsynth-memory brain="b1">') and "db02" in ctx
    assert plugin.calls[-1]["auth"] == "Bearer mst_reader" and plugin.calls[-1]["body"]["max_chars"] == 4000
    plugin.answers["/brains/b1/recall"] = TimeoutError("timed out")
    assert _run(plugin, "prompt", {"prompt": "where does the database run now?"}, capsys) == {}     # nothing, and the prompt goes on
    plugin.answers["/brains/b1/recall"] = urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b'{"detail": "token expired on 2026-11-01"}'))
    assert "token expired" in _run(plugin, "prompt", {"prompt": "where does the database run now?"}, capsys)["systemMessage"]
    n = len(plugin.calls)
    assert _run(plugin, "prompt", {"prompt": "/mimirsynth:status"}, capsys) == {} and len(plugin.calls) == n   # commands are not recalled


def test_with_capture_off_nothing_is_written_or_sent(plugin, monkeypatch, capsys):
    _configure(monkeypatch, NEWS="off")
    plugin.answers["/brains/b1/recall"] = {"context": ""}
    _run(plugin, "prompt", {"prompt": "please fix the deploy script", "session_id": "s1", "cwd": str(plugin.tmp)}, capsys)
    _run(plugin, "tool", {"session_id": "s1", "cwd": str(plugin.tmp), "tool_input": {"file_path": str(plugin.tmp / "deploy.sh")}}, capsys)
    _run(plugin, "stop", {"session_id": "s1", "last_assistant_message": "Done. " * 200}, capsys)
    _run(plugin, "session-end", {"session_id": "s1", "reason": "prompt_input_exit"}, capsys)
    _run(plugin, "session-start", {"session_id": "s2", "source": "startup"}, capsys)
    assert not (plugin.tmp / "data").exists() and [c["path"] for c in plugin.calls] == ["/brains/b1/recall"]   # only the recall


def _session(plugin, capsys, sid, message):
    plugin.answers["/brains/b1/recall"] = {"context": ""}
    _run(plugin, "prompt", {"prompt": f"rotate the deploy key {GITHUB} on db02", "session_id": sid, "cwd": str(plugin.tmp)}, capsys)
    _run(plugin, "tool", {"session_id": sid, "cwd": str(plugin.tmp), "tool_input": {"file_path": str(plugin.tmp / "ops" / "deploy.sh")}}, capsys)
    _run(plugin, "stop", {"session_id": sid, "last_assistant_message": message}, capsys)
    _run(plugin, "session-end", {"session_id": sid, "reason": "prompt_input_exit"}, capsys)


def test_capture_sends_one_redacted_quarantined_proposal_per_session(plugin, monkeypatch, capsys):
    _configure(monkeypatch, CAPTURE="send", NEWS="off")
    _session(plugin, capsys, "s1", f"The deploy key now lives in Vaultwarden; the old one {GITHUB} was revoked.")
    assert not [c for c in plugin.calls if c["path"].endswith("/proposals")]          # nothing left the machine at the end of the session
    plugin.answers["/brains/b1/whoami"] = {"role": "contributor"}
    plugin.answers["/brains/b1/proposals"] = {"id": 7, "status": "pending"}
    assert _run(plugin, "session-start", {"session_id": "s2", "source": "startup"}, capsys) == {}
    sent = [c for c in plugin.calls if c["path"] == "/brains/b1/proposals"]
    assert len(sent) == 1 and sent[0]["auth"] == "Bearer mst_writer"
    p = sent[0]["body"]
    assert GITHUB not in json.dumps(p) and "[secret removed]" in p["body"] and "ops/deploy.sh" in p["body"].replace("\\", "/")
    assert p["origin"] == "auto" and p["confidence"] == 0.3 and p["name"].startswith("Claude Code: ")
    _run(plugin, "session-start", {"session_id": "s3", "source": "startup"}, capsys)
    assert len([c for c in plugin.calls if c["path"] == "/brains/b1/proposals"]) == 1   # at most one per session


def test_capture_never_sends_with_a_curator_token_and_drafts_wait_for_review(plugin, monkeypatch, capsys):
    _configure(monkeypatch, CAPTURE="send", NEWS="off")
    _session(plugin, capsys, "s1", "The backup job moved to 03:00 because the 02:00 window collided with the reindex. " * 6)
    plugin.answers["/brains/b1/whoami"] = {"role": "curator"}
    out = _run(plugin, "session-start", {"session_id": "s2", "source": "startup"}, capsys)
    assert "contributor" in out["systemMessage"] and not [c for c in plugin.calls if c["path"].endswith("/proposals")]
    monkeypatch.setenv("MIMIRSYNTH_CAPTURE", "draft")
    out = _run(plugin, "session-start", {"session_id": "s3", "source": "startup"}, capsys)
    assert "1 session draft" in out["systemMessage"]
    cli = importlib.import_module("cli")
    assert cli.main(["drafts"]) == 0 and "backup job moved" in capsys.readouterr().out


def test_session_start_brings_what_changed_and_warns_about_other_memory_hooks(plugin, monkeypatch, capsys):
    _configure(monkeypatch)
    (plugin.tmp / ".claude").mkdir()
    (plugin.tmp / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"cognee-memory@x": True, "mimirsynth@mimirsynth": True}}))
    plugin.answers["/brains/b1/news"] = {"text": "# What changed\n- db moved to db02", "added": 1, "gone": 0}
    out = _run(plugin, "session-start", {"session_id": "s1", "source": "startup"}, capsys)
    assert out["hookSpecificOutput"]["additionalContext"].startswith('<mimirsynth-news brain="b1">') and "cognee-memory@x" in out["systemMessage"]
    plugin.answers["/brains/b1/news"] = {"text": "# Nothing new", "added": 0, "gone": 0}
    assert "hookSpecificOutput" not in _run(plugin, "session-start", {"session_id": "s1", "source": "startup"}, capsys)


@needs_falkor
def test_whoami_and_news_for_the_plugin(client):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "cp1", "name": "CP1"}).status_code == 201
    write = client.post("/api/brains/cp1/tokens", json={"name": "w", "role": "contributor", "scopes": ["propose"]}).json()["token"]
    w = client.get("/api/brains/cp1/whoami", headers={"Authorization": f"Bearer {write}"})
    assert w.status_code == 200 and w.json()["role"] == "contributor" and w.json()["token"]["scopes"] == ["propose"]   # any scope may ask
    assert client.post("/api/brains/cp1/news", headers={"Authorization": f"Bearer {write}"}).status_code == 403          # news needs recall
    read = client.post("/api/brains/cp1/tokens", json={"name": "r", "role": "reader", "scopes": ["recall"]}).json()["token"]
    n = client.post("/api/brains/cp1/news", headers={"Authorization": f"Bearer {read}"})
    assert n.status_code == 200 and n.json()["added"] == 0 and n.json()["gone"] == 0 and n.json()["text"]
