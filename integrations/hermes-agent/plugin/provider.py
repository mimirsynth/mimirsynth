"""MimirSynth as a Hermes Agent memory provider (docs/AGENT_CLIENT.md), on the shared client library (`mimirsynth_agent`, a copy of
`integrations/shared/python/mimirsynth_agent` written by `integrations/shared/vendor.py`).

What it does, through the `MemoryProvider` hooks Hermes calls:
  initialize        at session start, in the background: what changed in the brain (`/news`) and, with capture on, the sessions that ended
                    become proposals (send) or wait as drafts (draft)
  prefetch          before each turn: the recall for the message, inside <mimirsynth-memory>, plus the news the first time
  tools             mimirsynth_search (recall with more results) and mimirsynth_remember (a proposal, in quarantine)
  sync_turn         (capture on) the session's task, last answer and the files it changed, redacted, in a local record
  on_session_end    (capture on) marks the record as ended; nothing leaves the machine here

Everything fails open: every call has the configured timeout, and whatever goes wrong Hermes carries on without memory. With capture off
(the default) nothing about a session is written or sent.

The configuration is the shared one (`~/.config/mimirsynth/config.json`, or `MIMIRSYNTH_CONFIG`), with `MIMIRSYNTH_<KEY>` taking
precedence. Inside Hermes those variables are read through its secret scope (`agent.secret_scope.get_secret`), so each profile can keep its
own token in its `.env`.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path

from . import mimirsynth_agent as lib
from .mimirsynth_agent import capture

try:
    from agent.memory_provider import MemoryProvider
except ImportError:   # outside Hermes: the repository's own tests
    class MemoryProvider:  # type: ignore[no-redef]
        pass

try:
    from agent.memory_provider import RecallStatus
except ImportError:   # an older Hermes, or outside it: no recall indicator
    RecallStatus = None  # type: ignore[assignment,misc]

try:
    from agent.memory_provider import spawn_context_thread
except ImportError:   # an older Hermes, or outside it: a plain thread (there is no profile scope to carry)
    def spawn_context_thread(target, *, name, daemon=True, args=(), kwargs=None):  # type: ignore[no-redef]
        return threading.Thread(target=target, args=args, kwargs=kwargs, name=name, daemon=daemon)

logger = logging.getLogger(__name__)

NAME = "mimirsynth"                               # the provider's name: `memory.provider: mimirsynth`
AGENT, SOURCE = "Hermes Agent", "hermes-agent"   # how a captured session's proposal names the agent, for people and for machines
MIN_QUERY = 12                                    # shorter messages ("ok", "go on") are not worth a recall
NEWS_WAIT = 2.0                                   # most seconds the first turn waits for the news of the session start
FILE_TOOLS = ("write_file", "patch")              # Hermes's tools that change files
_V4A_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)

SEARCH_SCHEMA = {
    "name": "mimirsynth_search",
    "description": ("Search the team's shared memory (MimirSynth) for facts, decisions and documents about a topic. Relevant memory is "
                    "already recalled before each message; use this to look for more, or for something else."),
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "What to look for, in a sentence."},
    }, "required": ["query"]},
}
REMEMBER_SCHEMA = {
    "name": "mimirsynth_remember",
    "description": ("Propose a durable fact, decision or procedure to the team's shared memory (MimirSynth). It waits in quarantine until "
                    "a curator approves it. Only for what the team should keep: never secrets, never personal data."),
    "parameters": {"type": "object", "properties": {
        "title": {"type": "string", "description": "A short title for the memory."},
        "content": {"type": "string", "description": "The memory itself, self-contained, as it should be read later."},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1, "description": "How sure you are of it, from 0 to 1 (optional)."},
    }, "required": ["title", "content"]},
}


# --- the configuration, as Hermes hands it ------------------------------------------------------

def secret(name: str):
    """A `MIMIRSYNTH_*` value through Hermes's secret scope (the active profile's `.env`, then the process); the process environment
    outside Hermes. None when it is not set, or when Hermes refuses to read it (a multiplexed gateway with no profile bound)."""
    try:
        from agent.secret_scope import get_secret
    except ImportError:
        return os.environ.get(name)
    try:
        return get_secret(name)
    except Exception:  # noqa: BLE001
        return None


def environment() -> dict:
    """The `MIMIRSYNTH_*` variables the configuration contract reads, as Hermes gives them."""
    out = {n: v for n in [lib.config.ENV_PREFIX + k.upper() for k in lib.KEYS] if (v := secret(n)) is not None}
    path = secret(lib.config.PATH_ENV) or os.environ.get(lib.config.PATH_ENV)   # where the file is: not a secret
    if path:
        out[lib.config.PATH_ENV] = path
    return out


def hermes_home() -> Path:
    """The active profile's folder, when no agent handed us one (the CLI, a slash command)."""
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:  # noqa: BLE001
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def working_dir():
    """The conversation's folder when the agent did not say: Hermes's own resolution, else this process's."""
    try:
        from agent.runtime_cwd import resolve_agent_cwd
        return str(resolve_agent_cwd())
    except Exception:  # noqa: BLE001
        try:
            return os.getcwd()
        except OSError:
            return None


def config(cwd=None, env=None) -> lib.Config:
    """The configuration as of now: built on every call, so a change applies at once."""
    return lib.Config(env=environment() if env is None else env, cwd=cwd or working_dir())


def store(home) -> capture.Sessions:
    """The local session records of one Hermes profile: `$HERMES_HOME/mimirsynth/sessions`."""
    return capture.Sessions(Path(home) / NAME / "sessions")


def changed_files(messages, cwd=None) -> list:
    """The files Hermes's file tools changed in `messages` (OpenAI-style), relative to `cwd` when inside it, redacted."""
    out = []
    for m in messages or []:
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        for call in m.get("tool_calls") or []:
            fn = (call or {}).get("function") or {}
            if fn.get("name") not in FILE_TOOLS:
                continue
            try:
                args = json.loads(fn.get("arguments") or "{}") if isinstance(fn.get("arguments"), str) else (fn.get("arguments") or {})
            except ValueError:
                continue
            paths = [args.get("path")] + _V4A_FILE.findall(str(args.get("patch") or ""))
            for p in paths:
                if not p or not isinstance(p, str):
                    continue
                rel = p.strip()
                if cwd:
                    path = Path(rel).expanduser()
                    try:
                        rel = str((path if path.is_absolute() else Path(cwd) / path).resolve().relative_to(Path(cwd).resolve()))
                    except (ValueError, OSError):
                        rel = path.name
                rel = lib.redact(rel)
                if rel and rel not in out:
                    out.append(rel)
    return out


def _block(tag: str, brain: str, text: str) -> str:
    return f'<{tag} brain="{brain}">\n{text.strip()}\n</{tag}>'


def _count(answer: dict) -> int:
    return sum(len(answer.get(k) or []) for k in ("facts", "chunks", "documents") if isinstance(answer.get(k), list))


class MimirSynthProvider(MemoryProvider):
    """One agent's MimirSynth: bound to one Hermes profile (`hermes_home`) and one session at a time."""

    def __init__(self, env: dict | None = None):
        self._env = env                 # tests give the variables; Hermes's secret scope otherwise
        self._home: Path | None = None
        self._session = ""
        self._cwd = None
        self._primary = True            # a subagent or a cron run writes nothing and asks for nothing
        self._lock = threading.Lock()
        self._start: threading.Thread | None = None
        self._news = ""                 # what changed, waiting for the first prefetch of the session
        self._notices: list = []        # what the person should hear, said once through the agent
        self._said: set = set()
        self._recalled: int | None = None

    # -- identity and availability -------------------------------------------------------------

    @property
    def name(self) -> str:
        return NAME

    def config(self) -> lib.Config:
        return config(self._cwd, self._env)

    def is_available(self) -> bool:
        """A server, a brain and a token: no network here."""
        try:
            return self.config().configured()
        except Exception:  # noqa: BLE001
            return False

    def unavailable_reason(self) -> str:
        return ("MimirSynth needs a server, a brain and a token: run `hermes memory setup mimirsynth`, or set MIMIRSYNTH_URL, "
                "MIMIRSYNTH_BRAIN and MIMIRSYNTH_TOKEN")

    def get_config_schema(self) -> list:
        return []   # `post_setup` asks for everything, in a terminal, and writes the shared file every MimirSynth integration reads

    def save_config(self, values: dict, hermes_home: str) -> None:
        pass        # nothing in Hermes's own files: the configuration is the shared one

    def post_setup(self, hermes_home: str, config: dict) -> None:
        """`hermes memory setup mimirsynth`: asks for the server, the brain and the tokens (hidden), writes the shared configuration and
        makes MimirSynth this profile's memory provider."""
        from . import commands
        if commands.setup(interactive=True) != 0:
            return
        config.setdefault("memory", {})["provider"] = NAME
        try:
            from hermes_cli.config import save_config
            save_config(config)
            print(f"\nMemory provider: {NAME}. Start a new session to use it.")
        except Exception as e:  # noqa: BLE001
            print(f"\nCould not make MimirSynth the memory provider ({e}): run `hermes config set memory.provider {NAME}`.")

    # -- the session ---------------------------------------------------------------------------

    def initialize(self, session_id: str, **kwargs) -> None:
        self._home = Path(kwargs.get("hermes_home") or hermes_home())
        self._session = session_id or ""
        self._cwd = kwargs.get("cwd") or None
        self._primary = (kwargs.get("agent_context") or "primary") == "primary"
        if self._primary:
            self._begin(news=not kwargs.get("resumed"))

    def _store(self) -> capture.Sessions:
        return store(self._home or hermes_home())

    def _begin(self, news: bool) -> None:
        """What a session start does, in the background so the agent does not wait: the capture's ended sessions, then the news."""
        self._start = spawn_context_thread(self._session_start, args=(news, self._session), name="mimirsynth-session-start")
        self._start.start()

    def _say(self, text: str, key: str = "") -> None:
        """Something the person should hear, through the agent, once a session (per `key`, or per text)."""
        with self._lock:
            if (key or text) not in self._said:
                self._said.add(key or text)
                self._notices.append(text)

    def _session_start(self, news: bool, current: str) -> None:
        try:
            conf = self.config()
            if not conf.configured():
                return
            client = lib.Client(conf)
            mode = conf.capture_mode()
            if mode != "off":
                waiting = 0
                sessions = self._store()
                for rec in sessions.all():
                    if rec.get("session") == current or not rec.get("ended") or rec.get("sent"):
                        continue
                    if not capture.worth(rec):
                        sessions.drop(rec["session"])
                    elif mode == "send":
                        try:
                            capture.send(client, sessions, rec, AGENT, SOURCE)
                        except lib.ApiError as e:
                            self._say(f"MimirSynth did not propose the last session: {e.detail}")
                            break
                        except Exception:  # noqa: BLE001  (the server is away: it is tried again at the next start)
                            break
                    else:
                        waiting += 1
                if waiting:
                    self._say(f"MimirSynth: {waiting} session draft(s) waiting; review them with `hermes mimirsynth drafts`.")
            if news and conf.get("news"):
                answer, error = lib.fail_open(client.news, 20, 4000)
                if answer and (answer.get("added") or answer.get("gone")) and (answer.get("text") or "").strip():
                    with self._lock:
                        self._news = _block("mimirsynth-news", conf.get("brain"), answer["text"])
                elif error and error.auth:
                    self._say(f"MimirSynth: {error.detail}")
        except Exception as e:  # noqa: BLE001  (a session start never breaks the agent)
            logger.debug("MimirSynth session start failed: %s", e)

    def on_session_switch(self, new_session_id: str, *, parent_session_id: str = "", reset: bool = False, rewound: bool = False,
                          **kwargs) -> None:
        """`/new` or `/reset` start another conversation (the old one has ended); a compression or `/branch` carries on the same work
        under another id, so its record follows it."""
        old, self._session = self._session, new_session_id or ""
        if not self._primary:
            return
        try:
            if self.config().capture_mode() != "off" and old and old != self._session:
                sessions = self._store()
                if reset:
                    self._end(old)
                elif (sessions.path(old)).exists():
                    rec = sessions.load(old)
                    rec["session"] = self._session
                    sessions.save(rec)
                    sessions.drop(old)
        except Exception as e:  # noqa: BLE001
            logger.debug("MimirSynth could not follow the session switch: %s", e)
        if reset:
            self._begin(news=True)

    def system_prompt_block(self) -> str:
        try:
            conf = self.config()
        except Exception:  # noqa: BLE001
            return ""
        if not conf.configured():
            return ""
        return (f"# MimirSynth\nThe team's shared memory (brain «{conf.get('brain')}») is connected. Before each message, what it "
                "recalls arrives inside <mimirsynth-memory>, and at the start of a session what changed in the brain inside "
                "<mimirsynth-news>. Use mimirsynth_search to look for more, and mimirsynth_remember to propose something durable "
                "the team should keep: it waits in quarantine until a curator approves it. Never put secrets or personal data in it.")

    # -- before each turn ----------------------------------------------------------------------

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        self._recalled = None
        if not self._primary:
            return ""
        try:
            conf = self.config()
            if not conf.configured():
                return ""
            start = self._start
            if start is not None and start.is_alive():
                # the news, if they arrive in time; otherwise with the next message. Bounded so that this wait plus the recall's own
                # timeout stay under the limit Hermes gives a prefetch (8 s) with the default timeout (4 s)
                start.join(min(float(conf.get("timeout")) / 2, NEWS_WAIT))
            with self._lock:
                news, self._news = self._news, ""
            parts = [news] if news else []
            text = (query or "").strip()
            if conf.get("recall") and len(text) >= MIN_QUERY and not text.startswith("/"):
                answer, error = lib.fail_open(lib.Client(conf).recall, text)
                context = ((answer or {}).get("context") or "").strip()
                if context:
                    parts.append(_block("mimirsynth-memory", conf.get("brain"), context))
                    self._recalled = _count(answer)
                elif error and error.auth:   # an expired or revoked token is said, so recall does not stop without anyone noticing
                    logger.warning("MimirSynth could not recall: %s", error.detail)
                    self._say(f"MimirSynth could not recall: {error.detail}", key="recall")
            with self._lock:
                notices, self._notices = self._notices, []
            if notices:
                parts.append("<mimirsynth-notice>\nTell the person, briefly: " + " ".join(notices) + "\n</mimirsynth-notice>")
            return "\n\n".join(parts)
        except Exception as e:  # noqa: BLE001  (fail open: nothing injected, the turn goes on)
            logger.debug("MimirSynth prefetch failed: %s", e)
            return ""

    def recall_status(self):
        if RecallStatus is None or self._recalled is None:
            return None
        return RecallStatus("MimirSynth", self._recalled)

    # -- tools ---------------------------------------------------------------------------------

    def get_tool_schemas(self) -> list:
        return [SEARCH_SCHEMA, REMEMBER_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str:
        from . import commands
        args = args if isinstance(args, dict) else {}
        try:
            conf = self.config()
            if tool_name == "mimirsynth_search":
                return json.dumps(commands.search_result(conf, str(args.get("query") or "")), ensure_ascii=False)
            if tool_name == "mimirsynth_remember":
                return json.dumps(commands.remember_result(conf, str(args.get("title") or ""), str(args.get("content") or ""),
                                                           args.get("confidence")), ensure_ascii=False)
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:  # noqa: BLE001
            return json.dumps({"error": f"MimirSynth: {e}"}, ensure_ascii=False)

    # -- the optional capture ------------------------------------------------------------------

    def _capturing(self) -> bool:
        try:
            return self._primary and self.config().capture_mode() != "off"
        except Exception:  # noqa: BLE001
            return False

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "", messages=None) -> None:
        """(capture on) The session's task, its last answer and the files it changed, redacted, in its local record. Local and small:
        it does not wait on the network."""
        if not self._capturing():
            return
        try:
            sid = session_id or self._session
            sessions = self._store()
            rec = sessions.load(sid)
            text = (user_content or "").strip()
            cwd = self._cwd or working_dir()
            if not rec.get("first_prompt") and text and not text.startswith("/"):
                rec.update(first_prompt=lib.redact(text[:1500]), cwd=cwd, project=Path(cwd or ".").name)
            rec["turns"], rec["ended"] = int(rec.get("turns") or 0) + 1, False   # a resumed session is not over
            answer = (assistant_content or "").strip()
            if answer:
                rec["last_message"] = lib.redact(answer[:6000])
            for f in changed_files(messages, cwd):
                if f not in rec["files"]:
                    rec["files"].append(f)
            rec.setdefault("project", Path(cwd or ".").name)
            sessions.save(rec)
        except Exception as e:  # noqa: BLE001
            logger.debug("MimirSynth could not record the turn: %s", e)

    def _end(self, sid: str, messages=None) -> None:
        sessions = self._store()
        rec = sessions.load(sid)
        for f in changed_files(messages, self._cwd or working_dir()):
            if f not in rec["files"]:
                rec["files"].append(f)
        if rec.get("turns") or rec.get("files"):
            rec["ended"] = True
            sessions.save(rec)

    def on_session_end(self, messages) -> None:
        """(capture on) The session is over: its record becomes a draft, or a proposal at the next session start. Nothing is sent here."""
        if not self._capturing():
            return
        try:
            self._end(self._session, messages)
        except Exception as e:  # noqa: BLE001
            logger.debug("MimirSynth could not close the session: %s", e)

    def shutdown(self) -> None:
        start = self._start
        if start is not None and start.is_alive():
            start.join(1.0)
