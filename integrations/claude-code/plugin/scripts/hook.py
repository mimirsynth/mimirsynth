#!/usr/bin/env python3
"""The MimirSynth plugin's hooks. One script, the event as its argument:

  session-start   what changed in the brain since the last session (`/news`), a warning if another memory hook also injects context,
                  and, with capture on, the sessions that ended become proposals (send) or wait as drafts (draft)
  prompt          the recall for the prompt, inside <mimirsynth-memory>, before Claude reads it
  tool            (capture on) the file an edit touched
  stop            (capture on) the last answer, redacted
  session-end     (capture on) marks the session as ended; nothing leaves the machine here (a plugin has 1.5 s at the end)

Every hook fails open: whatever goes wrong, it exits 0 and Claude Code carries on. With capture off (the default) the last three do
nothing at all, and nothing about the session is written or sent.

Session start and the recall also write what happened to the session's status file, for the status row (`statusline.py`, #481): the
brain, the token's role and expiry, the capture mode and the drafts, and the recall's outcome, a failure included. It holds nothing
of the session itself (no prompt, file or answer), so it is written with capture off too.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mimir  # noqa: E402


def _out(context: str = "", event: str = "", message: str = "") -> None:
    out: dict = {}
    if context:
        out["hookSpecificOutput"] = {"hookEventName": event, "additionalContext": context[:9500]}
    if message:
        out["systemMessage"] = message
    if out:
        print(json.dumps(out, ensure_ascii=False))


def _auth_message(e: mimir.ApiError) -> str:
    return f"MimirSynth: {e.detail}" if e.status in (401, 403) else ""


_WHY = {"offline": "offline", "rejected": "token rejected", "error": "server error"}


def _row() -> dict:
    """The status row's fields at session start: the brain and the recall token's role and expiry (/whoami, cached), and the health."""
    mimir.prune_status()
    mimir.refresh_statusline()
    if not mimir.configured():
        return {"configured": False, "action": "not configured"}
    row = {"configured": True, "brain": mimir.cfg("brain"), "capture": mimir.capture_mode(), "drafts": 0, **mimir.whoami()}
    row["action"] = ("connected" if mimir.cfg("recall") else "recall off") if row["health"] == "ok" else _WHY[row["health"]]
    return row


def session_start(data: dict) -> None:
    messages, context = [], []
    sid = data.get("session_id") or ""
    row = _row()
    others = mimir.other_memory()
    if others:
        messages.append("MimirSynth: other memory hooks also inject context here (" + "; ".join(others) + "). "
                        "MimirSynth's blocks are marked <mimirsynth-memory> and <mimirsynth-news>.")
    if mimir.configured() and mimir.capture_mode() != "off":
        current = data.get("session_id")
        waiting = 0
        for rec in mimir.sessions():
            if rec.get("session") == current or not rec.get("ended") or rec.get("sent"):
                continue
            if not mimir.worth(rec):
                mimir.drop(rec["session"])
            elif mimir.capture_mode() == "send":
                try:
                    r = mimir.send(rec)
                    row["action"] = f"last session proposed (#{r.get('id')})"
                except mimir.ApiError as e:
                    messages.append(f"MimirSynth did not propose the last session: {e.detail}")
                    row["action"] = "last session not proposed"
                    break
                except Exception:  # noqa: BLE001  (the server is away: it is tried again at the next start)
                    break
            else:
                waiting += 1
        if waiting:
            messages.append(f"MimirSynth: {waiting} session draft(s) waiting; review them with /mimirsynth:remember.")
        row["drafts"] = waiting
    if mimir.configured() and mimir.cfg("news") and data.get("source", "startup") in ("startup", "clear", "compact"):
        try:
            r = mimir.call("POST", "/news", token=mimir.cfg("token"), query="limit=20&max_chars=4000")
            if r.get("added") or r.get("gone"):
                context.append(f"<mimirsynth-news brain=\"{mimir.cfg('brain')}\">\n{r.get('text', '').strip()}\n</mimirsynth-news>")
        except mimir.ApiError as e:
            if _auth_message(e):
                messages.append(_auth_message(e))
        except Exception:  # noqa: BLE001
            pass
    mimir.status(sid, **row)
    _out("\n".join(context), "SessionStart", " ".join(messages))


def prompt(data: dict) -> None:
    text = (data.get("prompt") or "").strip()
    if mimir.capture_mode() != "off" and text and not text.startswith("/"):
        rec = mimir.load(data.get("session_id") or "")
        if not rec.get("first_prompt"):
            rec.update(first_prompt=mimir.redact(text[:1500]), cwd=data.get("cwd"), project=Path(data.get("cwd") or ".").name)
            mimir.save(rec)
    if not (mimir.configured() and mimir.cfg("recall")) or len(text) < 12 or text.startswith("/"):
        return
    try:
        r = mimir.call("POST", "/recall", body={"query": text[:1500], "facts": 6, "chunks": 3, "max_chars": int(mimir.cfg("max_chars"))},
                       token=mimir.cfg("token"))
    except Exception as e:  # noqa: BLE001  (fail open: nothing injected, the prompt goes on; the row says why)
        health, what = mimir.failure(e)
        mimir.status(data.get("session_id") or "", health=health, action=f"recall: {what}")
        if isinstance(e, mimir.ApiError) and e.status in (401, 403):   # an expired or revoked token is also said in the conversation
            _out(message=f"MimirSynth could not recall: {e.detail}")
        return
    ctx = (r.get("context") or "").strip()
    facts, passages = len(r.get("facts") or []), len(r.get("chunks") or []) + len(r.get("documents") or [])
    found = [f"{facts} fact{'' if facts == 1 else 's'}" if facts else "", f"{passages} passage{'' if passages == 1 else 's'}" if passages else ""]
    mimir.status(data.get("session_id") or "", health="ok",
                 action="recall: " + (", ".join(x for x in found if x) if ctx and any(found) else "nothing relevant" if not ctx else "context"))
    if ctx:
        _out(f"<mimirsynth-memory brain=\"{mimir.cfg('brain')}\">\n{ctx}\n</mimirsynth-memory>", "UserPromptSubmit")


def tool(data: dict) -> None:
    if mimir.capture_mode() == "off":
        return
    path = str((data.get("tool_input") or {}).get("file_path") or (data.get("tool_input") or {}).get("notebook_path") or "")
    if not path:
        return
    rec = mimir.load(data.get("session_id") or "")
    try:
        rel = str(Path(path).resolve().relative_to(Path(data.get("cwd") or ".").resolve()))
    except ValueError:
        rel = Path(path).name
    rel = mimir.redact(rel)
    if rel not in rec["files"]:
        rec["files"].append(rel)
        rec.setdefault("cwd", data.get("cwd"))
        rec.setdefault("project", Path(data.get("cwd") or ".").name)
        mimir.save(rec)


def stop(data: dict) -> None:
    if mimir.capture_mode() == "off" or data.get("stop_hook_active"):
        return
    msg = (data.get("last_assistant_message") or "").strip()
    rec = mimir.load(data.get("session_id") or "")
    rec["turns"], rec["ended"] = int(rec.get("turns") or 0) + 1, False   # a resumed session is not over
    if msg:
        rec["last_message"] = mimir.redact(msg[:6000])
    rec.setdefault("project", Path(data.get("cwd") or ".").name)
    mimir.save(rec)


def session_end(data: dict) -> None:
    if mimir.capture_mode() == "off":
        return
    rec = mimir.load(data.get("session_id") or "")
    if rec.get("turns") or rec.get("files"):
        rec["ended"] = True
        mimir.save(rec)


EVENTS = {"session-start": session_start, "prompt": prompt, "tool": tool, "stop": stop, "session-end": session_end}


def main(argv: list[str]) -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        data = {}
    try:
        data = data if isinstance(data, dict) else {}
        mimir.CWD = data.get("cwd") or None   # a `projects` entry of the configuration may give this folder another brain
        EVENTS[argv[1]](data)
    except Exception:  # noqa: BLE001  (a hook never breaks Claude Code)
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
