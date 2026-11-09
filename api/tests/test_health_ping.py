"""#424: the periodic health check is a cheap ping again; the full check of #420 (graphiti's structured request, the decider's letter with
logprobs) runs on Test, Add, Edit and the wizard, once when the engine in use changes and at most once a day, is kept on the engine and
shown in Administration, and a model that answers but fails it still raises a notice. A fake provider counts what each model receives."""
from collections import Counter
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from test_control import client  # noqa: F401  (fixture with the app and the test database)
from test_llm_structured import FENCED_KEYS, GOOD

from mimirsynth import appsettings, fitness, llmcheck, notify
from mimirsynth.models import Notification
from mimirsynth.store import _factory

T0 = datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc)
LLM, DEC = "/api/llm-engines", "/api/decision-engines"


class Provider:
    """A fake OpenAI-compatible provider for every host: its models list, the ping, the structured request and the decider's question.
    `calls` keeps (host, what) for each request; `structured` and `logprobs` set a host's answers."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.structured: dict[str, str] = {}
        self.logprobs: dict[str, bool] = {}
        self.listed: dict[str, list[str]] = {}
        self.down: set[str] = set()

    def count(self, host: str, what: str) -> int:
        return Counter(self.calls)[(host, what)]

    def get(self, url, timeout=None, headers=None):
        host = httpx.URL(url).host
        self.calls.append((host, "models"))
        if host in self.down:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, json={"data": [{"id": m} for m in self.listed.get(host, [])]}, request=httpx.Request("GET", url))

    def post(self, url, json=None, timeout=None, headers=None):  # noqa: A002
        host = httpx.URL(url).host
        what = "structured" if "response_format" in json else "decider" if json.get("logprobs") else "ping"
        self.calls.append((host, what))
        if host in self.down:
            raise httpx.ConnectError("connection refused")
        choice = {"message": {"role": "assistant", "content": "ok"}}
        if what == "structured":
            choice["message"]["content"] = self.structured.get(host, GOOD)
        elif what == "decider":
            choice["message"]["content"] = "B"
            if self.logprobs.get(host, True):
                choice["logprobs"] = {"content": [{"top_logprobs": [{"token": "B", "logprob": -0.05}, {"token": "A", "logprob": -3.2}]}]}
        elif what == "ping":
            assert json["max_tokens"] == 1 and len(json["messages"]) == 1                     # a few tokens, not the extraction
        return httpx.Response(200, json={"choices": [choice]}, request=httpx.Request("POST", url))


@pytest.fixture()
def provider(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth import embeddings_admin
    p = Provider()
    monkeypatch.setattr(httpx, "get", p.get)
    monkeypatch.setattr(httpx, "post", p.post)
    monkeypatch.setattr(embeddings_admin, "_probe", lambda *a: 768)                           # only the LLM and the decider are counted
    monkeypatch.setattr(dbm, "list_graphs", lambda: [])
    notify._FAILS.clear()
    return p


@pytest.fixture()
def clock(monkeypatch):
    """`fitness`'s clock, moved by hand: clock(minutes since T0)."""
    now = [T0]
    monkeypatch.setattr(fitness, "_now", lambda: now[0])

    def move(minutes: float) -> datetime:
        now[0] = T0 + timedelta(minutes=minutes)
        return now[0]
    return move


@pytest.fixture()
def engines(client):  # noqa: F811
    """Adds LLM engines and deciders (in use unless told otherwise); afterwards they go, the ones in use before come back and the notices
    of the full check are cleared (the test database is shared)."""
    before = {p: next((e["id"] for e in client.get(p).json() if e["is_default"]), None) for p in (LLM, DEC)}
    made = []

    def add(path: str, name: str, key: str = "sk-test", default: bool = True, model: str = "m") -> int:
        eid = client.post(path, json={"name": name, "base_url": f"http://{name}/v1", "model": model, "api_key": key or None}).json()["id"]
        if default:
            assert client.post(f"{path}/{eid}/default").status_code == 200
        made.append((path, eid))
        return eid
    yield add
    for path, eid in made:
        client.delete(f"{path}/{eid}")
    for path, eid in before.items():
        if eid:
            client.post(f"{path}/{eid}/default")
    with _factory()() as db:
        db.query(Notification).filter(Notification.key.in_(["llm.fit", "decider.fit"])).delete()
        db.commit()


def _fit_notice(kind: str) -> Notification | None:
    with _factory()() as db:
        return db.query(Notification).filter_by(event="model.unavailable", key=f"{kind}.fit").one_or_none()


def _row(client, path: str, eid: int) -> dict:  # noqa: F811
    return next(e for e in client.get(path).json() if e["id"] == eid)


def test_an_idle_day_with_the_defaults_sends_each_model_the_ping_and_the_full_check_once(client, engines, provider, clock):  # noqa: F811
    """The acceptance count: with the defaults, an idle day is 144 pings and one full check per model; the next day brings one more."""
    engines(LLM, "day424")
    engines(DEC, "dday424")
    mins = int(appsettings.get("notify_health_minutes"))
    assert mins == 10                                                                          # the default
    for minute in range(24 * 60):                                                              # the worker: due every minute, the ping every 10
        clock(minute)
        if minute % mins == 0:
            notify.check_health()
        fitness.due(mins > 0)
    assert provider.count("day424", "ping") == 144 and provider.count("day424", "structured") == 1
    assert provider.count("dday424", "ping") == 144 and provider.count("dday424", "decider") == 1
    assert provider.count("day424", "models") == 0                                             # a key to prove: the ping is a chat request
    clock(24 * 60)
    fitness.due()
    assert provider.count("day424", "structured") == 2 and provider.count("dday424", "decider") == 2  # once a day, not more
    clock(24 * 60 + 600)
    fitness.due(daily=False)                                                                   # notify_health_minutes = 0: no daily check
    assert provider.count("day424", "structured") == 2


def test_changing_the_llm_in_use_runs_the_full_check_once_and_shows_it(client, engines, provider, clock):  # noqa: F811
    engines(LLM, "a424")
    fitness.due()
    b = engines(LLM, "b424", default=False)
    assert client.post(f"{LLM}/{b}/test").json()["ok"]                                         # tested while not in use
    provider.calls.clear()
    at = clock(30)
    assert client.post(f"{LLM}/{b}/default").status_code == 200                                # another engine made default
    fitness.due(); fitness.due(); fitness.due()
    assert provider.count("b424", "structured") == 1 and provider.count("a424", "structured") == 0
    shown = _row(client, LLM, b)["fitness"]                                                    # what Administration shows
    assert shown["fit"] is True and shown["ok"] and shown["current"] and datetime.fromisoformat(shown["at"]) == at
    assert shown["text"] == "devuelve salida estructurada: Alice Moreno, Atlas billing server"

    body = {"name": "b424", "base_url": "http://b424/v1", "model": "m2"}
    client.patch(f"{LLM}/{b}", json=body)                                                      # its model edited
    assert _row(client, LLM, b)["fitness"]["current"] is False                                 # the result shown is the old model's
    fitness.due(); fitness.due()
    assert provider.count("b424", "structured") == 2 and _row(client, LLM, b)["fitness"]["current"]

    client.patch(f"{LLM}/{b}", json={**body, "model": "m3"})
    client.post(f"{LLM}/{b}/test")                                                             # the interface tests it right after an edit
    n = provider.count("b424", "structured")
    fitness.due()
    assert provider.count("b424", "structured") == n                                           # that test was the check: no second one


def test_a_model_that_answers_but_fails_the_full_check_raises_a_notice(client, engines, provider, clock):  # noqa: F811
    provider.structured["bad424"] = FENCED_KEYS
    engines(LLM, "bad424")
    fitness.due()                                                                              # on the change of engine
    n = _fit_notice("llm")
    assert n and n.resolved_at is None and n.severity == "critical"
    assert n.title == "El modelo LLM no devuelve la salida estructurada que necesita la ingesta"  # #420's words
    assert n.body.startswith("Motor «bad424»: responde, pero no con un JSON que cumpla el esquema") and "otras claves" in n.body
    for _ in range(3):
        notify.check_health()                                                                  # the ping answers: it does not close it
    assert _fit_notice("llm").resolved_at is None and provider.count("bad424", "structured") == 1
    clock(24 * 60)
    fitness.due()                                                                              # the daily check: still failing, still open
    assert provider.count("bad424", "structured") == 2 and _fit_notice("llm").resolved_at is None
    provider.structured["bad424"] = GOOD
    clock(48 * 60)
    fitness.due()                                                                              # it passes: closed
    assert _fit_notice("llm").resolved_at is not None

    provider.logprobs["nolp424"] = False                                                       # the decider: an answer without logprobs
    engines(DEC, "nolp424")
    fitness.due()
    d = _fit_notice("decider")
    assert d and d.resolved_at is None and d.title == fitness.TITLES["decider"] and llmcheck.NO_LOGPROBS in d.body


def test_a_full_check_that_gets_no_answer_raises_nothing_and_is_retried_within_the_hour(client, engines, provider, clock):  # noqa: F811
    provider.down.add("down424")
    eid = engines(LLM, "down424")
    fitness.due()
    assert _fit_notice("llm") is None                                                          # not reaching it is the ping's notice
    assert _row(client, LLM, eid)["fitness"]["fit"] is None
    clock(30); fitness.due()
    assert provider.count("down424", "structured") == 1
    provider.down.clear()
    clock(61); fitness.due()
    assert provider.count("down424", "structured") == 2 and _row(client, LLM, eid)["fitness"]["fit"] is True


def test_the_ping_is_a_few_tokens_or_the_models_list(provider):
    provider.listed["ollama"] = ["qwen2.5:14b-instruct", "llama3.2:latest"]
    llmcheck.ping("http://ollama/v1", "qwen2.5:14b-instruct")                                  # no key: the list answers, nothing is generated
    llmcheck.ping("http://ollama/v1", "llama3.2")
    assert provider.calls == [("ollama", "models"), ("ollama", "models")]
    provider.calls.clear()
    llmcheck.ping("http://ollama/v1", "not-pulled")                                            # not in the list: a chat request decides
    assert provider.calls == [("ollama", "models"), ("ollama", "ping")]
    provider.calls.clear()
    llmcheck.ping("http://paid/v1", "gpt-x", "sk")                                             # a key to prove: never the (often public) list
    assert provider.calls == [("paid", "ping")]
    provider.down.add("paid")
    with pytest.raises(RuntimeError, match="no se pudo contactar con el endpoint"):
        llmcheck.ping("http://paid/v1", "gpt-x", "sk")


def test_administrations_check_is_the_ping_too(client, engines, provider, monkeypatch):  # noqa: F811
    from mimirsynth import aistatus
    monkeypatch.setattr(aistatus, "_probe", lambda *a: 768)
    engines(LLM, "adm424")
    engines(DEC, "dadm424")
    s = client.get("/api/ai-status?check=true").json()
    assert s["llm"]["healthy"] and s["decider"]["healthy"]
    assert provider.count("adm424", "ping") == 1 and provider.count("adm424", "structured") == 0
    assert provider.count("dadm424", "ping") == 1 and provider.count("dadm424", "decider") == 0


def test_the_new_texts_have_their_english_entry():
    from mimirsynth import i18n_extract
    cat = i18n_extract.read_catalog(i18n_extract.CATALOG)
    help_text = appsettings.REGISTRY[[d.key for d in appsettings.REGISTRY].index("notify_health_minutes")].help
    assert [t for t in [*fitness.TITLES.values(), help_text, notify.EVENT_DOCS["model.unavailable"][0]] if not cat.get(t)] == []
