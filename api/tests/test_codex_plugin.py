"""The Codex plugin (#370): its manifest, marketplace, hooks and skills hang together and it carries the server's own secret detector;
recall fails open and says when the token is no longer valid; the capture is off by default and then nothing is written, read or sent;
when it is on, a finished session is read from Codex's own session file and becomes at most one quarantined proposal, redacted, only
with a contributor token.

With MIMIRSYNTH_TEST_CODEX (the path to a `codex` executable), the plugin is also installed from this repository's marketplace into a
throwaway CODEX_HOME and the real Codex runs against a test instance, with a stand-in for the model so no account is needed."""
import importlib
import io
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from test_agent_contract import _free_port, _proposals, agent_instance  # noqa: F401
from test_control import client  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "integrations" / "codex" / "plugin"
CODEX = os.environ.get("MIMIRSYNTH_TEST_CODEX")
GITHUB = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
LONG = "The backup job moved to 03:00 because the 02:00 window collided with the reindex. " * 6


@pytest.fixture()
def plugin(monkeypatch, tmp_path):
    """The plugin's modules, configured by environment, with its state and CODEX_HOME in a temporary folder and every request recorded."""
    monkeypatch.syspath_prepend(str(PLUGIN / "scripts"))
    for m in [m for m in sys.modules if m.split(".")[0] in ("mimir", "hook", "cli", "rollout", "mimirsynth_agent")]:
        sys.modules.pop(m, None)
    mimir = importlib.import_module("mimir")
    monkeypatch.setattr(mimir, "CONFIG", tmp_path / "config.json")
    (tmp_path / "codex").mkdir()
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
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
    state = tmp_path / "state" / "codex" / "sessions"
    return type("P", (), {"mimir": mimir, "hook": hook, "calls": calls, "answers": answers, "tmp": tmp_path, "state": state})


def _run(p, event, data, capsys):
    sys.stdin = io.TextIOWrapper(io.BytesIO(json.dumps(data).encode("utf-8")), encoding="utf-8")
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


def _line(kind, payload):
    return json.dumps({"timestamp": "2026-11-08T10:00:00Z", "type": kind, "payload": payload})


def _rollout(folder: Path, sid: str, cwd: Path, prompt: str, answer: str, files=(), paginated=True) -> Path:
    """A session file as Codex writes it: the injected context, the prompt, an edit and the last answer."""
    p = folder / "sessions" / "2026" / "11" / "08" / f"rollout-2026-11-08T10-00-00-{sid}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [_line("session_meta", {"id": sid, "session_id": sid, "cwd": str(cwd), "cli_version": "0.167.0"}),
             _line("response_item", {"type": "message", "role": "user", "content": [
                 {"type": "input_text", "text": f"<environment_context>\n  <cwd>{cwd}</cwd>\n</environment_context>"}]}),
             _line("response_item", {"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]})]
    if paginated:
        lines.append(_line("event_msg", {"type": "item_completed", "item": {"type": "UserMessage", "content": [{"type": "text", "text": prompt}]}}))
        for i, f in enumerate(files):
            lines.append(_line("event_msg", {"type": "item_completed", "item": {
                "type": "FileChange", "id": f"c{i}", "status": "completed", "changes": {str(cwd / f): {"type": "update"}}}}))
        lines.append(_line("event_msg", {"type": "item_completed", "item": {
            "type": "FileChange", "id": "x", "status": "failed", "changes": {str(cwd / "never-written.txt"): {"type": "add"}}}}))
    else:
        lines.append(_line("event_msg", {"type": "user_message", "message": prompt, "kind": "plain"}))
        for i, f in enumerate(files):
            lines.append(_line("event_msg", {"type": "patch_apply_end", "call_id": f"c{i}", "success": True,
                                             "changes": {str(cwd / f): {"type": "update", "unified_diff": "…"}}}))
    lines += [_line("response_item", {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": answer}]}),
              _line("event_msg", {"type": "task_complete", "last_agent_message": answer}), "not json"]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _session(plugin, capsys, sid, answer, files=("ops/deploy.sh",)):
    """A whole Codex session as the hooks see it, with its session file written by «Codex»."""
    path = _rollout(plugin.tmp / "codex", sid, plugin.tmp, f"rotate the deploy key {GITHUB} on db02", answer, files)
    plugin.answers["/brains/b1/recall"] = {"context": ""}
    _run(plugin, "prompt", {"prompt": f"rotate the deploy key {GITHUB} on db02", "session_id": sid, "cwd": str(plugin.tmp),
                            "transcript_path": str(path)}, capsys)
    _run(plugin, "session-end", {"session_id": sid, "cwd": str(plugin.tmp), "transcript_path": str(path), "reason": "other"}, capsys)
    return path


def test_the_plugin_hangs_together_and_carries_the_servers_detector():
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    entry = next(p for p in market["plugins"] if p["name"] == "mimirsynth")
    assert market["name"] == manifest["name"] == "mimirsynth" and (ROOT / entry["source"]).resolve() == PLUGIN.resolve()
    assert manifest["skills"] == "./skills/" and manifest["hooks"] == "./hooks/hooks.json"
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    handlers = [h for groups in hooks.values() for g in groups for h in g["hooks"]]
    events = {h["command"].rsplit(" ", 1)[-1] for h in handlers}
    src = (PLUGIN / "scripts" / "hook.py").read_text(encoding="utf-8")
    assert events == {"session-start", "prompt", "session-end"} and all(f'"{e}"' in src for e in events)
    assert all(h["commandWindows"].rsplit(" ", 1)[-1] == h["command"].rsplit(" ", 1)[-1] and "${PLUGIN_ROOT}" in h["command"] for h in handlers)
    assert hooks["SessionEnd"][0]["hooks"][0]["timeout"] <= 3   # Codex gives SessionEnd at most 3 s
    skills = {p.parent.name: p.read_text(encoding="utf-8") for p in (PLUGIN / "skills").glob("*/SKILL.md")}
    assert set(skills) == {"setup", "status", "search", "remember"}
    assert all(text.startswith(f"---\nname: {name}\ndescription: ") for name, text in skills.items())
    # the same module on both sides: a rule added to the server reaches the plugin only by copying the file again
    assert (PLUGIN / "scripts" / "mimirsynth_agent" / "secretscan.py").read_bytes() == (ROOT / "api" / "mimirsynth" / "secretscan.py").read_bytes()
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import plugin_versions
    finally:
        sys.path.pop(0)
    assert plugin_versions.PLUGINS["integrations/codex/plugin"] == "integrations/codex/plugin/.codex-plugin/plugin.json"


def test_recall_fails_open_and_says_when_the_token_is_not_valid(plugin, monkeypatch, capsys):
    _configure(monkeypatch)
    plugin.answers["/brains/b1/recall"] = {"context": "## Facts\n- db runs on db02 · «ñ»"}
    out = _run(plugin, "prompt", {"prompt": "where does the database run now?", "session_id": "s1"}, capsys)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert ctx.startswith('<mimirsynth-memory brain="b1">') and "db02" in ctx and "«ñ»" in ctx
    assert plugin.calls[-1]["auth"] == "Bearer mst_reader" and plugin.calls[-1]["body"]["max_chars"] == 4000
    plugin.answers["/brains/b1/recall"] = TimeoutError("timed out")
    assert _run(plugin, "prompt", {"prompt": "where does the database run now?"}, capsys) == {}     # nothing, and the prompt goes on
    plugin.answers["/brains/b1/recall"] = urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b'{"detail": "token expired on 2026-11-01"}'))
    assert "token expired" in _run(plugin, "prompt", {"prompt": "where does the database run now?"}, capsys)["systemMessage"]
    n = len(plugin.calls)
    assert _run(plugin, "prompt", {"prompt": "/status"}, capsys) == {} and len(plugin.calls) == n   # commands are not recalled
    assert _run(plugin, "nonsense", {}, capsys) == {}                                               # an unknown event does nothing


def test_with_capture_off_nothing_is_written_read_or_sent(plugin, monkeypatch, capsys):
    _configure(monkeypatch, NEWS="off")
    _session(plugin, capsys, "s1", LONG)
    _run(plugin, "session-start", {"session_id": "s2", "source": "startup", "cwd": str(plugin.tmp)}, capsys)
    assert not (plugin.tmp / "state").exists() and [c["path"] for c in plugin.calls] == ["/brains/b1/recall"]   # only the recall


def test_a_session_file_gives_the_task_the_outcome_and_the_applied_edits(plugin):
    rollout = importlib.import_module("rollout")
    for paginated in (True, False):
        path = _rollout(plugin.tmp / f"h{paginated}", "s1", plugin.tmp, "fix the deploy", "Fixed it.", ["ops/deploy.sh", "README.md"], paginated)
        got = rollout.read(path)
        assert got["cwd"] == str(plugin.tmp) and got["prompts"] == ["fix the deploy"] and got["last_message"] == "Fixed it."
        assert got["files"] == [str(plugin.tmp / "ops/deploy.sh"), str(plugin.tmp / "README.md")]   # a failed edit is not one
        assert rollout.find("s1", plugin.tmp / f"h{paginated}") == path
    assert rollout.read(plugin.tmp / "missing.jsonl") == {"cwd": "", "prompts": [], "last_message": "", "files": []}
    assert rollout.find("nope", plugin.tmp / "hTrue") is None


def test_capture_sends_one_redacted_quarantined_proposal_per_session(plugin, monkeypatch, capsys):
    _configure(monkeypatch, CAPTURE="send", NEWS="off")
    _session(plugin, capsys, "s1", f"The deploy key now lives in Vaultwarden; the old one {GITHUB} was revoked.")
    assert not [c for c in plugin.calls if c["path"].endswith("/proposals")]          # nothing left the machine at the end of the session
    on_disk = json.dumps([json.loads(p.read_text(encoding="utf-8")) for p in plugin.state.glob("*.json")])
    assert GITHUB not in on_disk
    plugin.answers["/brains/b1/whoami"] = {"role": "contributor"}
    plugin.answers["/brains/b1/proposals"] = {"id": 7, "status": "pending"}
    assert _run(plugin, "session-start", {"session_id": "s2", "source": "startup"}, capsys) == {}
    sent = [c for c in plugin.calls if c["path"] == "/brains/b1/proposals"]
    assert len(sent) == 1 and sent[0]["auth"] == "Bearer mst_writer"
    p = sent[0]["body"]
    assert GITHUB not in json.dumps(p) and "[secret removed]" in p["body"] and "Vaultwarden" in p["body"]
    assert "ops/deploy.sh" in p["body"].replace("\\", "/") and "never-written" not in p["body"]
    assert p["origin"] == "auto" and p["confidence"] == 0.3 and p["name"].startswith("Codex: ") and p["source_description"] == "codex session"
    assert GITHUB not in json.dumps([json.loads(f.read_text(encoding="utf-8")) for f in plugin.state.glob("*.json")])
    _run(plugin, "session-start", {"session_id": "s3", "source": "startup"}, capsys)
    assert len([c for c in plugin.calls if c["path"] == "/brains/b1/proposals"]) == 1   # at most one per session


def test_capture_never_sends_with_a_curator_token_and_drafts_wait_for_review(plugin, monkeypatch, capsys):
    _configure(monkeypatch, CAPTURE="send", NEWS="off")
    _session(plugin, capsys, "s1", LONG, files=())
    plugin.answers["/brains/b1/whoami"] = {"role": "curator"}
    out = _run(plugin, "session-start", {"session_id": "s2", "source": "startup"}, capsys)
    assert "contributor" in out["systemMessage"] and not [c for c in plugin.calls if c["path"].endswith("/proposals")]
    monkeypatch.setenv("MIMIRSYNTH_CAPTURE", "draft")
    out = _run(plugin, "session-start", {"session_id": "s3", "source": "startup"}, capsys)
    assert "1 session draft" in out["systemMessage"] and "$mimirsynth:remember" in out["systemMessage"]
    cli = importlib.import_module("cli")
    assert cli.main(["drafts"]) == 0 and "backup job moved" in capsys.readouterr().out
    assert cli.main(["drop-draft", "s1"]) == 0 and cli.main(["drafts"]) == 0 and "No drafts" in capsys.readouterr().out


def test_an_open_session_waits_a_resumed_one_goes_on_and_one_never_closed_counts_after_a_while(plugin, monkeypatch, capsys):
    _configure(monkeypatch, CAPTURE="draft", NEWS="off")
    path = _rollout(plugin.tmp / "codex", "s1", plugin.tmp, "rotate the deploy key", LONG)
    _run(plugin, "prompt", {"prompt": "rotate the deploy key", "session_id": "s1", "cwd": str(plugin.tmp), "transcript_path": str(path)}, capsys)
    assert _run(plugin, "session-start", {"session_id": "s2", "source": "startup"}, capsys) == {}     # still open: not a draft yet
    old = time.time() - (plugin.mimir.STALE_HOURS + 1) * 3600
    os.utime(path, (old, old))
    assert "1 session draft" in _run(plugin, "session-start", {"session_id": "s3", "source": "startup"}, capsys)["systemMessage"]
    _run(plugin, "session-start", {"session_id": "s1", "source": "resume"}, capsys)                  # the same session again
    assert plugin.mimir.load("s1")["ended"] is False


def test_unknown_sessions_and_sessions_before_capture_are_never_read(plugin, monkeypatch, capsys):
    _configure(monkeypatch, CAPTURE="send", NEWS="off")
    _rollout(plugin.tmp / "codex", "older", plugin.tmp, "a session from before the capture", LONG)
    assert _run(plugin, "session-start", {"session_id": "s2", "source": "startup"}, capsys) == {}
    assert not list(plugin.state.glob("*.json")) and not plugin.calls


def test_setup_asks_for_the_tokens_hidden_only_in_a_terminal(plugin, monkeypatch, capsys):
    cli = importlib.import_module("cli")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))                       # run by the agent, not in a terminal
    assert cli.main(["setup"]) == 2 and "in a terminal" in capsys.readouterr().out and not plugin.mimir.CONFIG.exists()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    asked = iter(["https://mimir.test/", "b1", "draft"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(asked))
    hidden = iter(["mst_reader", "mst_writer"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(hidden))
    plugin.answers["/brains/b1/whoami"] = {"role": "reader", "brain": "b1", "name": "B1", "version": "0.14.0",
                                           "token": {"name": "laptop", "scopes": ["recall"]}}
    assert cli.main(["setup"]) == 0
    saved = json.loads(plugin.mimir.CONFIG.read_text(encoding="utf-8"))
    assert saved == {"url": "https://mimir.test", "brain": "b1", "token": "mst_reader", "write_token": "mst_writer", "capture": "draft"}
    out = capsys.readouterr().out
    assert "mst_reader" not in out and "role reader" in out and "Capture of what each session learned: draft" in out


def test_session_start_brings_what_changed_and_says_what_else_feeds_codex(plugin, monkeypatch, capsys):
    _configure(monkeypatch)
    (plugin.tmp / "codex" / "config.toml").write_text(
        '[features]\nmemories = true\n\n[plugins."cognee-memory@x"]\nenabled = true\n\n[plugins."mimirsynth@mimirsynth"]\nenabled = true\n\n'
        '[hooks.state."mimirsynth@mimirsynth:hooks/hooks.json:user_prompt_submit:0:0"]\ntrusted_hash = "sha256:x"\n', encoding="utf-8")
    plugin.answers["/brains/b1/news"] = {"text": "# What changed\n- db moved to db02", "added": 1, "gone": 0}
    out = _run(plugin, "session-start", {"session_id": "s1", "source": "startup"}, capsys)
    assert out["hookSpecificOutput"]["additionalContext"].startswith('<mimirsynth-news brain="b1">')
    assert "cognee-memory@x" in out["systemMessage"] and "Codex memories" in out["systemMessage"] and "mimirsynth@" not in out["systemMessage"]
    plugin.answers["/brains/b1/news"] = {"text": "# Nothing new", "added": 0, "gone": 0}
    assert "hookSpecificOutput" not in _run(plugin, "session-start", {"session_id": "s1", "source": "startup"}, capsys)
    n = len(plugin.calls)
    _run(plugin, "session-start", {"session_id": "s1", "source": "resume"}, capsys)
    assert len(plugin.calls) == n                                                                    # a resumed session gets no news
    if sys.version_info >= (3, 11):
        assert plugin.mimir.hooks_trusted() is True
        (plugin.tmp / "codex" / "config.toml").write_text("", encoding="utf-8")
        assert plugin.mimir.hooks_trusted() is False


# --- the real Codex --------------------------------------------------------------------------------------------------------------------

class _Model(BaseHTTPRequestHandler):
    """A stand-in for the model's Responses API: every request is kept, every answer is one long assistant message."""
    seen: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"object": "list", "data": [], "models": []}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        type(self).seen.append(raw.decode("utf-8", "replace"))
        rid = f"resp_{len(type(self).seen)}"
        item = {"type": "message", "role": "assistant", "id": "msg_1", "content": [{"type": "output_text", "text": LONG, "annotations": []}]}
        usage = {"input_tokens": 10, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 10,
                 "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 20}
        events = [{"type": "response.created", "response": {"id": rid}}, {"type": "response.output_item.done", "item": item},
                  {"type": "response.completed", "response": {"id": rid, "usage": usage}}]
        body = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _trust_hooks(env, cwd) -> int:
    """What a person does in Codex's /hooks screen, through Codex's app server: list the hooks and trust the plugin's."""
    p = subprocess.Popen([CODEX, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                         encoding="utf-8", cwd=cwd, env=env)
    n = [0]

    def rpc(method, params):
        n[0] += 1
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": n[0], "method": method, "params": params}) + "\n")
        p.stdin.flush()
        while True:
            msg = json.loads(p.stdout.readline())
            if msg.get("id") == n[0]:
                assert "error" not in msg, msg
                return msg["result"]
    try:
        rpc("initialize", {"clientInfo": {"name": "mimirsynth-test", "version": "0"}})
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "initialized"}) + "\n")
        hooks = [h for e in rpc("hooks/list", {"cwds": [str(cwd)]}).get("data") or [] for h in e.get("hooks") or []
                 if str(h.get("pluginId") or "").startswith("mimirsynth@")]
        rpc("config/batchWrite", {"edits": [{"keyPath": f"hooks.state.{json.dumps(h['key'])}.trusted_hash", "mergeStrategy": "upsert",
                                             "value": h["currentHash"]} for h in hooks]})
        return len(hooks)
    finally:
        p.kill()


@pytest.mark.skipif(not CODEX, reason="needs the Codex CLI (MIMIRSYNTH_TEST_CODEX=path to codex)")
def test_the_real_codex_recalls_fails_open_and_captures_only_when_asked(agent_instance, tmp_path):  # noqa: F811
    model = HTTPServer(("127.0.0.1", 0), _Model)
    _Model.seen = []
    threading.Thread(target=model.serve_forever, daemon=True).start()
    home, work = tmp_path / "codex", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    (home / "config.toml").write_text(
        f'model = "gpt-5.5"\nmodel_provider = "stand-in"\n\n[model_providers.stand-in]\nname = "stand-in"\n'
        f'base_url = "http://127.0.0.1:{model.server_address[1]}/v1"\nwire_api = "responses"\n', encoding="utf-8")
    conf = tmp_path / "mimirsynth" / "config.json"
    conf.parent.mkdir()

    def configure(**over):
        conf.write_text(json.dumps({"url": agent_instance.url, "brain": agent_instance.brain, "token": agent_instance.tokens["reader"],
                                    "write_token": agent_instance.tokens["contributor"], "timeout": 10, **over}), encoding="utf-8")
    configure()
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("MIMIRSYNTH_")}, "CODEX_HOME": str(home),
           "MIMIRSYNTH_CONFIG": str(conf), "NO_COLOR": "1"}

    def codex(*args, timeout=180):
        r = subprocess.run([CODEX, *args], cwd=work, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout + r.stderr

    try:
        # installed the way the documentation says, from this repository's marketplace
        codex("plugin", "marketplace", "add", str(ROOT))
        codex("plugin", "add", "mimirsynth@mimirsynth")
        assert _trust_hooks(env, work) == 3
        state = conf.parent / "state"

        codex("exec", "--skip-git-repo-check", "where does the production database run now?")
        sent = "\n".join(_Model.seen)
        assert "<mimirsynth-memory" in sent and "the contract brain answers: where does the production database" in sent
        assert agent_instance.seen == ["where does the production database run now?"]
        assert not state.exists()                                                     # capture off: nothing written

        configure(url=f"http://127.0.0.1:{_free_port()}", timeout=2)                  # MimirSynth is away: Codex carries on
        n = len(_Model.seen)
        started = time.monotonic()
        codex("exec", "--skip-git-repo-check", "where does the production database run now?")
        assert len(_Model.seen) > n and "<mimirsynth-memory" not in _Model.seen[-1] and time.monotonic() - started < 120

        configure(capture="send")
        before = _proposals(agent_instance)
        codex("exec", "--skip-git-repo-check", f"move the backup job; the old key {GITHUB} is revoked")
        assert _proposals(agent_instance) == before                                   # nothing leaves the machine during the session
        codex("exec", "--skip-git-repo-check", "what changed in the backups?")
        assert _proposals(agent_instance) == before + 1                               # the first session, at the next start
        listed = agent_instance.client.get(f"/api/brains/{agent_instance.brain}/proposals",
                                           headers={"Authorization": f"Bearer {agent_instance.tokens['curator']}"}).json()
        p = next(i for i in listed["items"] if i["name"].startswith("Codex: "))
        assert p["status"] == "pending" and p["origin"] == "auto" and p["source_description"] == "codex session"
        full = agent_instance.client.get(f"/api/brains/{agent_instance.brain}/proposals/{p['id']}",
                                         headers={"Authorization": f"Bearer {agent_instance.tokens['curator']}"}).json()
        assert GITHUB not in full["body"] and "backup job moved to 03:00" in full["body"]
    finally:
        model.shutdown()
