"""Calls to a brain's API with an API token: recall, news, whoami and proposals (docs/AGENT_CLIENT.md).

Every call has the configured timeout (4 s) and raises: `ApiError` when the server answered with an error, anything else when it could
not be reached. A hook must never break its agent, so it wraps calls in `fail_open`, which turns a network error into nothing and keeps
the server's answer only when it is worth telling the person (an expired or revoked token).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from . import secretscan
from .config import Config

QUERY_MAX = 1500            # characters of a prompt sent as a recall query
MARKER = "[secret removed]"


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"{status}: {detail}")
        self.status, self.detail = status, detail

    @property
    def auth(self) -> bool:
        """The token is missing, expired, revoked or lacks the scope: worth telling the person, unlike a server that is away."""
        return self.status in (401, 403)


def _detail(raw: bytes, reason) -> str:
    try:
        d = json.loads(raw or b"{}").get("detail")
    except Exception:  # noqa: BLE001
        d = None
    if d is None or d == "":
        return str(reason)
    return d if isinstance(d, str) else json.dumps(d, ensure_ascii=False, separators=(",", ":"))   # as JSON.stringify writes it


def url_for(conf: Config, path: str, query="") -> str:
    """`{url}/api/brains/{brain}{path}`, or `{url}/api{path without one slash}` when `path` starts with `//`."""
    base = str(conf.get("url")).rstrip("/")
    full = f"{base}/api{path[1:]}" if path.startswith("//") else f"{base}/api/brains/{conf.get('brain')}{path}"
    if isinstance(query, dict):
        query = urllib.parse.urlencode(query)
    return full + (f"?{query}" if query else "")


def request(conf: Config, method: str, path: str, body: dict | None = None, token: str | None = None, timeout: float | None = None,
            query="") -> dict:
    """One call. Returns the JSON answer (`{}` when empty); raises ApiError with the server's message on an HTTP error."""
    req = urllib.request.Request(url_for(conf, path, query), method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout or float(conf.get("timeout"))) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            raw = e.read()
        except Exception:  # noqa: BLE001
            raw = b""
        raise ApiError(e.code, _detail(raw, e.reason)) from None


def fail_open(fn, *args, **kwargs):
    """Runs a call that must not break the agent: `(answer, None)`, `(None, ApiError)` when the server answered with an error, or
    `(None, None)` when it could not be reached or anything else went wrong."""
    try:
        return fn(*args, **kwargs), None
    except ApiError as e:
        return None, e
    except Exception:  # noqa: BLE001
        return None, None


def redact(text: str) -> str:
    """The text with everything the server's detector finds, sure or possible, replaced by a marker. By patterns: not infallible."""
    text = text or ""
    found = secretscan.scan(text)
    return secretscan.redact(text, found, marker=MARKER, everything=True) if found else text


class Client:
    """The calls an agent integration makes, with the tokens of one configuration."""

    def __init__(self, conf: Config | None = None):
        self.conf = conf if conf is not None else Config()

    def call(self, method: str, path: str, body: dict | None = None, token: str | None = None, timeout: float | None = None, query=""):
        return request(self.conf, method, path, body=body, token=token, timeout=timeout, query=query)

    def write_token(self) -> str:
        return self.conf.get("write_token") or self.conf.get("token")

    def recall(self, query: str, facts: int = 6, chunks: int = 3, max_chars: int | None = None, timeout: float | None = None) -> dict:
        """`POST /recall` with the reader token: `{"context": …}` among others. `max_chars` defaults to the configured one."""
        body = {"query": (query or "")[:QUERY_MAX], "facts": facts, "chunks": chunks,
                "max_chars": int(max_chars if max_chars is not None else self.conf.get("max_chars"))}
        return self.call("POST", "/recall", body=body, token=self.conf.get("token"), timeout=timeout)

    def news(self, limit: int = 20, max_chars: int = 4000) -> dict:
        """`POST /news`: what changed since this token last asked, `{"text", "added", "gone"}`."""
        return self.call("POST", "/news", token=self.conf.get("token"), query=f"limit={int(limit)}&max_chars={int(max_chars)}")

    def whoami(self, token: str | None = None) -> dict:
        """`GET /whoami`: the brain, the role, the server's version and the token's name, scopes and expiry."""
        return self.call("GET", "/whoami", token=token if token is not None else self.conf.get("token"))

    def propose(self, body: dict, token: str | None = None, timeout: float | None = 20) -> dict:
        """`POST /proposals` with the write token, as given: redact it first (see `remember`)."""
        return self.call("POST", "/proposals", body=body, token=token or self.write_token(), timeout=timeout)

    def remember(self, title: str, content: str, confidence: float | None = None, source_description: str = "",
                 origin: str = "agent", timeout: float | None = 20) -> dict:
        """A memory an agent chose to write, redacted, as one proposal: `{"id", "status"}` (`pending` with a contributor token)."""
        body = {"name": redact(title)[:255], "body": redact(content), "source": "text", "source_description": source_description,
                "origin": origin}
        if confidence is not None:
            body["confidence"] = confidence
        return self.propose(body, timeout=timeout)
