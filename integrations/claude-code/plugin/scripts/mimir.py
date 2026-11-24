"""What the MimirSynth plugin's hooks and commands share, on top of the shared client library (`mimirsynth_agent`, a copy of
`integrations/shared/python/mimirsynth_agent` written by `integrations/shared/vendor.py`): the configuration, calls to the API, secret
redaction and the local record of each session for the optional capture. What is only Claude Code's lives here: where the records are
kept, how a session's proposal is labelled and the other memory hooks in `~/.claude/settings.json`.

Configuration: `~/.config/mimirsynth/config.json`, shared with every MimirSynth agent integration, with `MIMIRSYNTH_<KEY>` environment
variables taking precedence and a `projects` map to use another brain in some folders (docs/AGENT_CLIENT.md):
  url, brain, token        the server, the brain's slug and an API token (reader is enough to recall)
  write_token              a contributor token, to propose (the capture never sends with a curator token)
  timeout                  seconds a call may take before it gives up (4)
  max_chars                most characters the recall injects before each prompt (4000)
  recall, news             on/off: recall before each prompt, what changed at session start (both on)
  capture                  off (default) | draft | send: what happens to what a session learned
  capture_confidence       the confidence the captured proposal declares (0.3)

Nothing here ever blocks Claude Code: every network call has a short timeout and fails open.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.request  # noqa: F401  (the library calls urllib.request.urlopen; tests replace it here)
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mimirsynth_agent as lib  # noqa: E402
from mimirsynth_agent import capture  # noqa: E402
from mimirsynth_agent.client import ApiError  # noqa: E402,F401

AGENT, SOURCE = "Claude Code", "claude-code"   # how a captured session's proposal names the agent, for people and for machines
CONFIG = lib.config_path()
DEFAULTS = lib.DEFAULTS
CAPTURE_MODES = lib.CAPTURE_MODES
KEEP_DAYS, WORTH_CHARS = capture.KEEP_DAYS, capture.WORTH_CHARS
MEMORY_PLUGINS = re.compile(r"memor|cognee|mem0|graphiti|letta|zep\b|recall", re.I)
CWD: str | None = None   # the session's folder, from the hook's input; the process's own when not set


def config() -> lib.Config:
    """The configuration as of now (the file is read again on every call, so a change applies at once)."""
    cwd = CWD
    if not cwd:
        try:
            cwd = os.getcwd()
        except OSError:   # the folder was removed under us: no project applies
            cwd = None
    return lib.Config(path=CONFIG, cwd=cwd)


def client() -> lib.Client:
    return lib.Client(config())


def cfg(key: str):
    return config().get(key)


def capture_mode() -> str:
    return config().capture_mode()


def configured() -> bool:
    return config().configured()


def call(method: str, path: str, body: dict | None = None, token: str | None = None, timeout: float | None = None, query: str = ""):
    """One call to `{url}/api/brains/{brain}{path}` (or to `/api{path}` when `path` starts with `//`). Raises ApiError with the server's
    message on an HTTP error, and anything else on a network error."""
    return lib.request(config(), method, path, body=body, token=token, timeout=timeout, query=query)


redact = lib.redact


# --- the local record of a session (only when capture is on) ------------------------------------

def _store() -> capture.Sessions:
    return capture.Sessions(Path(os.environ.get("CLAUDE_PLUGIN_DATA") or (CONFIG.parent / "state")) / "sessions")


def state_dir() -> Path:
    return _store().dir()


def load(session: str) -> dict:
    return _store().load(session)


def save(rec: dict) -> None:
    _store().save(rec)


def sessions() -> list:
    return _store().all()


def drop(session: str) -> None:
    _store().drop(session)


worth = capture.worth


def proposal(rec: dict) -> dict:
    """The proposal a session becomes: the task, the outcome and the files it changed. Already redacted when recorded."""
    return capture.proposal(rec, AGENT, SOURCE, cfg("capture_confidence"))


def send(rec: dict) -> dict:
    """Sends a recorded session as one proposal, only with a contributor token: a curator's would be approved at once."""
    return capture.send(client(), _store(), rec, AGENT, SOURCE)


# --- the status row (#481) ----------------------------------------------------------------------
# The hooks write what the memory did, per session, to small files next to the configuration; `statusline.py` only reads them. Never a
# token, a prompt or a fact: the brain, the token's role and expiry, the capture mode, the drafts, the health and the last action.

STATUS_KEEP_DAYS = 7
WHOAMI_HOURS = 1   # session start asks /whoami again only after this, per server, brain and token
STATUS_KEYS = ("configured", "brain", "role", "expires_at", "capture", "drafts", "health", "action")


def status_dir() -> Path:
    return CONFIG.parent / "status"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)   # the status line never reads a half-written file


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def status(session: str, **fields) -> None:
    """Merges `fields` into the session's status file (or the shared one, for an action outside any session). Never fails."""
    try:
        name = session if re.fullmatch(r"[\w.-]{1,128}", session or "") else "_shared"
        p = status_dir() / f"{name}.json"
        cur = _read_json(p)
        cur.update({k: v for k, v in fields.items() if k in STATUS_KEYS})
        if "action" in fields:
            cur["at"] = time.time()
        _write_json(p, cur)
    except Exception:  # noqa: BLE001
        pass


def last_status() -> dict:
    """The most recent action written on this machine, for `/mimirsynth:status`."""
    best: dict = {}
    try:
        for p in status_dir().glob("*.json"):
            s = _read_json(p)
            if s.get("action") and float(s.get("at") or 0) > float(best.get("at") or 0):
                best = s
    except Exception:  # noqa: BLE001
        pass
    return best


def prune_status(now: float | None = None) -> None:
    now = time.time() if now is None else now
    try:
        for p in status_dir().glob("*.json"):
            if now - p.stat().st_mtime > STATUS_KEEP_DAYS * 86400:
                p.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def whoami() -> dict:
    """The recall token's role, expiry and brain, from /whoami, asked at most once every WHOAMI_HOURS per server, brain and token. On a
    failure: {"health": "offline" | "rejected" | "error"} and nothing cached, so the next start asks again."""
    token = cfg("token") or ""
    key = hashlib.sha256(f"{cfg('url')}|{cfg('brain')}|{token}".encode()).hexdigest()[:16]
    cache = status_dir() / "_whoami.json"
    known = _read_json(cache).get(key) or {}
    if known and time.time() - float(known.get("at") or 0) < WHOAMI_HOURS * 3600:
        return {k: known.get(k) for k in ("role", "expires_at")} | {"health": "ok"}
    try:
        w = call("GET", "/whoami", token=token)
    except ApiError as e:
        return {"health": "rejected" if e.status in (401, 403) else "error"}
    except Exception:  # noqa: BLE001
        return {"health": "offline"}
    out = {"role": w.get("role"), "expires_at": (w.get("token") or {}).get("expires_at")}
    try:
        _write_json(cache, {key: {**out, "at": time.time()}})   # only the current key: a rotated token leaves nothing behind
    except Exception:  # noqa: BLE001
        pass
    return out | {"health": "ok"}


def failure(e: BaseException) -> tuple[str, str]:
    """A failed call as the row says it: (health, what happened)."""
    if isinstance(e, ApiError):
        if e.status in (401, 403):
            return "rejected", f"token rejected ({e.status})"
        return "error", f"server error {e.status}" if e.status >= 500 else f"error {e.status}"
    return "offline", "offline"


STATUSLINE = Path(__file__).resolve().parent / "statusline.py"


def statusline_copy() -> Path:
    """Where `cli.py statusline` puts the script: a path that does not change with the plugin's version."""
    return CONFIG.parent / "statusline.py"


def refresh_statusline() -> None:
    """An installed copy follows the plugin's own script when the plugin updates."""
    try:
        dst = statusline_copy()
        if dst.exists() and dst.read_bytes() != STATUSLINE.read_bytes():
            shutil.copyfile(STATUSLINE, dst)
    except Exception:  # noqa: BLE001
        pass


# --- other memory hooks on this machine ---------------------------------------------------------

def other_memory() -> list:
    """Other plugins or hooks that look like they inject memory too, from the user's settings; and the loose MimirSynth script, which
    would inject the same context twice."""
    found = []
    try:
        s = json.loads((Path.home() / ".claude" / "settings.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return found
    for name, on in (s.get("enabledPlugins") or {}).items():
        if on and MEMORY_PLUGINS.search(name) and not name.startswith("mimirsynth@"):
            found.append(name)
    for event in ("UserPromptSubmit", "SessionStart"):
        for group in (s.get("hooks") or {}).get(event, []):
            for h in group.get("hooks", []):
                cmd = str(h.get("command") or "")
                if "mimirsynth_recall.py" in cmd:
                    found.append("mimirsynth_recall.py (the loose script: remove it from settings.json, the plugin replaces it)")
                elif MEMORY_PLUGINS.search(cmd):
                    found.append(cmd[:80])
    return sorted(set(found))
