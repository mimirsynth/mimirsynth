"""The optional capture of what a session learned (docs/AGENT_CLIENT.md), off unless `capture` says otherwise.

  off    (the default) nothing about a session is written or sent
  draft  each session is kept on this machine, already redacted, until the person reviews it
  send   at the next session start, each finished session worth it becomes one proposal, in quarantine

A session is recorded in a JSON file of its own, readable only by the person, in a folder each integration chooses. Only sessions that
changed files, or ended with a substantial answer, are worth proposing; at most one proposal per session, and only with a contributor
token, because a curator's would skip quarantine.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from .client import ApiError, Client

KEEP_DAYS = 14          # local session records older than this are dropped
WORTH_CHARS = 400       # a session without edits is only worth proposing if its last answer says this much


def default_dir(agent: str, conf_path=None) -> Path:
    """Where an integration keeps its session records unless its agent gives it a folder: `~/.config/mimirsynth/state/<agent>/sessions`."""
    from .config import config_path
    return Path(conf_path or config_path()).parent / "state" / agent / "sessions"


class Sessions:
    """The session records of one integration, one file each. The folder is only created when a record is written or listed."""

    def __init__(self, directory):
        self.base = Path(directory)

    def dir(self) -> Path:
        self.base.mkdir(parents=True, exist_ok=True)
        return self.base

    def path(self, session: str) -> Path:
        return self.dir() / (re.sub(r"[^\w.-]", "_", session or "unknown")[:120] + ".json")

    def load(self, session: str) -> dict:
        try:
            return json.loads(self.path(session).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {"session": session, "files": [], "turns": 0, "started": time.time(), "ended": False, "sent": None}

    def save(self, rec: dict) -> None:
        p = self.path(rec["session"])
        p.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass

    def all(self) -> list:
        """Every record, oldest file name first; those older than KEEP_DAYS are deleted on the way."""
        out = []
        for p in sorted(self.dir().glob("*.json")):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if time.time() - float(rec.get("started") or 0) > KEEP_DAYS * 86400:
                p.unlink(missing_ok=True)
                continue
            out.append(rec)
        return out

    def drop(self, session: str) -> None:
        self.path(session).unlink(missing_ok=True)


def worth(rec: dict) -> bool:
    """Only sessions that changed something, or ended with a substantial answer, are proposed."""
    return bool(rec.get("files")) or len(rec.get("last_message") or "") >= WORTH_CHARS


def is_draft(rec: dict) -> bool:
    """A finished session worth proposing that has not been sent."""
    return bool(rec.get("ended") and not rec.get("sent") and worth(rec))


def proposal(rec: dict, agent: str, source: str, confidence: float) -> dict:
    """The proposal a session becomes: the task, the outcome and the files it changed, already redacted when recorded. `agent` names
    the agent for people («Claude Code»), `source` for machines («claude-code»)."""
    project = rec.get("project") or "?"
    task = (rec.get("first_prompt") or "").strip()
    day = time.strftime("%Y-%m-%d", time.localtime(float(rec.get("started") or time.time())))
    files = rec.get("files") or []
    body = [f"{agent} session in «{project}» ({day})."]
    if task:
        body += ["", f"Task: {task[:500]}"]
    if rec.get("last_message"):
        body += ["", "Outcome:", rec["last_message"][:3000]]
    if files:
        body += ["", "Files changed: " + ", ".join(files[:20]) + (f" and {len(files) - 20} more" if len(files) > 20 else "")]
    first = task.splitlines()[0][:80] if task else "session"
    return {"name": f"{agent}: {project} — {first}"[:255], "body": "\n".join(body), "source": "text",
            "source_description": f"{source} session", "origin": "auto", "confidence": float(confidence)}


def send(client: Client, store: Sessions, rec: dict, agent: str, source: str) -> dict:
    """Sends a recorded session as one proposal, only with a contributor token: a curator's would be approved at once."""
    conf = client.conf
    token = client.write_token()
    who = client.whoami(token)
    if who.get("role") != "contributor":
        raise ApiError(403, f"the capture only sends with a contributor token, and this one is {who.get('role')}: its proposals would not "
                            "wait in quarantine")
    r = client.propose(proposal(rec, agent, source, conf.get("capture_confidence")), token=token,
                       timeout=max(float(conf.get("timeout")), 10))
    rec["sent"] = {"id": r.get("id"), "status": r.get("status"), "at": time.time()}
    store.save(rec)
    return r
