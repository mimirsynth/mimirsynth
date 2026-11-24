#!/usr/bin/env python3
"""The MimirSynth plugin's commands, also usable from a terminal.

  cli.py setup                      asks for the server, the brain and the tokens (hidden) and writes ~/.config/mimirsynth/config.json
  cli.py status                     connection, brain, role and expiry of each token, server version, capture mode, drafts, other hooks
  cli.py search <query…>            recall on demand, with more results than before each prompt
  cli.py remember --title T --content C [--confidence X]
                                    proposes a memory with the write token (redacted first)
  cli.py drafts                     the sessions the capture recorded and has not sent (capture = draft)
  cli.py send-draft <session>       proposes one of them; cli.py drop-draft <session> forgets it
  cli.py statusline [--remove]      adds MimirSynth's row to Claude Code's status line, unless ~/.claude/settings.json already has one
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mimir  # noqa: E402


def _ask(label: str, current: str = "", secret: bool = False) -> str:
    hint = " (leave empty to keep it)" if current else ""
    v = (getpass.getpass(f"{label}{hint}: ") if secret else input(f"{label}{f' [{current}]' if current else ''}: ")).strip()
    return v or current


def setup(a) -> int:
    c = {}
    try:
        c = json.loads(mimir.CONFIG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    c["url"] = (a.url or _ask("MimirSynth URL (https://…)", c.get("url", ""))).rstrip("/")
    c["brain"] = a.brain or _ask("Brain (its slug)", c.get("brain", ""))
    c["token"] = _ask("Reader token for recall (mst_…)", c.get("token", ""), secret=True)
    c["write_token"] = _ask("Contributor token to propose (optional)", c.get("write_token", ""), secret=True)
    mode = a.capture or _ask("Capture what each session learned: off, draft or send", c.get("capture", "off"))
    c["capture"] = mode if mode in mimir.CAPTURE_MODES else "off"
    mimir.CONFIG.parent.mkdir(parents=True, exist_ok=True)
    mimir.CONFIG.write_text(json.dumps({k: v for k, v in c.items() if v != ""}, indent=2), encoding="utf-8")
    try:
        os.chmod(mimir.CONFIG, 0o600)
    except OSError:
        pass
    print(f"Saved in {mimir.CONFIG}.\n")
    return status(a)


def _who(label: str, token: str) -> list[str]:
    if not token:
        return [f"{label}: not set"]
    try:
        w = mimir.call("GET", "/whoami", token=token)
    except mimir.ApiError as e:
        return [f"{label}: MimirSynth answered {e.status}: {e.detail}"]
    except Exception as e:  # noqa: BLE001
        return [f"{label}: cannot reach MimirSynth ({e})"]
    t = w.get("token") or {}
    exp = f", expires {str(t['expires_at'])[:10]}" if t.get("expires_at") else ", does not expire"
    return [f"{label}: «{t.get('name', '?')}», role {w.get('role')}, scopes {', '.join(t.get('scopes') or [])}{exp}",
            f"  brain «{w.get('name')}» ({w.get('brain')}), server {w.get('version')}"]


def status(_a=None) -> int:
    lines = [f"Configuration: {mimir.CONFIG}" + ("" if mimir.CONFIG.exists() else " (missing: run setup, or set MIMIRSYNTH_* variables)")]
    if not (mimir.cfg("url") and mimir.cfg("brain")):
        print("\n".join(lines + ["Not configured: url and brain are missing."]))
        return 1
    lines.append(f"Server: {mimir.cfg('url')} · brain: {mimir.cfg('brain')}")
    lines += _who("Recall token", mimir.cfg("token"))
    if mimir.cfg("write_token"):
        lines += _who("Write token", mimir.cfg("write_token"))
    lines.append(f"Recall before each prompt: {'on' if mimir.cfg('recall') else 'off'} (up to {mimir.cfg('max_chars')} characters, "
                 f"{mimir.cfg('timeout')} s) · what changed at session start: {'on' if mimir.cfg('news') else 'off'}")
    mode = mimir.capture_mode()
    lines.append(f"Capture of what each session learned: {mode}"
                 + (" (nothing about the sessions is written or sent)" if mode == "off" else ""))
    if mode != "off":
        recs = mimir.sessions()
        lines.append(f"  sessions recorded on this machine: {len(recs)}; drafts waiting: {sum(1 for r in recs if _draft(r))}")
    others = mimir.other_memory()
    if others:
        lines.append("Other memory hooks here: " + "; ".join(others))
    last = mimir.last_status()
    if last:
        lines.append(f"Last thing the memory did: {last['action']} ({time.strftime('%Y-%m-%d %H:%M', time.localtime(float(last['at'])))})")
    lines.append("Status row: " + ("on" if _ours(_settings().get("statusLine")) else "off (add it with: cli.py statusline)"))
    print("\n".join(lines))
    return 0


def search(a) -> int:
    q = " ".join(a.query).strip()
    if not q:
        print("Say what to look for.")
        return 2
    try:
        r = mimir.call("POST", "/recall", body={"query": q[:1500], "facts": 12, "chunks": 6, "max_chars": 12000}, token=mimir.cfg("token"),
                       timeout=max(float(mimir.cfg("timeout")), 15))
    except mimir.ApiError as e:
        print(f"MimirSynth answered {e.status}: {e.detail}")
        return 1
    print((r.get("context") or "").strip() or "MimirSynth has nothing on that.")
    return 0


def remember(a) -> int:
    body = {"name": mimir.redact(a.title)[:255], "body": mimir.redact(a.content), "source": "text", "source_description": "claude-code",
            "origin": "agent"}
    if a.confidence is not None:
        body["confidence"] = a.confidence
    try:
        r = mimir.call("POST", "/proposals", body=body, token=mimir.cfg("write_token") or mimir.cfg("token"), timeout=20)
    except Exception as e:  # noqa: BLE001
        health, what = mimir.failure(e)
        mimir.status("", health=health, action=f"proposal not sent: {what}")
        if not isinstance(e, mimir.ApiError):
            raise
        print(f"MimirSynth answered {e.status}: {e.detail}")
        return 1
    _proposed(r)
    print(f"Proposal #{r.get('id')}: {r.get('status')}" + (" (waiting for a curator)" if r.get("status") == "pending" else ""))
    return 0


def _proposed(r: dict) -> None:
    """The status row's last action after a proposal. It belongs to no session: a command does not know which one it runs in."""
    state = "queued for review" if r.get("status") == "pending" else str(r.get("status") or "sent")
    mimir.status("", health="ok", action=f"proposal #{r.get('id')} {state}")


def _draft(rec: dict) -> bool:
    return rec.get("ended") and not rec.get("sent") and mimir.worth(rec)


def drafts(_a) -> int:
    ds = [r for r in mimir.sessions() if _draft(r)]
    if not ds:
        print("No drafts waiting.")
        return 0
    for r in ds:
        p = mimir.proposal(r)
        print(f"=== {r['session']} · {time.strftime('%Y-%m-%d %H:%M', time.localtime(float(r.get('started') or 0)))}\n{p['name']}\n\n{p['body']}\n")
    return 0


def send_draft(a) -> int:
    rec = next((r for r in mimir.sessions() if r.get("session") == a.session), None)
    if not rec:
        print("No such draft.")
        return 2
    try:
        r = mimir.send(rec)
    except mimir.ApiError as e:
        print(f"MimirSynth answered {e.status}: {e.detail}")
        return 1
    _proposed(r)
    print(f"Proposal #{r.get('id')}: {r.get('status')}")
    return 0


def drop_draft(a) -> int:
    mimir.drop(a.session)
    print("Forgotten.")
    return 0


def _settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _settings() -> dict:
    try:
        s = json.loads(_settings_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:  # noqa: BLE001  (unreadable: never rewritten, see statusline)
        return {"_unreadable": True}
    return s if isinstance(s, dict) else {"_unreadable": True}


def _ours(line) -> bool:
    """Whether a `statusLine` is the one `statusline` added: it runs the copy next to the configuration."""
    return isinstance(line, dict) and mimir.statusline_copy().as_posix() in str(line.get("command") or "").replace(chr(92), "/")


def statusline(a) -> int:
    """A plugin cannot install a status line, so this copies the row's script next to the configuration, at a path that does not change
    with the plugin's version (session start keeps the copy up to date). It then adds `statusLine` to ~/.claude/settings.json, only when
    the user has none. With --remove it takes out only its own."""
    s = _settings()
    if s.get("_unreadable"):
        print(f"{_settings_path()} is not valid JSON: nothing was changed.")
        return 1
    dst = mimir.statusline_copy()
    command = f'python3 "{dst.as_posix()}"'   # on Windows Claude Code runs it through Git Bash: forward slashes
    current = s.get("statusLine")
    if a.remove:
        if not _ours(current):
            print("The status line is not MimirSynth's: nothing was changed." if current else "There is no status line to remove.")
            return 0
        del s["statusLine"]
        _save_settings(s)
        dst.unlink(missing_ok=True)
        print(f"MimirSynth's status row removed from {_settings_path()}.")
        return 0
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(mimir.STATUSLINE, dst)
    if _ours(current):
        print(f"MimirSynth's status row is already on ({_settings_path()}), and its script is up to date.")
        return 0
    if current:
        print(f"{_settings_path()} already has a status line, and it was left as it is. To show MimirSynth's row too, have your script "
              f"pass the JSON it reads on stdin to:\n  {command}\nand print what it prints.")
        return 0
    s["statusLine"] = {"type": "command", "command": command, "padding": 0}
    _save_settings(s)
    print(f"MimirSynth's status row added to {_settings_path()}. It shows after the next message. Remove it with: cli.py statusline --remove")
    return 0


def _save_settings(s: dict) -> None:
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.mimirsynth.tmp")
    tmp.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="cli.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup")
    s.add_argument("--url")
    s.add_argument("--brain")
    s.add_argument("--capture", choices=mimir.CAPTURE_MODES)
    s.set_defaults(fn=setup)
    sub.add_parser("status").set_defaults(fn=status)
    s = sub.add_parser("search")
    s.add_argument("query", nargs="*")
    s.set_defaults(fn=search)
    s = sub.add_parser("remember")
    s.add_argument("--title", required=True)
    s.add_argument("--content", required=True)
    s.add_argument("--confidence", type=float)
    s.set_defaults(fn=remember)
    sub.add_parser("drafts").set_defaults(fn=drafts)
    for name, fn in (("send-draft", send_draft), ("drop-draft", drop_draft)):
        s = sub.add_parser(name)
        s.add_argument("session")
        s.set_defaults(fn=fn)
    s = sub.add_parser("statusline")
    s.add_argument("--remove", action="store_true")
    s.set_defaults(fn=statusline)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
