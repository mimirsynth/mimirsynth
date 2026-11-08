"""The configuration contract every MimirSynth agent integration shares (docs/AGENT_CLIENT.md).

One file, `~/.config/mimirsynth/config.json` (or the path in `MIMIRSYNTH_CONFIG`), serves every agent. A value is looked up, first hit
wins, in:
  1. the environment variable `MIMIRSYNTH_<KEY>`;
  2. the entry of `projects` whose folder holds the working directory (the deepest one when several do);
  3. the top level of the file;
  4. the default below.
An empty value (an unset or blank variable, `""` or `null` in the file) counts as not given. A value that cannot be read as its type
falls back to the default, so a typo never stops an agent.

Standard library only, Python 3.8 or later: plugins vendor this package as it is.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

ENV_PREFIX = "MIMIRSYNTH_"
PATH_ENV = "MIMIRSYNTH_CONFIG"
CAPTURE_MODES = ("off", "draft", "send")
CAPTURE_ALIASES = {"drafts": "draft", "auto": "send"}
DEFAULTS = {
    "url": "",                  # the server, https://…
    "brain": "",                # the brain's slug
    "token": "",                # an API token for that brain (reader is enough to recall)
    "write_token": "",          # a contributor token, to propose; empty: `token` is used
    "timeout": 4.0,             # seconds a call may take before it gives up
    "max_chars": 4000,          # most characters the recall before each prompt injects
    "recall": True,             # recall before each prompt
    "news": True,               # what changed in the brain, at session start
    "capture": "off",           # off | draft | send: what happens to what a session learned
    "capture_confidence": 0.3,  # the confidence a captured proposal declares
}
KEYS = tuple(DEFAULTS)
FALSE = ("0", "false", "off", "no")
_INT = re.compile(r"^\s*[+-]?\d+\s*$")
_FLOAT = re.compile(r"^\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\s*$")
_VALID = {"timeout": lambda n: n > 0, "max_chars": lambda n: n > 0, "capture_confidence": lambda n: 0 <= n <= 1}


def default_path() -> Path:
    return Path.home() / ".config" / "mimirsynth" / "config.json"


def config_path(env=None) -> Path:
    """The file: `MIMIRSYNTH_CONFIG` when set, otherwise `~/.config/mimirsynth/config.json` (on every system, Windows included)."""
    p = (os.environ if env is None else env).get(PATH_ENV) or ""
    return Path(p.strip()).expanduser() if p.strip() else default_path()


def read_file(path) -> dict:
    """The file's JSON object; `{}` when it is missing, unreadable or not an object."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(p)))


def project_entry(data: dict, cwd) -> dict:
    """The entry of `projects` (a map from a folder to an object with any of the keys) whose folder is `cwd` or holds it; the deepest
    one wins. Folders are compared as absolute paths, without following links, and without case on Windows."""
    projects = data.get("projects") if isinstance(data, dict) else None
    if not cwd or not isinstance(projects, dict):
        return {}
    here = _norm(str(cwd))
    best, depth = {}, -1
    for root, entry in projects.items():
        if not isinstance(root, str) or not root.strip() or not isinstance(entry, dict):
            continue
        r = _norm(root.strip())
        if (here == r or here.startswith(r.rstrip("\\/") + os.sep)) and len(r) > depth:
            best, depth = entry, len(r)
    return best


def _given(v) -> bool:
    return v is not None and not (isinstance(v, str) and not v.strip())


def coerce(key: str, value):
    """`value` read as the type of `key`'s default; the default when it is not given or cannot be read."""
    d = DEFAULTS.get(key, "")
    if not _given(value):
        return d
    if key == "capture":
        m = str(value).strip().lower() if isinstance(value, str) else ""
        m = CAPTURE_ALIASES.get(m, m)
        return m if m in CAPTURE_MODES else "off"
    if isinstance(d, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() not in FALSE
        return d
    if isinstance(d, (int, float)):
        integer = isinstance(d, int)
        if isinstance(value, bool):
            return d
        if isinstance(value, (int, float)):
            n = value
        elif isinstance(value, str) and (_INT if integer else _FLOAT).match(value):
            n = int(value) if integer else float(value)
        else:
            return d
        if not math.isfinite(n):
            return d
        n = int(n) if integer else float(n)
        return n if _VALID.get(key, lambda _: True)(n) else d
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return d
    return value.strip() if isinstance(value, str) else str(value)


class Config:
    """The configuration as one agent sees it from one working directory. Read once when built: build another to see changes."""

    def __init__(self, path=None, env=None, cwd=None):
        self.env = dict(os.environ if env is None else env)
        self.path = Path(path) if path is not None else config_path(self.env)
        self.file = read_file(self.path)
        self.cwd = str(cwd) if cwd else None
        self.project = project_entry(self.file, self.cwd)

    def lookup(self, key: str):
        """(raw value, where it came from: env, project, file or default)."""
        key = key.lower()
        v = self.env.get(ENV_PREFIX + key.upper())
        if _given(v):
            return v, "env"
        if key != "projects":
            for layer, name in ((self.project, "project"), (self.file, "file")):
                if _given(layer.get(key)):
                    return layer.get(key), name
        return None, "default"

    def get(self, key: str):
        return coerce(key.lower(), self.lookup(key)[0])

    def source(self, key: str) -> str:
        return self.lookup(key)[1]

    def capture_mode(self) -> str:
        return self.get("capture")

    def configured(self) -> bool:
        """Enough to recall: a server, a brain and a token."""
        return bool(self.get("url") and self.get("brain") and self.get("token"))

    def values(self) -> dict:
        return {k: self.get(k) for k in KEYS}


def load(path=None, env=None, cwd=None) -> Config:
    return Config(path=path, env=env, cwd=cwd)
