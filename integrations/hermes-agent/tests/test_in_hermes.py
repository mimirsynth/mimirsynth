"""The MimirSynth plugin inside a real Hermes Agent (#372). Run by `.github/workflows/plugin-hermes-agent.yml`, which installs Hermes
Agent from its official repository at a release tag; skipped where Hermes is not installed.

The plugin is installed the way `hermes plugins install` leaves it (a folder named after the manifest under `$HERMES_HOME/plugins/`),
found and loaded by Hermes's own memory-provider discovery, and driven through Hermes's `MemoryManager`, against a small stand-in for a
MimirSynth server. The end-to-end tests against a real MimirSynth are in `api/tests/test_hermes_plugin.py`."""
import json
import shutil
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("agent.memory_manager", reason="needs Hermes Agent installed")

PLUGIN = Path(__file__).resolve().parents[1] / "plugin"
QUESTION = "how do we deploy the api service now?"


class Server:
    """A stand-in for MimirSynth: answers recall, news, whoami and proposals, and records what it got."""

    def __init__(self):
        self.calls = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self._answer()

            def do_POST(self):
                self._answer()

            def _answer(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n)) if n else None
                path = self.path.split("?")[0]
                outer.calls.append({"path": path, "auth": self.headers.get("Authorization"), "body": body})
                answer = {"/api/brains/b1/recall": {"context": "## Facts\n- the api deploys with ops/deploy.sh", "facts": [{}], "chunks": []},
                          "/api/brains/b1/news": {"text": "# What changed\n- the db moved to db02", "added": 1, "gone": 0},
                          "/api/brains/b1/whoami": {"brain": "b1", "role": "contributor"},
                          "/api/brains/b1/proposals": {"id": 5, "status": "pending"}}.get(path)
                data = json.dumps(answer if answer is not None else {"detail": "not found"}).encode()
                self.send_response(200 if answer is not None else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


@pytest.fixture()
def hermes(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    shutil.copytree(PLUGIN, home / "plugins" / "mimirsynth")   # what `hermes plugins install` leaves
    (home / "config.yaml").write_text("memory:\n  provider: mimirsynth\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    server = Server()
    monkeypatch.setenv("MIMIRSYNTH_CONFIG", str(tmp_path / "mimirsynth.json"))
    (tmp_path / "mimirsynth.json").write_text(json.dumps({"url": server.url, "brain": "b1", "token": "mst_reader",
                                                          "write_token": "mst_writer"}), encoding="utf-8")
    for k in ("URL", "BRAIN", "TOKEN", "WRITE_TOKEN", "CAPTURE"):
        monkeypatch.delenv(f"MIMIRSYNTH_{k}", raising=False)
    yield home, server
    server.httpd.shutdown()


def _manager(home):
    from agent.memory_manager import MemoryManager
    from agent.memory_provider import MemoryProvider
    from plugins.memory import discover_memory_providers, load_memory_provider

    assert ("mimirsynth", True) in [(name, available) for name, _, available in discover_memory_providers()]
    provider = load_memory_provider("mimirsynth")
    assert isinstance(provider, MemoryProvider) and provider.name == "mimirsynth" and provider.is_available()
    manager = MemoryManager()
    manager.add_provider(provider)
    manager.initialize_all(session_id="t1", platform="cli", hermes_home=str(home), agent_context="primary")
    return manager, provider


def test_hermes_finds_the_plugin_and_injects_the_recall_and_the_news(hermes):
    home, server = hermes
    manager, _ = _manager(home)
    assert "mimirsynth_remember" in manager.build_system_prompt()
    out = manager.prefetch_all(QUESTION, session_id="t1")
    assert '<mimirsynth-news brain="b1">' in out and "db02" in out
    assert '<mimirsynth-memory brain="b1">' in out and "ops/deploy.sh" in out
    recall = [c for c in server.calls if c["path"] == "/api/brains/b1/recall"]
    assert len(recall) == 1 and recall[0]["auth"] == "Bearer mst_reader" and recall[0]["body"]["query"] == QUESTION
    assert "MimirSynth" in manager.describe_recall()
    from agent.memory_context import build_memory_context_block
    assert "<mimirsynth-memory" in build_memory_context_block(out)   # Hermes keeps our blocks inside its own fence
    manager.shutdown_all()


def test_the_tools_go_through_hermes_and_remember_waits_in_quarantine(hermes):
    home, server = hermes
    manager, _ = _manager(home)
    assert {"mimirsynth_search", "mimirsynth_remember"} <= {s["name"] for s in manager.get_all_tool_schemas()}
    r = json.loads(manager.handle_tool_call("mimirsynth_remember", {"title": "Deploy key moved", "content": "It lives in Vaultwarden."}))
    assert r["status"] == "pending"
    sent = [c for c in server.calls if c["path"] == "/api/brains/b1/proposals"]
    assert len(sent) == 1 and sent[0]["auth"] == "Bearer mst_writer" and sent[0]["body"]["origin"] == "agent"
    assert "ops/deploy.sh" in json.loads(manager.handle_tool_call("mimirsynth_search", {"query": "deploy"}))["context"]
    manager.shutdown_all()


def test_capture_is_off_by_default_inside_hermes(hermes):
    home, server = hermes
    manager, _ = _manager(home)
    manager.sync_all("rotate the deploy key", "Done. " * 200, session_id="t1")
    manager.flush_pending(timeout=5)
    manager.on_session_end([])
    manager.shutdown_all()
    assert not (home / "mimirsynth").exists()
    assert not [c for c in server.calls if c["path"].endswith("/proposals")]


def test_a_server_that_is_away_never_blocks_hermes(hermes, monkeypatch):
    home, _ = hermes
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv("MIMIRSYNTH_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("MIMIRSYNTH_TIMEOUT", "2")
    started = time.monotonic()
    manager, _ = _manager(home)
    assert manager.prefetch_all(QUESTION, session_id="t1") == ""
    manager.shutdown_all()
    assert time.monotonic() - started < 8


def test_the_commands_are_wired_into_hermes(hermes, capsys):
    import argparse

    from plugins.memory import discover_plugin_cli_commands
    commands = discover_plugin_cli_commands()
    assert [c["name"] for c in commands] == ["mimirsynth"]
    parser = argparse.ArgumentParser()
    commands[0]["setup_fn"](parser)
    args = parser.parse_args(["search", "deploy"])
    assert args.func(args) == 0 and "ops/deploy.sh" in capsys.readouterr().out
