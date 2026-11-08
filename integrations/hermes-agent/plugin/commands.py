"""The MimirSynth plugin's commands, shared by the terminal (`hermes mimirsynth …`), the chat (`/mimirsynth …`) and the agent's tools.

  setup                     asks for the server, the brain and the tokens (hidden, in a terminal only) and writes the shared configuration
  status                    connection, brain, role, scopes and expiry of each token, server version, capture mode, drafts
  search <query…>           recall on demand, with more results than before each turn
  remember <title> <content>  proposes a memory with the write token (redacted first): it waits in quarantine
  drafts                    the sessions the capture recorded and has not sent (capture = draft)
  send-draft <session>      proposes one of them; drop-draft <session> forgets it

Each returns its text (and the terminal its exit code); nothing here raises when MimirSynth is away.
"""
from __future__ import annotations

import getpass
import json
import os
import sys
import time

from . import mimirsynth_agent as lib
from .mimirsynth_agent import capture
from .provider import AGENT, SOURCE, config, hermes_home, store

SEARCH = {"facts": 12, "chunks": 6, "max_chars": 12000}   # more than the recall before each turn


def _ask(label: str, current: str = "", secret: bool = False) -> str:
    hint = " (leave empty to keep it)" if current else ""
    v = (getpass.getpass(f"{label}{hint}: ") if secret else input(f"{label}{f' [{current}]' if current else ''}: ")).strip()
    return v or current


def setup(interactive: bool = True, url: str = "", brain: str = "", capture_mode: str = "") -> int:
    """Writes `~/.config/mimirsynth/config.json` (or `MIMIRSYNTH_CONFIG`), readable only by its owner. Tokens are only asked in a
    terminal, hidden: never through the conversation."""
    path = lib.config_path(config().env)
    if not (interactive and sys.stdin and sys.stdin.isatty()):
        print(f"Run `hermes mimirsynth setup` in a terminal: it asks for the tokens hidden and writes {path}.")
        return 1
    c = lib.config.read_file(path)
    c["url"] = (url or _ask("MimirSynth URL (https://…)", str(c.get("url") or ""))).rstrip("/")
    c["brain"] = brain or _ask("Brain (its slug)", str(c.get("brain") or ""))
    c["token"] = _ask("Reader token for recall (mst_…)", str(c.get("token") or ""), secret=True)
    c["write_token"] = _ask("Contributor token to propose (optional)", str(c.get("write_token") or ""), secret=True)
    mode = capture_mode or _ask("Capture what each session learned: off, draft or send", str(c.get("capture") or "off"))
    c["capture"] = lib.config.coerce("capture", mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: v for k, v in c.items() if v != ""}, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    print(f"Saved in {path}.\n")
    code, text = status()
    print(text)
    return code


def _who(client: lib.Client, label: str, token: str) -> list:
    if not token:
        return [f"{label}: not set"]
    try:
        w = client.whoami(token)
    except lib.ApiError as e:
        return [f"{label}: MimirSynth answered {e.status}: {e.detail}"]
    except Exception as e:  # noqa: BLE001
        return [f"{label}: cannot reach MimirSynth ({e})"]
    t = w.get("token") or {}
    exp = f", expires {str(t['expires_at'])[:10]}" if t.get("expires_at") else ", does not expire"
    return [f"{label}: «{t.get('name', '?')}», role {w.get('role')}, scopes {', '.join(t.get('scopes') or [])}{exp}",
            f"  brain «{w.get('name')}» ({w.get('brain')}), server {w.get('version')}"]


def status(conf: lib.Config | None = None, home=None) -> tuple:
    conf = conf or config()
    lines = [f"Configuration: {conf.path}" + ("" if conf.path.exists() else " (missing: run `hermes mimirsynth setup`, or set "
                                                                           "MIMIRSYNTH_* variables)")]
    if not (conf.get("url") and conf.get("brain")):
        return 1, "\n".join(lines + ["Not configured: url and brain are missing."])
    lines.append(f"Server: {conf.get('url')} · brain: {conf.get('brain')}")
    client = lib.Client(conf)
    lines += _who(client, "Recall token", conf.get("token"))
    if conf.get("write_token"):
        lines += _who(client, "Write token", conf.get("write_token"))
    lines.append(f"Recall before each turn: {'on' if conf.get('recall') else 'off'} (up to {conf.get('max_chars')} characters, "
                 f"{conf.get('timeout')} s) · what changed at session start: {'on' if conf.get('news') else 'off'}")
    mode = conf.capture_mode()
    lines.append(f"Capture of what each session learned: {mode}" + (" (nothing about the sessions is written or sent)" if mode == "off" else ""))
    if mode != "off":
        recs = store(home or hermes_home()).all()
        lines.append(f"  sessions recorded for this Hermes profile: {len(recs)}; drafts waiting: {sum(1 for r in recs if capture.is_draft(r))}")
    return 0, "\n".join(lines)


def search_result(conf: lib.Config, query: str) -> dict:
    """What the `mimirsynth_search` tool answers: `{"context"}`, or `{"error"}`."""
    q = (query or "").strip()
    if not q:
        return {"error": "Say what to look for."}
    if not conf.configured():
        return {"error": "MimirSynth is not configured: run `hermes mimirsynth setup`."}
    try:
        r = lib.Client(conf).recall(q, facts=SEARCH["facts"], chunks=SEARCH["chunks"], max_chars=SEARCH["max_chars"],
                                    timeout=max(float(conf.get("timeout")), 15))
    except lib.ApiError as e:
        return {"error": f"MimirSynth answered {e.status}: {e.detail}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"Cannot reach MimirSynth ({e})."}
    return {"context": (r.get("context") or "").strip() or "MimirSynth has nothing on that."}


def remember_result(conf: lib.Config, title: str, content: str, confidence=None) -> dict:
    """What the `mimirsynth_remember` tool answers: `{"id", "status", "note"}`, or `{"error"}`. Redacted before it leaves."""
    title, content = (title or "").strip(), (content or "").strip()
    if not title or not content:
        return {"error": "A memory needs a title and a content."}
    if not (conf.get("url") and conf.get("brain") and (conf.get("write_token") or conf.get("token"))):
        return {"error": "MimirSynth is not configured: run `hermes mimirsynth setup`."}
    try:
        c = float(confidence) if confidence is not None and confidence != "" else None
        c = c if c is None or 0 <= c <= 1 else None
    except (TypeError, ValueError):
        c = None
    try:
        r = lib.Client(conf).remember(title, content, confidence=c, source_description=SOURCE)
    except lib.ApiError as e:
        return {"error": f"MimirSynth answered {e.status}: {e.detail}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"Cannot reach MimirSynth ({e})."}
    note = "waiting in quarantine for a curator" if r.get("status") == "pending" else str(r.get("status"))
    return {"id": r.get("id"), "status": r.get("status"), "note": note}


def search(query: str, conf: lib.Config | None = None) -> tuple:
    r = search_result(conf or config(), query)
    return (1, r["error"]) if "error" in r else (0, r["context"])


def remember(title: str, content: str, confidence=None, conf: lib.Config | None = None) -> tuple:
    r = remember_result(conf or config(), title, content, confidence)
    return (1, r["error"]) if "error" in r else (0, f"Proposal #{r['id']}: {r['status']}"
                                                     + (" (waiting for a curator)" if r["status"] == "pending" else ""))


def drafts(conf: lib.Config | None = None, home=None) -> tuple:
    conf = conf or config()
    ds = [r for r in store(home or hermes_home()).all() if capture.is_draft(r)]
    if not ds:
        return 0, "No drafts waiting."
    out = []
    for r in ds:
        p = capture.proposal(r, AGENT, SOURCE, conf.get("capture_confidence"))
        day = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(r.get("started") or 0)))
        out.append(f"=== {r['session']} · {day}\n{p['name']}\n\n{p['body']}\n")
    return 0, "\n".join(out)


def send_draft(session: str, conf: lib.Config | None = None, home=None) -> tuple:
    sessions = store(home or hermes_home())
    rec = next((r for r in sessions.all() if r.get("session") == session and capture.is_draft(r)), None)
    if not rec:
        return 2, "No such draft."
    try:
        r = capture.send(lib.Client(conf or config()), sessions, rec, AGENT, SOURCE)
    except lib.ApiError as e:
        return 1, f"MimirSynth answered {e.status}: {e.detail}"
    except Exception as e:  # noqa: BLE001
        return 1, f"Cannot reach MimirSynth ({e})."
    return 0, f"Proposal #{r.get('id')}: {r.get('status')}"


def drop_draft(session: str, home=None) -> tuple:
    store(home or hermes_home()).drop(session)
    return 0, "Forgotten."


USAGE = ("/mimirsynth status · /mimirsynth search <query> · /mimirsynth remember <title> :: <content> · /mimirsynth drafts · "
         "/mimirsynth send-draft <session> · /mimirsynth drop-draft <session>. Setup: `hermes mimirsynth setup`, in a terminal.")


def slash(raw_args: str = "") -> str:
    """`/mimirsynth …` in a chat. Never asks for tokens: setup is only in a terminal."""
    try:
        cmd, _, rest = (raw_args or "").strip().partition(" ")
        rest = rest.strip()
        if cmd in ("", "status"):
            return status()[1]
        if cmd == "search":
            return search(rest)[1]
        if cmd == "remember":
            title, sep, content = rest.partition("::")
            if not sep:
                title, content = rest.splitlines()[0][:80] if rest else "", rest
            return remember(title.strip(), content.strip())[1]
        if cmd == "drafts":
            return drafts()[1]
        if cmd == "send-draft":
            return send_draft(rest)[1]
        if cmd == "drop-draft":
            return drop_draft(rest)[1]
        if cmd == "setup":
            return "Run `hermes mimirsynth setup` in a terminal: it asks for the tokens hidden, never through the chat."
        return USAGE
    except Exception as e:  # noqa: BLE001  (a command never breaks the chat)
        return f"MimirSynth: {e}"
