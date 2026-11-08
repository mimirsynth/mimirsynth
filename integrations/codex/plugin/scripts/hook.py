#!/usr/bin/env python3
"""The MimirSynth plugin's hooks for Codex. One script, the event as its argument:

  session-start   what changed in the brain since the last session (`/news`), a warning if other memory also feeds Codex, and, with
                  capture on, the sessions that ended are read from Codex's session files and become proposals (send) or wait as
                  drafts (draft)
  prompt          the recall for the prompt, inside <mimirsynth-memory>, before the model reads it; with capture on, the session is
                  noted so that its file can be read once it is over
  session-end     (capture on) marks the session as over; nothing leaves the machine here (Codex gives this hook at most 3 s)

Every hook fails open: whatever goes wrong, it exits 0 and Codex carries on. With capture off (the default) nothing about the session is
written, read or sent.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mimir  # noqa: E402

CONTEXT_MAX = 9500   # characters; Codex moves a longer additionalContext to a file and injects only a preview


def _out(context: str = "", event: str = "", message: str = "") -> None:
    out: dict = {}
    if context:
        out["hookSpecificOutput"] = {"hookEventName": event, "additionalContext": context[:CONTEXT_MAX]}
    if message:
        out["systemMessage"] = message
    if out:
        print(json.dumps(out))   # ASCII: the console's encoding (cp1252 on Windows) never gets in the way


def _capture(current: str | None, messages: list) -> None:
    """The sessions that ended become proposals (send) or drafts (draft); those not worth it are forgotten."""
    waiting = 0
    for rec in mimir.sessions():
        if rec.get("session") == current or rec.get("sent"):
            continue
        rec = mimir.harvest(rec, current)
        if not rec.get("ended"):
            continue
        if not mimir.worth(rec):
            mimir.drop(rec["session"])
        elif mimir.capture_mode() == "send":
            try:
                mimir.send(rec)
            except mimir.ApiError as e:
                messages.append(f"MimirSynth did not propose the last session: {e.detail}")
                break
            except Exception:  # noqa: BLE001  (the server is away: it is tried again at the next start)
                break
        else:
            waiting += 1
    if waiting:
        messages.append(f"MimirSynth: {waiting} session draft(s) waiting; review them with $mimirsynth:remember.")


def session_start(data: dict) -> None:
    messages, context = [], []
    others = mimir.other_memory()
    if others:
        messages.append("MimirSynth: other memory also feeds Codex here (" + "; ".join(others) + "). "
                        "MimirSynth's blocks are marked <mimirsynth-memory> and <mimirsynth-news>.")
    current = data.get("session_id")
    if mimir.configured() and mimir.capture_mode() != "off":
        if data.get("source") == "resume" and current:   # a resumed session is not over
            rec = mimir.load(current)
            if rec.get("ended") and not rec.get("sent"):
                rec.update(ended=False, harvested=False)
                mimir.save(rec)
        _capture(current, messages)
    if mimir.configured() and mimir.cfg("news") and data.get("source", "startup") in ("startup", "clear", "compact"):
        answer, error = mimir.lib.fail_open(mimir.client().news, 20, 4000)
        if answer and (answer.get("added") or answer.get("gone")):
            context.append(f"<mimirsynth-news brain=\"{mimir.cfg('brain')}\">\n{str(answer.get('text') or '').strip()}\n</mimirsynth-news>")
        elif error and error.auth:
            messages.append(f"MimirSynth: {error.detail}")
    _out("\n".join(context), "SessionStart", " ".join(messages))


def prompt(data: dict) -> None:
    text = (data.get("prompt") or "").strip()
    session = data.get("session_id") or ""
    if mimir.capture_mode() != "off" and session and text and not text.startswith("/"):
        rec = mimir.load(session)
        changed = False
        if not rec.get("first_prompt"):
            rec.update(first_prompt=mimir.redact(text[:1500]), cwd=data.get("cwd"), project=Path(data.get("cwd") or ".").name)
            changed = True
        if data.get("transcript_path") and rec.get("transcript") != data["transcript_path"]:
            rec["transcript"] = data["transcript_path"]
            changed = True
        if rec.get("ended") or rec.get("harvested"):   # it goes on: read it again when it is over
            rec.update(ended=False, harvested=False)
            changed = True
        if changed:
            mimir.save(rec)
    if not (mimir.configured() and mimir.cfg("recall")) or len(text) < 12 or text.startswith("/"):
        return
    answer, error = mimir.lib.fail_open(mimir.client().recall, text)
    if error is not None:   # an expired or revoked token is said, so recall does not stop without anyone noticing
        _out(message=f"MimirSynth could not recall: {error.detail}" if error.auth else "")
        return
    ctx = str((answer or {}).get("context") or "").strip()
    if ctx:
        _out(f"<mimirsynth-memory brain=\"{mimir.cfg('brain')}\">\n{ctx}\n</mimirsynth-memory>", "UserPromptSubmit")


def session_end(data: dict) -> None:
    if mimir.capture_mode() == "off":
        return
    session = data.get("session_id") or ""
    if not session or not mimir.store().path(session).exists():
        return
    rec = mimir.load(session)
    rec.update(ended=True, ended_at=time.time())
    if data.get("transcript_path"):
        rec["transcript"] = data["transcript_path"]
    mimir.save(rec)


EVENTS = {"session-start": session_start, "prompt": prompt, "session-end": session_end}


def main(argv: list) -> int:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))   # Codex writes UTF-8, whatever the console uses
    except Exception:  # noqa: BLE001
        data = {}
    try:
        data = data if isinstance(data, dict) else {}
        mimir.CWD = data.get("cwd") or None   # a `projects` entry of the configuration may give this folder another brain
        EVENTS[argv[1]](data)
    except Exception:  # noqa: BLE001  (a hook never breaks Codex)
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
