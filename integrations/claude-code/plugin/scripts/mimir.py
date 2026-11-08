"""What the MimirSynth plugin's hooks and commands share: the configuration, calls to the API, secret redaction and the local record of
each session for the optional capture.

Configuration: `~/.config/mimirsynth/config.json`, with the same keys as the loose scripts it replaces, and `MIMIRSYNTH_<KEY>`
environment variables taking precedence:
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

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import secretscan  # noqa: E402  (the server's own detector, copied as is: the same rules on both sides)

CONFIG = Path.home() / ".config" / "mimirsynth" / "config.json"
DEFAULTS = {"timeout": 4.0, "max_chars": 4000, "recall": True, "news": True, "capture": "off", "capture_confidence": 0.3}
CAPTURE_MODES = ("off", "draft", "send")
KEEP_DAYS = 14          # local session records older than this are dropped
WORTH_CHARS = 400       # a session without edits is only worth proposing if its last answer says this much
MEMORY_PLUGINS = re.compile(r"memor|cognee|mem0|graphiti|letta|zep\b|recall", re.I)


def _file() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def cfg(key: str):
    v = os.environ.get(f"MIMIRSYNTH_{key.upper()}")
    if v is None:
        v = _file().get(key.lower())
    d = DEFAULTS.get(key)
    if v is None or v == "":
        return d if d is not None else ""
    if isinstance(d, bool):
        return v if isinstance(v, bool) else str(v).strip().lower() not in ("0", "false", "off", "no")
    if isinstance(d, (int, float)) and not isinstance(d, bool):
        try:
            return type(d)(v)
        except (TypeError, ValueError):
            return d
    return v


def capture_mode() -> str:
    m = str(cfg("capture") or "off").lower()
    return m if m in CAPTURE_MODES else "off"


def configured() -> bool:
    return bool(cfg("url") and cfg("brain") and cfg("token"))


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"{status}: {detail}")
        self.status, self.detail = status, detail


def call(method: str, path: str, body: dict | None = None, token: str | None = None, timeout: float | None = None, query: str = ""):
    """One call to `{url}/api/brains/{brain}{path}` (or to `/api{path}` when `path` starts with `//`). Raises ApiError with the server's
    message on an HTTP error, and anything else on a network error."""
    url = str(cfg("url")).rstrip("/")
    full = f"{url}/api{path[1:]}" if path.startswith("//") else f"{url}/api/brains/{cfg('brain')}{path}"
    req = urllib.request.Request(full + (f"?{query}" if query else ""), method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout or float(cfg("timeout"))) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read() or b"{}").get("detail") or e.reason
        except Exception:  # noqa: BLE001
            detail = e.reason
        raise ApiError(e.code, str(detail)) from None


def redact(text: str) -> str:
    """The text with everything the server's detector finds, sure or possible, replaced by a marker. By patterns: not infallible."""
    text = text or ""
    found = secretscan.scan(text)
    return secretscan.redact(text, found, marker="[secret removed]", everything=True) if found else text


# --- the local record of a session (only when capture is on) ------------------------------------

def state_dir() -> Path:
    d = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or (CONFIG.parent / "state")) / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(session: str) -> Path:
    return state_dir() / (re.sub(r"[^\w.-]", "_", session or "unknown")[:120] + ".json")


def load(session: str) -> dict:
    try:
        return json.loads(_path(session).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"session": session, "files": [], "turns": 0, "started": time.time(), "ended": False, "sent": None}


def save(rec: dict) -> None:
    p = _path(rec["session"])
    p.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def sessions() -> list[dict]:
    out = []
    for p in sorted(state_dir().glob("*.json")):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if time.time() - float(rec.get("started") or 0) > KEEP_DAYS * 86400:
            p.unlink(missing_ok=True)
            continue
        out.append(rec)
    return out


def drop(session: str) -> None:
    _path(session).unlink(missing_ok=True)


def worth(rec: dict) -> bool:
    """Only sessions that changed something, or ended with a substantial answer, are proposed."""
    return bool(rec.get("files")) or len(rec.get("last_message") or "") >= WORTH_CHARS


def proposal(rec: dict) -> dict:
    """The proposal a session becomes: the task, the outcome and the files it changed. Already redacted when recorded."""
    project = rec.get("project") or "?"
    task = (rec.get("first_prompt") or "").strip()
    day = time.strftime("%Y-%m-%d", time.localtime(float(rec.get("started") or time.time())))
    files = rec.get("files") or []
    body = [f"Claude Code session in «{project}» ({day})."]
    if task:
        body += ["", f"Task: {task[:500]}"]
    if rec.get("last_message"):
        body += ["", "Outcome:", rec["last_message"][:3000]]
    if files:
        body += ["", "Files changed: " + ", ".join(files[:20]) + (f" and {len(files) - 20} more" if len(files) > 20 else "")]
    first = task.splitlines()[0][:80] if task else "session"
    return {"name": f"Claude Code: {project} — {first}"[:255], "body": "\n".join(body), "source": "text",
            "source_description": "claude-code session", "origin": "auto", "confidence": float(cfg("capture_confidence"))}


def send(rec: dict) -> dict:
    """Sends a recorded session as one proposal, only with a contributor token: a curator's would be approved at once."""
    token = cfg("write_token") or cfg("token")
    who = call("GET", "/whoami", token=token)
    if who.get("role") != "contributor":
        raise ApiError(403, f"the capture only sends with a contributor token, and this one is {who.get('role')}: its proposals would not "
                            "wait in quarantine")
    r = call("POST", "/proposals", body=proposal(rec), token=token, timeout=max(float(cfg("timeout")), 10))
    rec["sent"] = {"id": r.get("id"), "status": r.get("status"), "at": time.time()}
    save(rec)
    return r


# --- other memory hooks on this machine ---------------------------------------------------------

def other_memory() -> list[str]:
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
