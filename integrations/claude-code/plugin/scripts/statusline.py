#!/usr/bin/env python3
"""MimirSynth's row in Claude Code's status line (#481): the server's health, the brain, the token's role, the capture mode and what
the memory last did in this session.

  ● mimirsynth  seismenos · contributor · capture off · recall: 4 facts

It only reads what the plugin's hooks wrote for this session (`<config folder>/status/<session>.json`, see `mimir.status`): it makes no
network call and never reads the configuration or its tokens, so it can run after every message. Claude Code passes the session on stdin.
`cli.py statusline` copies this file to `~/.config/mimirsynth/statusline.py` and points `statusLine` in `~/.claude/settings.json` at
it, since a plugin cannot install a status line and its own folder changes with every version. Standard library only; it never fails.

  ●  green: the last call worked · amber: the recall token expires within EXPIRY_DAYS days · red: unreachable, rejected or failing
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

EXPIRY_DAYS = 7   # a token that expires sooner shows amber, with the days left
_SESSION = re.compile(r"[A-Za-z0-9][\w.-]{0,127}")   # as `mimir.SESSION`: a leading «_» is a shared file, never a session
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
FIELD_CHARS = 80
COLOURS = {"green": "\033[32m", "amber": "\033[33m", "red": "\033[31m", "grey": "\033[90m"}
RESET = "\033[0m"


def status_dir(env=None) -> Path:
    """Next to the shared configuration, which `MIMIRSYNTH_CONFIG` may move (the same rule as the plugins' `config_path`)."""
    p = ((os.environ if env is None else env).get("MIMIRSYNTH_CONFIG") or "").strip()
    return (Path(p).expanduser() if p else Path.home() / ".config" / "mimirsynth" / "config.json").parent / "status"


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001  (missing, half-written or not JSON: as if empty)
        return {}
    return data if isinstance(data, dict) else {}


def days_left(expires_at, now: float | None = None) -> int | None:
    """Whole days until a token's expiry (negative once expired); None when it does not expire or the date is unreadable."""
    try:
        exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return int((exp.timestamp() - (time.time() if now is None else now)) // 86400)


def _text(v, n: int = FIELD_CHARS) -> str:
    """A field as printed: a file someone else wrote could hold terminal escapes or new lines; the row has neither."""
    return "".join(c for c in _CONTROL.sub("", str(v)) if unicodedata.category(c) not in ("Cf", "Zl", "Zp"))[:n]


def health(s: dict, now: float | None = None) -> str:
    if s.get("health") in ("offline", "rejected", "error"):
        return "red"
    left = days_left(s.get("expires_at"), now) if s.get("expires_at") else None
    if left is not None and left < EXPIRY_DAYS:
        return "red" if left < 0 else "amber"
    return "green" if s.get("health") == "ok" else "grey"


def row(s: dict, colour: bool = True, now: float | None = None) -> str:
    """The line for one session's status (`{}` when the hooks have written nothing yet)."""
    dot = "●"
    if colour:
        dot = f"{COLOURS[health(s, now)]}●{RESET}"
    if not s:
        return f"{dot} mimirsynth  no activity yet"
    if s.get("configured") is False:
        return f"{dot} mimirsynth  not configured: run /mimirsynth:setup"
    parts = [_text(s["brain"])] if s.get("brain") else []
    if s.get("role"):
        left = days_left(s.get("expires_at"), now) if s.get("expires_at") else None
        parts.append(_text(s["role"]) + ("" if left is None or left >= EXPIRY_DAYS else " · token expired" if left < 0
                                         else " · token expires today" if left == 0
                                         else f" · token expires in {left} day{'' if left == 1 else 's'}"))
    if s.get("capture"):
        n = s.get("drafts") if isinstance(s.get("drafts"), int) and not isinstance(s.get("drafts"), bool) else 0
        parts.append(f"capture {_text(s['capture'], 16)}" + (f" · {n} draft{'' if n == 1 else 's'}" if n > 0 else ""))
    if s.get("action"):
        parts.append(_text(s["action"]))
    return f"{dot} mimirsynth  " + " · ".join(parts)


def current(session: str, base: Path | None = None) -> dict:
    """What the hooks wrote for this session, with a newer action that belongs to no session (a proposal from /mimirsynth:remember)."""
    base = status_dir() if base is None else base
    s = _read(base / f"{session}.json") if _SESSION.fullmatch(session or "") else {}
    shared = _read(base / "_shared.json")
    if shared.get("action") and float(shared.get("at") or 0) > float(s.get("at") or 0):
        s = {**s, "action": shared["action"], "at": shared["at"], **({"health": shared["health"]} if shared.get("health") else {})}
    return s


def _print(text: str) -> None:
    """UTF-8 whatever the console's code page: on Windows Python would otherwise fail to print «●»."""
    out = getattr(sys.stdout, "buffer", None)
    if out is None:   # a stream with no bytes underneath (a test's capture)
        print(text)
        return
    out.write((text + "\n").encode("utf-8"))
    out.flush()


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        session = str(data.get("session_id") or "") if isinstance(data, dict) else ""
        _print(row(current(session), colour=not os.environ.get("NO_COLOR")))
    except Exception:  # noqa: BLE001  (a status line never breaks the window)
        _print("mimirsynth")
    return 0


if __name__ == "__main__":
    sys.exit(main())
