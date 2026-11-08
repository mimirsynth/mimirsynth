"""What the MimirSynth plugin for Codex shares between its hooks and its commands, on top of the shared client library
(`mimirsynth_agent`, a copy of `integrations/shared/python/mimirsynth_agent` written by `integrations/shared/vendor.py`): the
configuration, calls to the API, secret redaction and the local record of each session for the optional capture. What is only
Codex's lives here: where the records are kept, how a session's proposal is labelled, how a finished session is read from Codex's own
session file (`rollout.py`), whether Codex trusts the plugin's hooks, and other memory in `$CODEX_HOME/config.toml`.

Configuration: `~/.config/mimirsynth/config.json`, shared with every MimirSynth agent integration, with `MIMIRSYNTH_<KEY>` environment
variables taking precedence and a `projects` map to use another brain in some folders (docs/AGENT_CLIENT.md).

Nothing here ever blocks Codex: every network call has a short timeout and fails open.
"""
from __future__ import annotations

import os
import re
import sys
import time
import urllib.request  # noqa: F401  (the library calls urllib.request.urlopen; tests replace it here)
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mimirsynth_agent as lib  # noqa: E402
import rollout  # noqa: E402
from mimirsynth_agent import capture  # noqa: E402
from mimirsynth_agent.client import ApiError  # noqa: E402,F401

AGENT, SOURCE = "Codex", "codex"   # how a captured session's proposal names the agent, for people and for machines
PLUGIN = "mimirsynth"              # the plugin's name, which prefixes its hooks' keys in Codex's trust list
CONFIG = lib.config_path()
CAPTURE_MODES = lib.CAPTURE_MODES
STALE_HOURS = 12   # a session whose end Codex never announced (it was killed) counts as over when its file is this old
MEMORY = re.compile(r"memor|cognee|mem0|graphiti|letta|zep\b|recall", re.I)
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
    """One call to `{url}/api/brains/{brain}{path}`. Raises ApiError with the server's message on an HTTP error, and anything else on a
    network error."""
    return lib.request(config(), method, path, body=body, token=token, timeout=timeout, query=query)


redact = lib.redact


# --- the local record of a session (only when capture is on) ------------------------------------

def store() -> capture.Sessions:
    """`~/.config/mimirsynth/state/codex/sessions`, next to the shared configuration: the hooks and the commands typed in a terminal
    find the same records."""
    return capture.Sessions(capture.default_dir(SOURCE, CONFIG))


def load(session: str) -> dict:
    return store().load(session)


def save(rec: dict) -> None:
    store().save(rec)


def sessions() -> list:
    return store().all()


def drop(session: str) -> None:
    store().drop(session)


worth = capture.worth
is_draft = capture.is_draft


def _relative(path: str, cwd: str) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(cwd or ".").resolve()))
    except (ValueError, OSError):
        return Path(path).name


def harvest(rec: dict, current: str | None = None, now: float | None = None) -> dict:
    """Completes the record of a finished session from Codex's session file: the task, the outcome and the files changed, redacted
    before they are written. A session still open is left as it is; one whose end never came (Codex was killed) counts as over once
    its file has not changed for STALE_HOURS. Returns the record, saved when it changed."""
    if rec.get("harvested") or rec.get("sent") or rec.get("session") == current:
        return rec
    path = Path(rec["transcript"]) if rec.get("transcript") else rollout.find(rec.get("session") or "")
    if not rec.get("ended"):
        try:
            last = path.stat().st_mtime if path else float(rec.get("started") or 0)
        except OSError:
            last = float(rec.get("started") or 0)
        if (now or time.time()) - last < STALE_HOURS * 3600:
            return rec
        rec["ended"] = True
    got = rollout.read(path) if path else {}
    cwd = rec.get("cwd") or got.get("cwd") or ""
    prompts = [p for p in got.get("prompts") or [] if not p.startswith("/")]
    if prompts and not rec.get("first_prompt"):
        rec["first_prompt"] = redact(prompts[0][:1500])
    if got.get("last_message"):
        rec["last_message"] = redact(got["last_message"][:6000])
    files = rec.get("files") or []
    for f in got.get("files") or []:
        rel = redact(_relative(f, cwd))
        if rel not in files:
            files.append(rel)
    rec.update(files=files, harvested=True, cwd=cwd, project=rec.get("project") or Path(cwd or ".").name)
    save(rec)
    return rec


def proposal(rec: dict) -> dict:
    """The proposal a session becomes: the task, the outcome and the files it changed. Already redacted when recorded."""
    return capture.proposal(rec, AGENT, SOURCE, cfg("capture_confidence"))


def send(rec: dict) -> dict:
    """Sends a recorded session as one proposal, only with a contributor token: a curator's would be approved at once."""
    return capture.send(client(), store(), rec, AGENT, SOURCE)


# --- Codex's own configuration ------------------------------------------------------------------

def codex_config() -> dict:
    """`$CODEX_HOME/config.toml` as a dict; `{}` when it is missing or unreadable, or this Python has no TOML reader (before 3.11)."""
    try:
        import tomllib
    except ImportError:
        return {}
    try:
        return tomllib.loads((rollout.codex_home() / "config.toml").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def hooks_trusted(conf: dict | None = None) -> bool | None:
    """Whether the person trusted this plugin's hooks in Codex (`/hooks`): Codex runs a plugin's hooks only once they are trusted, and
    again after each update. None when it cannot tell (no TOML reader)."""
    conf = codex_config() if conf is None else conf
    if not conf and sys.version_info < (3, 11):
        return None
    state = (conf.get("hooks") or {}).get("state") or {}
    return any(str(k).startswith(f"{PLUGIN}@") and (v or {}).get("trusted_hash") for k, v in state.items())


def other_memory(conf: dict | None = None) -> list:
    """Other memory that also feeds Codex, from its configuration: Codex's own memories, plugins and hooks that look like memory."""
    conf = codex_config() if conf is None else conf
    found = []
    if (conf.get("features") or {}).get("memories") is True:
        found.append("Codex memories ([features] memories = true)")
    for name, plugin in (conf.get("plugins") or {}).items():
        if (plugin or {}).get("enabled", True) and MEMORY.search(name) and not name.startswith(f"{PLUGIN}@"):
            found.append(name)
    for groups in ((conf.get("hooks") or {}).items()):
        event, value = groups
        if event == "state" or not isinstance(value, list):
            continue
        for group in value:
            for h in (group or {}).get("hooks") or []:
                cmd = str((h or {}).get("command") or "")
                if MEMORY.search(cmd):
                    found.append(cmd[:80])
    return sorted(set(found))
