"""The shared client library for agent integrations (#369): the Python implementation passes the contract cases that every
implementation must pass (integrations/shared/contract/cases.json), the plugins carry an exact copy of it, it carries the server's own
secret detector, and the configuration contract is documented in both languages."""
import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "integrations" / "shared"
CASES = json.loads((SHARED / "contract" / "cases.json").read_text(encoding="utf-8"))
sys.path.insert(0, str(SHARED / "python"))
import mimirsynth_agent as lib  # noqa: E402
from mimirsynth_agent import capture  # noqa: E402


def text(v):
    """A case's string: fragments joined, or {"repeat": s, "times": n}."""
    if isinstance(v, list):
        return "".join(v)
    if isinstance(v, dict) and "repeat" in v:
        return v["repeat"] * v["times"]
    return v


def rooted(v, root: Path):
    if isinstance(v, str):
        return v.replace("{root}", str(root))
    if isinstance(v, dict):
        return {rooted(k, root): rooted(x, root) for k, x in v.items()}
    if isinstance(v, list):
        return [rooted(x, root) for x in v]
    return v


def same(got, want) -> bool:
    if isinstance(want, bool) or isinstance(got, bool):
        return got is want
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        return got == want
    return got == want


@pytest.mark.parametrize("case", CASES["config"], ids=[c["name"] for c in CASES["config"]])
def test_config_contract(case, tmp_path):
    for rel, content in case["files"].items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content if isinstance(content, str) else json.dumps(rooted(content, tmp_path)), encoding="utf-8")
    env = rooted(case["env"], tmp_path)
    if case["path"] is None:
        assert "MIMIRSYNTH_CONFIG" in env   # never the real file
    conf = lib.Config(path=tmp_path / case["path"] if case["path"] else None, env=env, cwd=rooted(case.get("cwd"), tmp_path))
    for key, want in case["expect"].items():
        got = conf.get(key)
        assert same(got, want), f"{key}: {got!r} != {want!r}"
        assert type(got) is type(lib.DEFAULTS[key]), key
    for key, want in case.get("sources", {}).items():
        assert conf.source(key) == want, key
    if "configured" in case:
        assert conf.configured() is case["configured"]


@pytest.mark.parametrize("case", CASES["redact"], ids=[c["name"] for c in CASES["redact"]])
def test_redaction_contract(case):
    assert lib.redact(text(case["text"])) == case["expect"]


@pytest.mark.parametrize("case", CASES["worth"])
def test_worth_and_drafts_contract(case):
    rec = {k: text(v) for k, v in case["record"].items()}
    if "worth" in case:
        assert capture.worth(rec) is case["worth"]
    if "draft" in case:
        assert capture.is_draft(rec) is case["draft"]


@pytest.mark.parametrize("case", CASES["proposal"], ids=[c["name"] for c in CASES["proposal"]])
def test_proposal_contract(case):
    p = capture.proposal(case["record"], case["agent"], case["source"], case["confidence"])
    for key, want in case["expect"].items():
        assert p[key] == want, key


class Wire:
    """Replaces urllib.request.urlopen: records every request and answers from a table (path → (status, reason, body))."""

    def __init__(self, monkeypatch):
        self.calls, self.answers = [], {}
        monkeypatch.setattr(lib.client.urllib.request, "urlopen", self.urlopen)

    def urlopen(self, req, timeout=None):
        self.calls.append({"method": req.get_method(), "url": req.full_url, "auth": req.headers.get("Authorization"), "timeout": timeout,
                           "body": json.loads(req.data) if req.data else None})
        path = req.full_url.split("/api/brains/b1", 1)[-1].split("?")[0]
        a = self.answers.get(path, (200, "OK", "{}"))
        if isinstance(a, Exception):
            raise a
        status, reason, body = a
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, reason, {}, io.BytesIO(body.encode()))

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *e):
                return False
        return Resp(body.encode())


def _conf(tmp_path, **over) -> lib.Config:
    (tmp_path / "config.json").write_text(json.dumps({**CASES["requests"]["config"], **over}), encoding="utf-8")
    return lib.Config(path=tmp_path / "config.json", env={})


@pytest.mark.parametrize("case", CASES["requests"]["cases"], ids=[c["name"] for c in CASES["requests"]["cases"]])
def test_request_contract(case, tmp_path, monkeypatch):
    wire = Wire(monkeypatch)
    client = lib.Client(_conf(tmp_path, **case.get("config", {})))
    getattr(client, case["call"])(**{k: text(v) for k, v in case["args"].items()})
    want = dict(case["expect"])
    if want.get("body") and "query" in want["body"]:
        want["body"] = {**want["body"], "query": text(want["body"]["query"])}
    assert wire.calls == [want]


@pytest.mark.parametrize("case", CASES["answers"], ids=[c["name"] for c in CASES["answers"]])
def test_answer_contract(case, tmp_path, monkeypatch):
    wire = Wire(monkeypatch)
    wire.answers["/whoami"] = (case["status"], case["reason"], case["body"])
    client = lib.Client(_conf(tmp_path))
    want = case["expect"]
    if "value" in want:
        assert client.whoami() == want["value"]
        return
    with pytest.raises(lib.ApiError) as e:
        client.whoami()
    assert (e.value.status, e.value.detail, e.value.auth) == (want["status"], want["detail"], want["auth"])


@pytest.mark.parametrize("case", CASES["send"], ids=[c["name"] for c in CASES["send"]])
def test_send_contract(case, tmp_path, monkeypatch):
    wire = Wire(monkeypatch)
    wire.answers["/whoami"] = (200, "OK", json.dumps(case["whoami"]))
    wire.answers["/proposals"] = (201, "Created", json.dumps(case.get("proposals", {})))
    store = capture.Sessions(tmp_path / "sessions")
    rec = {"session": "s1", "files": ["a.py"], "ended": True, "sent": None, "started": 1794139200, "project": "p"}
    want = case["expect"]
    if "error" in want:
        with pytest.raises(lib.ApiError) as e:
            capture.send(lib.Client(_conf(tmp_path)), store, rec, "Codex", "codex")
        assert e.value.status == want["error"]
    else:
        capture.send(lib.Client(_conf(tmp_path)), store, rec, "Codex", "codex")
        assert wire.calls[-1]["auth"] == want["auth"] and wire.calls[-1]["timeout"] == want["timeout"]
    assert [f"{c['method']} {c['url'].split('/api/brains/b1', 1)[1]}" for c in wire.calls] == want["calls"]
    if want["sent"]:
        assert {k: rec["sent"][k] for k in want["sent"]} == want["sent"] and store.load("s1")["sent"]["id"] == want["sent"]["id"]
    else:
        assert not rec.get("sent")


def test_the_cases_are_for_this_version_of_the_contract():
    assert CASES["contract_version"] == lib.CONTRACT_VERSION


def test_fail_open_turns_a_network_error_into_nothing_and_keeps_what_the_server_said(tmp_path, monkeypatch):
    wire = Wire(monkeypatch)
    client = lib.Client(_conf(tmp_path))
    wire.answers["/recall"] = TimeoutError("timed out")
    assert lib.fail_open(client.recall, "where does the database run?") == (None, None)
    wire.answers["/recall"] = (401, "Unauthorized", '{"detail": "token revoked"}')
    value, err = lib.fail_open(client.recall, "where does the database run?")
    assert value is None and err.auth and err.detail == "token revoked"
    wire.answers["/recall"] = (200, "OK", '{"context": "x"}')
    assert lib.fail_open(client.recall, "q") == ({"context": "x"}, None)


def test_the_default_file_and_the_session_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert lib.config_path({}) == tmp_path / ".config" / "mimirsynth" / "config.json"
    assert capture.default_dir("codex", lib.config_path({})) == tmp_path / ".config" / "mimirsynth" / "state" / "codex" / "sessions"
    store = capture.Sessions(tmp_path / "s")
    assert store.base == tmp_path / "s" and not store.base.exists()   # nothing is written until a record is
    store.save({"session": "a/b c", "started": 0})
    assert (tmp_path / "s" / "a_b_c.json").exists() and store.all() == []   # older than KEEP_DAYS: dropped on the way
    assert not (tmp_path / "s" / "a_b_c.json").exists()


def test_the_library_carries_the_servers_detector_and_every_plugin_carries_the_library():
    """Fix: python integrations/shared/vendor.py"""
    assert (SHARED / "python" / "mimirsynth_agent" / "secretscan.py").read_bytes() == (ROOT / "api" / "mimirsynth" / "secretscan.py").read_bytes()
    spec = importlib.util.spec_from_file_location("vendor", SHARED / "vendor.py")
    vendor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vendor)
    assert vendor.TARGETS and vendor.main(["--check"]) == 0


def test_the_configuration_contract_is_documented_in_both_languages():
    for doc in (ROOT / "docs" / "AGENT_CLIENT.md", ROOT / "docs" / "es" / "AGENT_CLIENT.md"):
        src = doc.read_text(encoding="utf-8")
        missing = [k for k in (*lib.KEYS, "projects", "MIMIRSYNTH_CONFIG", *lib.CAPTURE_MODES, *lib.CAPTURE_ALIASES) if f"`{k}`" not in src]
        assert not missing, f"{doc.relative_to(ROOT)} does not mention {missing}"
