"""Reads what the capture needs from a Codex session file, the «rollout» Codex writes to `$CODEX_HOME/sessions/YYYY/MM/DD/`:
the task (the first prompt), the outcome (the last answer) and the files changed. Never the transcript itself.

A rollout is one JSON object per line, `{"timestamp", "type", "payload"}`. What this module reads, in both of Codex's history modes:
  session_meta                       the session's id and folder (`cwd`)
  event_msg user_message             a prompt (legacy history)
  event_msg item_completed           a prompt (`UserMessage`), an answer (`AgentMessage`) or an edit (`FileChange`, with its `status`)
  event_msg patch_apply_end          an edit (legacy history, with `success`)
  event_msg task_complete            the end of a turn, with `last_agent_message`
  response_item message              a prompt or an answer, as the model saw it (the fallback)
A line it does not know, or cannot read, is skipped: a newer Codex never breaks the capture, it only finds less. Compressed rollouts
(`.jsonl.zst`) are not read. Standard library only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def codex_home(env=None) -> Path:
    """`CODEX_HOME` when set, otherwise `~/.codex`."""
    p = ((os.environ if env is None else env).get("CODEX_HOME") or "").strip()
    return Path(p).expanduser() if p else Path.home() / ".codex"


def find(session: str, home: Path | None = None) -> Path | None:
    """The rollout of a session by its id, among the live and the archived sessions; None when there is none."""
    home = home or codex_home()
    if not session:
        return None
    for folder in ("sessions", "archived_sessions"):
        base = home / folder
        if base.is_dir():
            for p in sorted(base.rglob(f"rollout-*{session}.jsonl"), reverse=True):
                return p
    return None


def _texts(content, kinds=("input_text", "output_text", "text", "Text")) -> str:
    out = []
    for c in content or []:
        if isinstance(c, dict) and c.get("type") in kinds and isinstance(c.get("text"), str):
            out.append(c["text"])
    return "\n".join(out).strip()


def _injected(text: str) -> bool:
    """What Codex itself puts in the conversation as the user's (the environment, AGENTS.md, skills): it starts with a tag or a
    heading Codex writes, not with what the person typed."""
    t = text.lstrip()
    return t.startswith(("<", "# AGENTS.md instructions"))


def read(path) -> dict:
    """`{"cwd", "prompts", "last_message", "files"}` from a rollout; empty values for what is not there. `files` are the paths of the
    edits that were applied, as Codex wrote them (absolute), in order and without repeats."""
    out = {"cwd": "", "prompts": [], "last_message": "", "files": []}
    events_prompts, fallback_prompts, fallback_answer = [], [], ""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or not isinstance(rec.get("payload"), dict):
            continue
        kind, p = rec.get("type"), rec["payload"]
        if kind in ("session_meta", "turn_context") and not out["cwd"]:
            out["cwd"] = str(p.get("cwd") or "")
        elif kind == "event_msg":
            t = p.get("type")
            if t == "user_message" and isinstance(p.get("message"), str):
                events_prompts.append(p["message"].strip())
            elif t in ("task_complete", "turn_complete") and isinstance(p.get("last_agent_message"), str) and p["last_agent_message"].strip():
                out["last_message"] = p["last_agent_message"].strip()
            elif t == "agent_message" and isinstance(p.get("message"), str) and p["message"].strip():
                fallback_answer = p["message"].strip()
            elif t == "patch_apply_end" and p.get("success"):
                _add_files(out["files"], p.get("changes"))
            elif t == "item_completed" and isinstance(p.get("item"), dict):
                item = p["item"]
                if item.get("type") == "UserMessage":
                    events_prompts.append(_texts(item.get("content")))
                elif item.get("type") == "AgentMessage" and _texts(item.get("content")):
                    fallback_answer = _texts(item.get("content"))
                elif item.get("type") == "FileChange" and str(item.get("status") or "").lower() == "completed":
                    _add_files(out["files"], item.get("changes"))
        elif kind == "response_item" and p.get("type") == "message":
            text = _texts(p.get("content"))
            if p.get("role") == "user" and text and not _injected(text):
                fallback_prompts.append(text)
            elif p.get("role") == "assistant" and text:
                fallback_answer = text
    out["prompts"] = [t for t in (events_prompts or fallback_prompts) if t]
    out["last_message"] = out["last_message"] or fallback_answer
    return out


def _add_files(files: list, changes) -> None:
    if isinstance(changes, dict):
        for path, change in changes.items():
            for p in (path, (change or {}).get("move_path") if isinstance(change, dict) else None):
                if isinstance(p, str) and p and p not in files:
                    files.append(p)
