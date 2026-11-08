"""The Hermes Agent plugin (#372): a memory provider on the shared client library. It hangs together and carries the library, recall is
injected before each turn and fails open, the news arrive once per session, the tools search and propose into quarantine, the capture is
off by default and then nothing is written or sent, and when it is on a session becomes at most one redacted proposal, only with a
contributor token. The last tests run the provider against a real MimirSynth on a local port (`agent_instance`).

Hermes itself is not installed here: the provider is loaded as Hermes loads a user plugin (a package from its folder) and its hooks are
called as Hermes's MemoryManager calls them. `.github/workflows/plugin-hermes-agent.yml` loads it inside a real Hermes Agent."""
import importlib.util
import io
import json
import re
import sys
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from test_agent_contract import _free_port, _proposals, agent_instance  # noqa: F401
from test_control import client  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "integrations" / "hermes-agent" / "plugin"
GITHUB = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
QUESTION = "how do we deploy the api service now?"


def _load(name: str):
    """The plugin as a package, the way Hermes imports a provider from its folder (its relative imports included)."""
    for m in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
        sys.modules.pop(m)
    spec = importlib.util.spec_from_file_location(name, PLUGIN / "__init__.py", submodule_search_locations=[str(PLUGIN)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def hermes(monkeypatch, tmp_path):
    """The plugin with its configuration and Hermes's home in a temporary folder, and every request to the server recorded."""
    for k in ("URL", "BRAIN", "TOKEN", "WRITE_TOKEN", "CAPTURE", "NEWS", "RECALL", "TIMEOUT", "MAX_CHARS"):
        monkeypatch.delenv(f"MIMIRSYNTH_{k}", raising=False)
    monkeypatch.setenv("MIMIRSYNTH_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.chdir(tmp_path)
    pkg = _load("mimirsynth_hermes_plugin")
    calls, answers = [], {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        path = req.full_url.split("/api", 1)[1].split("?")[0]
        calls.append({"method": req.get_method(), "path": path, "auth": req.headers.get("Authorization"),
                      "body": json.loads(req.data) if req.data else None, "query": req.full_url.partition("?")[2]})
        a = answers.get(path)
        if isinstance(a, Exception):
            raise a
        return Resp(json.dumps(a if a is not None else {}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return types.SimpleNamespace(pkg=pkg, provider=sys.modules["mimirsynth_hermes_plugin.provider"],
                                 commands=importlib.import_module("mimirsynth_hermes_plugin.commands"),
                                 cli=importlib.import_module("mimirsynth_hermes_plugin.cli"), calls=calls, answers=answers, tmp=tmp_path,
                                 home=tmp_path / "hermes")


def _configure(monkeypatch, **extra):
    for k, v in {"URL": "https://mimir.test", "BRAIN": "b1", "TOKEN": "mst_reader", "WRITE_TOKEN": "mst_writer", **extra}.items():
        monkeypatch.setenv(f"MIMIRSYNTH_{k.upper()}", v)


def _start(h, session="s1", **kwargs):
    p = h.provider.MimirSynthProvider()
    p.initialize(session, hermes_home=str(h.home), platform="cli", cwd=str(h.tmp), **kwargs)
    if p._start is not None:
        p._start.join(5)
    return p


def _http_error(status: int, detail: str):
    return urllib.error.HTTPError("u", status, "x", {}, io.BytesIO(json.dumps({"detail": detail}).encode()))


def _turn(file_path: str, patch: str = "") -> list:
    args = {"path": file_path, "content": "x"} if not patch else {"mode": "patch", "patch": patch}
    return [{"role": "user", "content": "rotate the key"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {
                "name": "patch" if patch else "write_file", "arguments": json.dumps(args)}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "ok"}]


# --- the plugin itself ----------------------------------------------------------------------------

def test_the_plugin_hangs_together_and_carries_the_shared_library(hermes):
    manifest = (PLUGIN / "plugin.yaml").read_text(encoding="utf-8")
    assert "\nname: mimirsynth\n" in "\n" + manifest and "requires_hermes:" in manifest
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import plugin_versions
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    assert plugin_versions.PLUGINS["integrations/hermes-agent/plugin"] == "integrations/hermes-agent/plugin/plugin.yaml"
    plugin_versions.parse(plugin_versions.version_of(manifest))
    for f in (ROOT / "integrations" / "shared" / "python" / "mimirsynth_agent").glob("*.py"):   # an exact copy (vendor.py)
        assert (PLUGIN / "mimirsynth_agent" / f.name).read_bytes() == f.read_bytes()
    assert "register_memory_provider" in (PLUGIN / "__init__.py").read_text(encoding="utf-8")   # how Hermes tells a memory provider
    assert (PLUGIN / "README.md").exists() and (PLUGIN / "README.es.md").exists()
    # Hermes's install scan refuses a plugin whose source holds something shaped like a leaked key (tools/skills_guard.py)
    leaked = re.compile(r"ghp_[A-Za-z0-9]{36}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}")
    sources = [f for f in PLUGIN.rglob("*") if f.is_file() and "__pycache__" not in f.parts]   # what is published: no bytecode
    assert not [f.name for f in sources if leaked.search(f.read_text(encoding="utf-8", errors="replace"))]
    registered = {}
    ctx = types.SimpleNamespace(register_memory_provider=lambda p: registered.setdefault("provider", p),
                                register_command=lambda name, handler, **k: registered.setdefault(name, handler))
    hermes.pkg.register(ctx)
    p = registered["provider"]
    assert p.name == "mimirsynth" and {t["name"] for t in p.get_tool_schemas()} == {"mimirsynth_search", "mimirsynth_remember"}
    assert "hermes mimirsynth setup" in registered["mimirsynth"]("setup")
    hermes.pkg.register(types.SimpleNamespace(register_memory_provider=lambda p: None))   # a Hermes without chat commands still loads it
    parser = __import__("argparse").ArgumentParser()
    hermes.cli.register_cli(parser)
    assert parser.parse_args(["search", "deploy", "key"]).query == ["deploy", "key"]


def test_without_a_configuration_it_is_not_available_and_asks_for_nothing(hermes):
    p = _start(hermes)
    assert not p.is_available() and "hermes memory setup mimirsynth" in p.unavailable_reason()
    assert p.prefetch(QUESTION) == "" and p.system_prompt_block() == "" and hermes.calls == []


def test_the_configuration_comes_through_hermess_secret_scope(hermes, monkeypatch, tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"url": "https://file.test", "brain": "from-file", "token": "mst_file"}))
    secrets = {"MIMIRSYNTH_BRAIN": "from-profile", "MIMIRSYNTH_TOKEN": "mst_profile"}
    scope = types.ModuleType("agent.secret_scope")
    scope.get_secret = lambda name, default=None: secrets.get(name, default)
    monkeypatch.setitem(sys.modules, "agent", types.ModuleType("agent"))
    monkeypatch.setitem(sys.modules, "agent.secret_scope", scope)
    monkeypatch.setenv("MIMIRSYNTH_BRAIN", "from-the-process")   # inside Hermes the process environment is not read directly
    conf = hermes.provider.config()
    assert (conf.get("url"), conf.get("brain"), conf.get("token")) == ("https://file.test", "from-profile", "mst_profile")

    def refuse(name, default=None):
        raise RuntimeError("no profile scope on a multiplexed gateway")
    scope.get_secret = refuse
    assert hermes.provider.config().get("brain") == "from-file"   # refused counts as not given: the shared file still works


# --- before each turn -----------------------------------------------------------------------------

def test_recall_is_injected_before_each_turn_and_fails_open(hermes, monkeypatch):
    _configure(monkeypatch, NEWS="off")
    p = _start(hermes)
    assert p.is_available() and "mimirsynth_remember" in p.system_prompt_block()
    hermes.answers["/brains/b1/recall"] = {"context": "## Facts\n- the api deploys with ops/deploy.sh", "facts": [{}, {}], "chunks": [{}]}
    out = p.prefetch(QUESTION)
    assert out.startswith('<mimirsynth-memory brain="b1">') and "ops/deploy.sh" in out and out.endswith("</mimirsynth-memory>")
    c = hermes.calls[-1]
    assert c["path"] == "/brains/b1/recall" and c["auth"] == "Bearer mst_reader" and c["body"]["query"] == QUESTION
    assert c["body"]["max_chars"] == 4000 and c["body"]["facts"] == 6
    if hermes.provider.RecallStatus is None:
        assert p.recall_status() is None
    n = len(hermes.calls)
    assert p.prefetch("ok thanks") == "" and p.prefetch("/mimirsynth status please") == "" and len(hermes.calls) == n
    hermes.answers["/brains/b1/recall"] = urllib.error.URLError("connection refused")
    assert p.prefetch(QUESTION) == "" and p.recall_status() is None              # MimirSynth away: nothing, and the turn goes on
    hermes.answers["/brains/b1/recall"] = TimeoutError("timed out")
    assert p.prefetch(QUESTION) == ""
    monkeypatch.setenv("MIMIRSYNTH_RECALL", "off")
    n = len(hermes.calls)
    assert p.prefetch(QUESTION) == "" and len(hermes.calls) == n


def test_a_token_that_no_longer_works_is_said_once(hermes, monkeypatch):
    _configure(monkeypatch, NEWS="off")
    p = _start(hermes)
    hermes.answers["/brains/b1/recall"] = _http_error(401, "token expired on 2026-11-01")
    out = p.prefetch(QUESTION)
    assert "<mimirsynth-notice>" in out and "token expired on 2026-11-01" in out and "<mimirsynth-memory" not in out
    assert p.prefetch(QUESTION) == ""   # said once a session, not on every turn


def test_what_changed_arrives_once_at_session_start(hermes, monkeypatch):
    _configure(monkeypatch)
    hermes.answers["/brains/b1/news"] = {"text": "# What changed\n- the db moved to db02", "added": 1, "gone": 0}
    hermes.answers["/brains/b1/recall"] = {"context": ""}
    p = _start(hermes)
    news = [c for c in hermes.calls if c["path"] == "/brains/b1/news"]
    assert len(news) == 1 and news[0]["query"] == "limit=20&max_chars=4000" and news[0]["auth"] == "Bearer mst_reader"
    out = p.prefetch(QUESTION)
    assert out.startswith('<mimirsynth-news brain="b1">') and "db02" in out
    assert p.prefetch(QUESTION) == ""   # only the first turn
    hermes.calls.clear()
    _start(hermes, "s2", resumed=True)
    assert not [c for c in hermes.calls if c["path"].endswith("/news")]   # a resumed session already had them
    _start(hermes, "s3", agent_context="subagent")
    assert hermes.calls == []           # a subagent or a cron run asks for nothing
    hermes.answers["/brains/b1/news"] = {"text": "Nothing new", "added": 0, "gone": 0}
    assert _start(hermes, "s4").prefetch("hi") == ""


# --- tools and commands ---------------------------------------------------------------------------

def test_the_tools_search_and_propose_into_quarantine_redacted(hermes, monkeypatch):
    _configure(monkeypatch, NEWS="off")
    p = _start(hermes)
    hermes.answers["/brains/b1/recall"] = {"context": "## Facts\n- deploys go through ops/deploy.sh"}
    r = json.loads(p.handle_tool_call("mimirsynth_search", {"query": "deploy"}))
    assert "ops/deploy.sh" in r["context"] and hermes.calls[-1]["body"]["facts"] == 12
    hermes.answers["/brains/b1/proposals"] = {"id": 9, "status": "pending"}
    r = json.loads(p.handle_tool_call("mimirsynth_remember", {"title": "Deploy key moved", "content": f"The old key {GITHUB} was revoked.",
                                                              "confidence": 0.8}))
    assert r == {"id": 9, "status": "pending", "note": "waiting in quarantine for a curator"}
    c = hermes.calls[-1]
    assert c["auth"] == "Bearer mst_writer" and GITHUB not in json.dumps(c["body"]) and "[secret removed]" in c["body"]["body"]
    assert c["body"]["origin"] == "agent" and c["body"]["source_description"] == "hermes-agent" and c["body"]["confidence"] == 0.8
    hermes.answers["/brains/b1/proposals"] = _http_error(403, "this token cannot propose")
    assert "403" in json.loads(p.handle_tool_call("mimirsynth_remember", {"title": "x", "content": "y"}))["error"]
    hermes.answers["/brains/b1/proposals"] = urllib.error.URLError("refused")
    assert "Cannot reach" in json.loads(p.handle_tool_call("mimirsynth_remember", {"title": "x", "content": "y"}))["error"]
    assert "error" in json.loads(p.handle_tool_call("mimirsynth_search", {"query": " "}))


def test_the_commands_in_a_chat_and_in_a_terminal(hermes, monkeypatch, capsys):
    _configure(monkeypatch)
    hermes.answers["/brains/b1/whoami"] = {"brain": "b1", "name": "Team", "role": "reader", "version": "1.2.3",
                                           "token": {"name": "laptop", "scopes": ["recall"], "expires_at": None}}
    out = hermes.commands.slash("status")
    assert "role reader" in out and "server 1.2.3" in out and "Capture of what each session learned: off" in out
    hermes.answers["/brains/b1/proposals"] = {"id": 3, "status": "pending"}
    assert "Proposal #3: pending" in hermes.commands.slash("remember Backups :: The backup job runs at 03:00 now.")
    assert hermes.calls[-1]["body"]["name"] == "Backups" and hermes.calls[-1]["body"]["body"] == "The backup job runs at 03:00 now."
    assert "hermes mimirsynth setup" in hermes.commands.slash("setup") and "/mimirsynth status" in hermes.commands.slash("what")
    hermes.answers["/brains/b1/recall"] = {"context": "- found it"}
    args = types.SimpleNamespace(mimirsynth_command="search", query=["the", "backup"])
    assert hermes.cli.mimirsynth_command(args) == 0 and "found it" in capsys.readouterr().out
    assert hermes.commands.setup(interactive=False) == 1   # no terminal: setup never asks for tokens


# --- the optional capture -------------------------------------------------------------------------

def test_with_capture_off_nothing_is_written_or_sent(hermes, monkeypatch):
    _configure(monkeypatch, NEWS="off")
    p = _start(hermes)
    p.sync_turn(f"rotate the deploy key {GITHUB}", "Done. " * 200, session_id="s1", messages=_turn(str(hermes.tmp / "ops" / "deploy.sh")))
    p.on_session_end([])
    _start(hermes, "s2")
    assert not (hermes.home / "mimirsynth").exists() and hermes.calls == []


def _captured_session(h, sid="s1", answer="The deploy key now lives in Vaultwarden. " * 12):
    p = _start(h, sid)
    p.sync_turn(f"rotate the deploy key {GITHUB} on db02", answer, session_id=sid,
                messages=_turn(str(h.tmp / "ops" / "deploy.sh")) + _turn("", patch="*** Begin Patch\n*** Update File: ops/vars.yml\n"))
    p.on_session_end([])
    return p


def test_capture_sends_one_redacted_quarantined_proposal_per_session(hermes, monkeypatch):
    _configure(monkeypatch, CAPTURE="send", NEWS="off")
    _captured_session(hermes)
    rec = json.loads((hermes.home / "mimirsynth" / "sessions" / "s1.json").read_text(encoding="utf-8"))
    assert rec["ended"] and GITHUB not in json.dumps(rec) and set(rec["files"]) == {str(Path("ops") / "deploy.sh"), str(Path("ops") / "vars.yml")}
    assert not [c for c in hermes.calls if c["path"].endswith("/proposals")]   # nothing left the machine at the end of the session
    hermes.answers["/brains/b1/whoami"] = {"role": "contributor"}
    hermes.answers["/brains/b1/proposals"] = {"id": 7, "status": "pending"}
    _start(hermes, "s2")
    sent = [c for c in hermes.calls if c["path"] == "/brains/b1/proposals"]
    assert len(sent) == 1 and sent[0]["auth"] == "Bearer mst_writer"
    body = sent[0]["body"]
    assert GITHUB not in json.dumps(body) and "[secret removed]" in body["body"] and "deploy.sh" in body["body"]
    assert body["origin"] == "auto" and body["confidence"] == 0.3 and body["source_description"] == "hermes-agent session"
    assert body["name"].startswith(f"Hermes Agent: {hermes.tmp.name} — rotate the deploy key")
    _start(hermes, "s3")
    assert len([c for c in hermes.calls if c["path"] == "/brains/b1/proposals"]) == 1   # at most one per session


def test_capture_never_sends_with_a_curator_token_and_drafts_wait_for_review(hermes, monkeypatch):
    _configure(monkeypatch, CAPTURE="send", NEWS="off")
    _captured_session(hermes)
    hermes.answers["/brains/b1/whoami"] = {"role": "curator"}
    hermes.answers["/brains/b1/recall"] = {"context": ""}
    out = _start(hermes, "s2").prefetch(QUESTION)
    assert "contributor" in out and "<mimirsynth-notice>" in out and not [c for c in hermes.calls if c["path"].endswith("/proposals")]
    monkeypatch.setenv("MIMIRSYNTH_CAPTURE", "draft")
    out = _start(hermes, "s3").prefetch(QUESTION)
    assert "1 session draft(s) waiting" in out and not [c for c in hermes.calls if c["path"].endswith("/proposals")]
    code, text = hermes.commands.drafts()
    assert code == 0 and "Vaultwarden" in text and GITHUB not in text
    hermes.answers["/brains/b1/whoami"] = {"role": "contributor"}
    hermes.answers["/brains/b1/proposals"] = {"id": 11, "status": "pending"}
    assert hermes.commands.send_draft("s1") == (0, "Proposal #11: pending")
    assert hermes.commands.drafts()[1] == "No drafts waiting." and hermes.commands.send_draft("s1")[0] == 2


def test_switches_follow_the_work_and_a_session_not_worth_it_is_dropped(hermes, monkeypatch):
    _configure(monkeypatch, CAPTURE="draft", NEWS="off")
    sessions = hermes.home / "mimirsynth" / "sessions"
    p = _start(hermes, "s1")
    p.sync_turn("why does the backup job fail on sundays?", "Because the reindex runs at the same time. " * 12, session_id="s1")
    p.on_session_switch("s1b", parent_session_id="s1")            # a compression: the same work under another id
    assert not (sessions / "s1.json").exists() and json.loads((sessions / "s1b.json").read_text(encoding="utf-8"))["turns"] == 1
    p.on_session_switch("s2", reset=True)                         # /new: the old conversation is over, and a new one starts
    p._start.join(5)
    assert json.loads((sessions / "s1b.json").read_text(encoding="utf-8"))["ended"] and "1 session draft" in p.prefetch(QUESTION)
    p.sync_turn("what time is it there?", "Noon.", session_id="s2")
    p.on_session_end([])
    _start(hermes, "s3")
    assert not (sessions / "s2.json").exists() and (sessions / "s1b.json").exists()   # nothing changed and a short answer: dropped


# --- against a real MimirSynth --------------------------------------------------------------------

@pytest.fixture()
def real(agent_instance, monkeypatch, tmp_path):  # noqa: F811
    """The plugin pointed at a real MimirSynth on a local port: the shared file, as `hermes mimirsynth setup` writes it."""
    for k in ("URL", "BRAIN", "TOKEN", "WRITE_TOKEN", "CAPTURE", "NEWS", "RECALL"):
        monkeypatch.delenv(f"MIMIRSYNTH_{k}", raising=False)
    (tmp_path / "config.json").write_text(json.dumps({"url": agent_instance.url, "brain": agent_instance.brain, "timeout": 10,
                                                      "token": agent_instance.tokens["reader"],
                                                      "write_token": agent_instance.tokens["contributor"]}), encoding="utf-8")
    monkeypatch.setenv("MIMIRSYNTH_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    pkg = _load("mimirsynth_hermes_real")
    return types.SimpleNamespace(inst=agent_instance, provider=sys.modules["mimirsynth_hermes_real.provider"], pkg=pkg,
                                 home=tmp_path / "hermes", tmp=tmp_path)


def _real_start(r, session="s1"):
    p = r.provider.MimirSynthProvider()
    p.initialize(session, hermes_home=str(r.home), platform="cli", cwd=str(r.tmp))
    p._start.join(15)
    return p


def test_against_a_test_instance_recall_is_injected_and_remember_waits_in_quarantine(real):
    p = _real_start(real)
    assert p.is_available()
    out = p.prefetch("where does the production database run?")
    assert f'<mimirsynth-memory brain="{real.inst.brain}">' in out and "the contract brain answers: where does the production" in out
    assert real.inst.seen[-1] == "where does the production database run?"
    before = _proposals(real.inst)
    r = json.loads(p.handle_tool_call("mimirsynth_remember", {"title": "Deploy key moved",
                                                              "content": f"The deploy key lives in Vaultwarden; {GITHUB} was revoked."}))
    assert r["status"] == "pending" and _proposals(real.inst) == before + 1
    prop = real.inst.client.get(f"/api/brains/{real.inst.brain}/proposals/{r['id']}",
                                headers={"Authorization": f"Bearer {real.inst.tokens['curator']}"}).json()
    assert prop["status"] == "pending" and prop["origin"] == "agent" and GITHUB not in prop["body"]


def test_against_a_test_instance_capture_is_off_by_default_and_then_sends_once(real, monkeypatch):
    before = _proposals(real.inst)
    p = _real_start(real)
    p.sync_turn("rotate the deploy key", "The key now lives in Vaultwarden. " * 20, session_id="s1", messages=_turn("ops/deploy.sh"))
    p.on_session_end([])
    _real_start(real, "s2")
    assert _proposals(real.inst) == before and not (real.home / "mimirsynth").exists()   # off by default: nothing written or sent
    monkeypatch.setenv("MIMIRSYNTH_CAPTURE", "send")
    p = _real_start(real, "s3")
    p.sync_turn("rotate the deploy key", "The key now lives in Vaultwarden. " * 20, session_id="s3", messages=_turn("ops/deploy.sh"))
    p.on_session_end([])
    _real_start(real, "s4")
    _real_start(real, "s5")
    assert _proposals(real.inst) == before + 1


def test_against_a_test_instance_a_server_that_is_away_never_blocks_the_agent(real, monkeypatch):
    monkeypatch.setenv("MIMIRSYNTH_URL", f"http://127.0.0.1:{_free_port()}")
    monkeypatch.setenv("MIMIRSYNTH_TIMEOUT", "2")
    started = time.monotonic()
    p = _real_start(real)
    assert p.prefetch("where does the production database run?") == ""
    assert "Cannot reach" in json.loads(p.handle_tool_call("mimirsynth_search", {"query": "database"}))["error"]
    assert time.monotonic() - started < 8
