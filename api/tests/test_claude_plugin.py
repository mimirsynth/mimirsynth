"""The Claude Code plugin (issue 105): its manifest and hooks hang together, it carries the server's own secret detector, recall fails open
and says when the token is no longer valid, the capture is off by default and then nothing is written or sent, and when it is on a session
becomes at most one quarantined proposal, redacted, only with a contributor token. And the two routes it uses: /whoami and /news."""
import importlib
import io
import json
import os
import sys
import time
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
    for m in [m for m in sys.modules if m.split(".")[0] in ("mimir", "hook", "cli", "statusline", "mimirsynth_agent")]:
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
    return type("P", (), {"mimir": mimir, "hook": hook, "calls": calls, "answers": answers, "tmp": tmp_path,
                          "line": importlib.import_module("statusline"), "cli": importlib.import_module("cli")})


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
    assert not (plugin.tmp / "data").exists()
    assert [c["path"] for c in plugin.calls] == ["/brains/b1/recall", "/brains/b1/whoami"]   # the recall, and who the token is (#481)
    rows = "".join(f.read_text(encoding="utf-8") for f in (plugin.tmp / "status").glob("*.json"))   # the status row: nothing of the session
    assert "deploy" not in rows and "Done." not in rows


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


# --- the status row (#481) ----------------------------------------------------------------------

def _row(p, session):
    return p.line.row(p.line.current(session, p.tmp / "status"), colour=False)


def _http(status, detail):
    return urllib.error.HTTPError("u", status, "x", {}, io.BytesIO(json.dumps({"detail": detail}).encode()))


def test_the_row_shows_the_brain_the_role_and_what_the_recall_did(plugin, monkeypatch, capsys):
    _configure(monkeypatch)
    plugin.answers["/brains/b1/whoami"] = {"role": "contributor", "token": {"expires_at": None}}
    _run(plugin, "session-start", {"session_id": "s1", "source": "startup"}, capsys)
    assert _row(plugin, "s1") == "● mimirsynth  b1 · contributor · capture off · connected"
    plugin.answers["/brains/b1/recall"] = {"context": "## Facts\n- db runs on db02", "facts": [{}, {}, {}, {}], "chunks": [{}], "documents": []}
    _run(plugin, "prompt", {"prompt": "where does the database run now?", "session_id": "s1"}, capsys)
    assert _row(plugin, "s1").endswith("capture off · recall: 4 facts, 1 passage")
    assert plugin.line.health(plugin.line.current("s1", plugin.tmp / "status")) == "green"
    plugin.answers["/brains/b1/recall"] = {"context": "", "facts": []}
    _run(plugin, "prompt", {"prompt": "something nobody wrote down", "session_id": "s1"}, capsys)
    assert _row(plugin, "s1").endswith("recall: nothing relevant")
    _run(plugin, "prompt", {"prompt": "short", "session_id": "s1"}, capsys)                     # not recalled: the row stays
    assert _row(plugin, "s1").endswith("recall: nothing relevant")
    assert _row(plugin, "s2") == "● mimirsynth  no activity yet"                                # another session, nothing yet


@pytest.mark.parametrize("error, says, message", [
    (TimeoutError("timed out"), "recall: offline", False),
    (urllib.error.URLError("refused"), "recall: offline", False),
    (_http(401, "token expired on 2026-11-01"), "recall: token rejected (401)", True),
    (_http(403, "no recall scope"), "recall: token rejected (403)", True),
    (_http(404, "no such brain"), "recall: error 404", False),
    (_http(503, "unavailable"), "recall: server error 503", False),
    (ValueError("not JSON"), "recall: unexpected answer", False),       # a proxy's HTML page: not «offline»
])
def test_a_failed_recall_shows_in_the_row_and_the_prompt_goes_on(plugin, monkeypatch, capsys, error, says, message):
    _configure(monkeypatch)
    plugin.answers["/brains/b1/recall"] = error
    out = _run(plugin, "prompt", {"prompt": "where does the database run now?", "session_id": "s1"}, capsys)
    assert "hookSpecificOutput" not in out and ("systemMessage" in out) == message                # nothing injected; 401 also said
    st = plugin.line.current("s1", plugin.tmp / "status")
    assert _row(plugin, "s1").endswith(says) and plugin.line.health(st) == "red"


def test_rendering_the_row_makes_no_network_call_and_never_fails(plugin, monkeypatch, capsys):
    _configure(monkeypatch)
    plugin.answers["/brains/b1/whoami"] = {"role": "reader", "token": {}}
    _run(plugin, "session-start", {"session_id": "s1"}, capsys)

    def no_network(*a, **k):
        raise AssertionError("the status row made a network call")
    monkeypatch.setattr(plugin.mimir.urllib.request, "urlopen", no_network)
    monkeypatch.setenv("MIMIRSYNTH_CONFIG", str(plugin.tmp / "config.json"))
    monkeypatch.setenv("NO_COLOR", "1")
    for stdin, expected in ((json.dumps({"session_id": "s1"}), "● mimirsynth  b1 · reader · capture off · connected"),
                            ("not json", "mimirsynth"), (json.dumps({"session_id": "../../etc/passwd"}), "● mimirsynth  no activity yet")):
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
        assert plugin.line.main() == 0 and capsys.readouterr().out.strip() == expected
    (plugin.tmp / "status" / "s1.json").write_text("{half", encoding="utf-8")              # a corrupt file: a neutral row
    assert _row(plugin, "s1") == "● mimirsynth  no activity yet"
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"session_id": "s1"})))
    plugin.line.main()
    assert "\033[" in capsys.readouterr().out                                                    # coloured unless NO_COLOR


def test_whoami_is_asked_once_an_hour_and_a_close_expiry_turns_the_dot_amber(plugin, monkeypatch, capsys):
    _configure(monkeypatch)
    soon = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3 * 86400 + 3600))
    plugin.answers["/brains/b1/whoami"] = {"role": "reader", "token": {"expires_at": soon}}
    for sid in ("s1", "s2"):
        _run(plugin, "session-start", {"session_id": sid}, capsys)
    assert [c["path"] for c in plugin.calls].count("/brains/b1/whoami") == 1
    st = plugin.line.current("s2", plugin.tmp / "status")
    assert plugin.line.health(st) == "amber" and "reader · token expires in 3 days" in _row(plugin, "s2")
    monkeypatch.setenv("MIMIRSYNTH_TOKEN", "mst_rotated")                                     # another token: asked again
    plugin.answers["/brains/b1/whoami"] = _http(401, "revoked")
    _run(plugin, "session-start", {"session_id": "s3"}, capsys)
    assert _row(plugin, "s3").endswith("token rejected (401)") and [c["path"] for c in plugin.calls].count("/brains/b1/whoami") == 2
    assert plugin.line.health({"health": "ok", "expires_at": "2020-01-01T00:00:00Z"}) == "red"


def test_not_configured_drafts_and_a_proposal_show_in_the_row(plugin, monkeypatch, capsys):
    _run(plugin, "session-start", {"session_id": "s0"}, capsys)
    assert _row(plugin, "s0") == "● mimirsynth  not configured: run /mimirsynth:setup"
    _configure(monkeypatch, capture="draft")
    plugin.answers["/brains/b1/whoami"] = {"role": "contributor", "token": {}}
    _session(plugin, capsys, "old", "Moved the database to db02 and updated the backup job to match the new host and its retention.")
    _run(plugin, "session-start", {"session_id": "s1"}, capsys)
    assert "capture draft · 1 draft · connected" in _row(plugin, "s1")
    time.sleep(0.01)
    plugin.answers["/brains/b1/proposals"] = {"id": 7, "status": "pending"}
    assert plugin.cli.main(["remember", "--title", "db", "--content", "the database runs on db02"]) == 0
    assert _row(plugin, "s1").endswith("proposal #7 queued for review")                        # newer than the session's own


def test_the_status_files_hold_no_token_or_prompt_and_old_ones_go(plugin, monkeypatch, capsys):
    _configure(monkeypatch)
    plugin.answers["/brains/b1/whoami"] = {"role": "reader", "token": {}}
    plugin.answers["/brains/b1/recall"] = {"context": "- x", "facts": [{}]}
    _run(plugin, "session-start", {"session_id": "s1"}, capsys)
    _run(plugin, "prompt", {"prompt": "where does the secret database run?", "session_id": "s1"}, capsys)
    text = "".join(f.read_text(encoding="utf-8") for f in (plugin.tmp / "status").glob("*.json"))
    assert "mst_reader" not in text and "secret database" not in text
    old = plugin.tmp / "status" / "gone.json"
    old.write_text("{}", encoding="utf-8")
    os.utime(old, (time.time() - 8 * 86400,) * 2)
    _run(plugin, "session-start", {"session_id": "s2"}, capsys)
    assert not old.exists() and (plugin.tmp / "status" / "s1.json").exists()


def test_statusline_setup_never_replaces_the_users_own_and_removes_only_its_own(plugin, capsys):
    settings = plugin.tmp / ".claude" / "settings.json"
    assert plugin.cli.main(["statusline"]) == 0                                                # none: added, script copied
    line = json.loads(settings.read_text(encoding="utf-8"))["statusLine"]
    copy = plugin.tmp / "statusline.py"
    assert line["type"] == "command" and copy.as_posix() in line["command"] and "\\" not in line["command"]
    assert copy.read_bytes() == (PLUGIN / "scripts" / "statusline.py").read_bytes()
    assert plugin.cli.main(["statusline", "--remove"]) == 0 and "statusLine" not in json.loads(settings.read_text(encoding="utf-8"))
    assert not copy.exists()
    mine = {"statusLine": {"type": "command", "command": "~/bin/my-line.sh"}, "theme": "dark"}
    settings.write_text(json.dumps(mine), encoding="utf-8")
    assert plugin.cli.main(["statusline"]) == 0 and json.loads(settings.read_text(encoding="utf-8")) == mine
    assert "already has a status line" in capsys.readouterr().out
    assert plugin.cli.main(["statusline", "--remove"]) == 0 and json.loads(settings.read_text(encoding="utf-8")) == mine
    settings.write_text("{not json", encoding="utf-8")
    assert plugin.cli.main(["statusline"]) == 1 and settings.read_text(encoding="utf-8") == "{not json"


def test_session_start_keeps_an_installed_copy_of_the_row_up_to_date(plugin, monkeypatch, capsys):
    copy = plugin.tmp / "statusline.py"
    _run(plugin, "session-start", {"session_id": "s1"}, capsys)
    assert not copy.exists()                                                                   # not installed: nothing written
    copy.write_text("# an older version", encoding="utf-8")
    _run(plugin, "session-start", {"session_id": "s1"}, capsys)
    assert copy.read_bytes() == (PLUGIN / "scripts" / "statusline.py").read_bytes()


def test_status_says_the_last_action_and_whether_the_row_is_on(plugin, monkeypatch, capsys):
    _configure(monkeypatch)
    plugin.answers["/brains/b1/whoami"] = {"role": "reader", "token": {}, "name": "B1", "brain": "b1"}
    plugin.answers["/brains/b1/recall"] = {"context": "- x", "facts": [{}]}
    _run(plugin, "prompt", {"prompt": "where does the database run now?", "session_id": "s1"}, capsys)
    plugin.cli.main(["status"])
    out = capsys.readouterr().out
    assert "Last thing the memory did: recall: 1 fact" in out and "Status row: off" in out


# --- answers to the reviews of #481 -------------------------------------------------------------

def test_remove_leaves_a_users_own_line_that_calls_the_row(plugin, capsys):
    """Code review, QA and security: a user's line that also runs the copy is theirs, and --remove leaves it."""
    settings = plugin.tmp / ".claude" / "settings.json"
    settings.parent.mkdir()
    mine = {"statusLine": {"type": "command", "command": f"bash -c 'mine.sh; python3 {plugin.tmp.as_posix()}/statusline.py'"}}
    settings.write_text(json.dumps(mine), encoding="utf-8")
    assert plugin.cli.main(["statusline", "--remove"]) == 0 and json.loads(settings.read_text(encoding="utf-8")) == mine
    assert "not MimirSynth's" in capsys.readouterr().out


def test_a_config_folder_with_shell_characters_stays_a_path(plugin, monkeypatch):
    """Security: the command is quoted for the shell, so `$(…)`, backticks and `$VAR` in the folder's name are never run."""
    import shlex
    odd = plugin.tmp / "a$(touch PWNED) `id` $HOME"
    odd.mkdir()
    monkeypatch.setattr(plugin.mimir, "CONFIG", odd / "config.json")
    assert plugin.cli.main(["statusline"]) == 0
    command = json.loads((plugin.tmp / ".claude" / "settings.json").read_text(encoding="utf-8"))["statusLine"]["command"]
    assert shlex.split(command) == ["python3", (odd / "statusline.py").as_posix()] and command.count("'") == 2
    assert plugin.cli.main(["statusline", "--remove"]) == 0 and not (odd / "statusline.py").exists()


def test_the_row_never_prints_terminal_escapes_or_new_lines(plugin, monkeypatch, capsys):
    """Security: what a server or a file sends reaches the row without control characters, and the role must look like one."""
    _configure(monkeypatch)
    plugin.answers["/brains/b1/whoami"] = {"role": "reader\x1b]0;owned\x07\nsecond", "token": {"expires_at": "\x1b[2J"}}
    _run(plugin, "session-start", {"session_id": "s1"}, capsys)
    st = json.loads((plugin.tmp / "status" / "s1.json").read_text(encoding="utf-8"))
    assert st["role"] is None and st["expires_at"] == "[2J"
    (plugin.tmp / "status" / "_shared.json").write_text(json.dumps({"action": "x\x1b]52;c;Zm9v\x07\ny" + "z" * 500, "at": time.time() + 9}))
    line = _row(plugin, "s1")
    assert "\x1b" not in line and "\n" not in line and "\x07" not in line and len(line) < 140


def test_a_cached_whoami_never_hides_a_server_that_is_down_now(plugin, monkeypatch, capsys):
    """Code review and QA: /whoami came from the cache, but /news failed at this start: the row says so, not «connected»."""
    _configure(monkeypatch)
    plugin.answers["/brains/b1/whoami"] = {"role": "reader", "token": {}}
    _run(plugin, "session-start", {"session_id": "s1"}, capsys)
    plugin.answers["/brains/b1/news"] = _http(401, "revoked")
    _run(plugin, "session-start", {"session_id": "s2"}, capsys)
    assert _row(plugin, "s2").endswith("token rejected (401)") and plugin.line.health(plugin.line.current("s2", plugin.tmp / "status")) == "red"
    plugin.answers["/brains/b1/news"] = urllib.error.URLError("down")
    _run(plugin, "session-start", {"session_id": "s3"}, capsys)
    assert _row(plugin, "s3").endswith("offline")


def test_an_unreachable_server_is_not_asked_again_at_the_same_start(plugin, monkeypatch, capsys):
    """Code review: when /whoami cannot reach the server, news and the capture's sends are left for the next start."""
    _configure(monkeypatch, capture="send")
    plugin.answers["/brains/b1/whoami"] = urllib.error.URLError("down")
    _session(plugin, capsys, "old", "Moved the database to db02 and updated the backup job to match the new host and its retention.")
    n = len(plugin.calls)
    _run(plugin, "session-start", {"session_id": "s1"}, capsys)
    assert [c["path"] for c in plugin.calls[n:]] == ["/brains/b1/whoami"] and _row(plugin, "s1").endswith("offline")


def test_with_recall_and_news_off_the_start_stays_off_the_network(plugin, monkeypatch, capsys):
    _configure(monkeypatch, recall="off", news="off")
    _run(plugin, "session-start", {"session_id": "s1"}, capsys)
    assert plugin.calls == [] and _row(plugin, "s1") == "● mimirsynth  b1 · capture off · recall off"


def test_a_setup_during_the_session_shows_at_the_next_recall(plugin, monkeypatch, capsys):
    """QA: the row said «not configured» until the next start, although the recall already worked."""
    _run(plugin, "session-start", {"session_id": "s1"}, capsys)
    _configure(monkeypatch)
    plugin.answers["/brains/b1/recall"] = {"context": "- x", "facts": [{}]}
    _run(plugin, "prompt", {"prompt": "where does the database run now?", "session_id": "s1"}, capsys)
    assert _row(plugin, "s1") == "● mimirsynth  b1 · capture off · recall: 1 fact"


@pytest.mark.parametrize("body", [[1], "str", {"role": "reader", "token": "abc"}])
def test_an_odd_whoami_answer_never_stops_the_session_start(plugin, monkeypatch, capsys, body):
    """QA: an unexpected /whoami body lost the drafts message and the news."""
    _configure(monkeypatch, capture="draft")
    plugin.answers["/brains/b1/whoami"] = body
    _session(plugin, capsys, "old", "Moved the database to db02 and updated the backup job to match the new host and its retention.")
    out = _run(plugin, "session-start", {"session_id": "s1"}, capsys)
    assert "1 session draft(s) waiting" in out["systemMessage"] and _row(plugin, "s1").endswith("unexpected answer")


def test_a_damaged_whoami_cache_is_asked_again(plugin, monkeypatch, capsys):
    _configure(monkeypatch)
    (plugin.tmp / "status").mkdir()
    (plugin.tmp / "status" / "_whoami.json").write_text(json.dumps({"k": 1, "x": {"at": "soon"}}), encoding="utf-8")
    plugin.answers["/brains/b1/whoami"] = {"role": "reader", "token": {}}
    _run(plugin, "session-start", {"session_id": "s1"}, capsys)
    assert _row(plugin, "s1").endswith("reader · capture off · connected")


def test_a_failed_remember_still_says_why_and_shows_in_the_row(plugin, monkeypatch, capsys):
    _configure(monkeypatch)
    plugin.answers["/brains/b1/proposals"] = urllib.error.URLError("down")
    with pytest.raises(urllib.error.URLError):                                 # the command fails loudly, as before
        plugin.cli.main(["remember", "--title", "db", "--content", "the database runs on db02"])
    shared = json.loads((plugin.tmp / "status" / "_shared.json").read_text(encoding="utf-8"))
    assert shared["action"] == "proposal not sent: offline" and shared["health"] == "offline"
    plugin.answers["/brains/b1/proposals"] = {"id": "x\x1b[2J", "status": "weird status!"}
    assert plugin.cli.main(["remember", "--title", "db", "--content", "the database runs on db02"]) == 0
    assert json.loads((plugin.tmp / "status" / "_shared.json").read_text(encoding="utf-8"))["action"] == "proposal #? sent"


def test_reserved_names_are_never_a_session_and_leftovers_go(plugin, monkeypatch, capsys):
    _configure(monkeypatch)
    plugin.answers["/brains/b1/whoami"] = {"role": "reader", "token": {}}
    _run(plugin, "session-start", {"session_id": "s1"}, capsys)
    assert _row(plugin, "_whoami") == _row(plugin, "_shared") == "● mimirsynth  no activity yet"
    left = plugin.tmp / "status" / ".s1.json.123.tmp"
    left.write_text("{}", encoding="utf-8")
    os.utime(left, (time.time() - 7200,) * 2)
    _run(plugin, "session-start", {"session_id": "s2"}, capsys)
    assert not left.exists()


def test_a_token_that_expires_today_says_so(plugin):
    soon = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3 * 3600))
    assert plugin.line.row({"brain": "b1", "role": "reader", "expires_at": soon, "health": "ok"}, colour=False).endswith("reader · token expires today")
