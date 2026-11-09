"""#420: the LLM checks ask for what ingestion needs (graphiti's structured output), not just an answer, and a failed ingestion caused
by the model's output says so in words. The three answers of the issue's table are simulated: a fenced ```json block with other keys
or a list (gemma4:31b-cloud), an empty answer with only reasoning (gpt-oss:120b-cloud) and a correct one; and the small model that
returns the schema but cannot link the entities (llama3.2:3b-instruct). There is no real LLM in CI."""
import json

import httpx
import pytest

from test_control import client  # noqa: F401  (fixture with the app and the test database)

from mimirsynth import llmcheck

GOOD = json.dumps({"extracted_entities": [{"name": "Alice Moreno", "entity_type_id": 0}, {"name": "Atlas billing server", "entity_type_id": 0}]})
FENCED_KEYS = "```json\n" + json.dumps({"entities": [{"name": "Alice Moreno", "type": "Person"}], "relations": []}) + "\n```"
FENCED_LIST = "```json\n" + json.dumps([{"name": "Alice Moreno"}, {"name": "Atlas billing server"}]) + "\n```"
LINKED = json.dumps({"edges": [{"source_entity_name": "Alice Moreno", "target_entity_name": "Atlas billing server", "relation_type": "MAINTAINS",
                                "fact": "Alice Moreno maintains the Atlas billing server."}]})
UNLINKED = json.dumps({"edges": [{"source_entity_name": "Alice Moreno", "target_entity_name": "MAINTAINS", "relation_type": "MAINTAINS",
                                  "fact": "Alice maintains it."}]})


def _answer(*contents, reasoning=None, status=200, sent=None):
    """A fake /chat/completions that answers each request with the next content."""
    queue = list(contents)

    def post(url, json=None, timeout=None, headers=None):  # noqa: A002
        if sent is not None:
            sent.append({"url": url, "body": json, "headers": headers})
        msg = {"role": "assistant", "content": queue.pop(0) if queue else ""}
        if reasoning:
            msg["reasoning"] = reasoning
        return httpx.Response(status, json={"choices": [{"message": msg}]} if status == 200 else {"error": "boom"},
                              request=httpx.Request("POST", url))
    return post


def test_a_correct_answer_returns_structured_output_with_graphitis_own_request(monkeypatch):
    sent = []
    monkeypatch.setattr(llmcheck.httpx, "post", _answer(GOOD, sent=sent))
    r = llmcheck.structured("http://llm/v1/", "qwen2.5:14b-instruct", "k")
    assert r["ok"] and r["structured"] is True and "warning" not in r
    assert r["reply"] == "devuelve salida estructurada: Alice Moreno, Atlas billing server"
    body = sent[0]["body"]
    assert sent[0]["url"] == "http://llm/v1/chat/completions" and sent[0]["headers"] == {"Authorization": "Bearer k"}
    assert body["response_format"]["type"] == "json_schema" and body["response_format"]["json_schema"]["name"] == "ExtractedEntities"
    assert "extracted_entities" in json.dumps(body["response_format"]["json_schema"]["schema"])
    assert body["max_tokens"] == 16384 and llmcheck.SENTENCE in body["messages"][-1]["content"]    # the same request as ingestion's


def test_gemma_fenced_json_with_other_keys_or_a_list_fails_in_words(monkeypatch):
    monkeypatch.setattr(llmcheck.httpx, "post", _answer(FENCED_KEYS))
    r = llmcheck.structured("http://llm/v1", "gemma4:31b-cloud")
    assert not r["ok"] and r["structured"] is False
    assert r["error"] == ("responde, pero no con un JSON que cumpla el esquema (lo envolvió en ``` y devolvió JSON con otras claves: "
                          "entities, relations): la ingesta fallará con este modelo")
    monkeypatch.setattr(llmcheck.httpx, "post", _answer(FENCED_LIST))
    r = llmcheck.structured("http://llm/v1", "gemma4:31b-cloud")
    assert "(lo envolvió en ``` y devolvió una lista)" in r["error"] and "la ingesta fallará" in r["error"]
    with pytest.raises(llmcheck.StructuredOutputError):
        llmcheck.require("http://llm/v1", "gemma4:31b-cloud")


def test_a_fence_alone_is_fine_because_graphiti_strips_it(monkeypatch):
    monkeypatch.setattr(llmcheck.httpx, "post", _answer("```json\n" + GOOD + "\n```"))
    assert llmcheck.structured("http://llm/v1", "m")["ok"]


def test_gpt_oss_empty_answer_with_only_reasoning_fails(monkeypatch):
    monkeypatch.setattr(llmcheck.httpx, "post", _answer("", reasoning="We need to extract entities..."))
    r = llmcheck.structured("http://llm/v1", "gpt-oss:120b-cloud")
    assert not r["ok"] and r["structured"] is False and "(no devolvió nada, solo su razonamiento)" in r["error"]
    monkeypatch.setattr(llmcheck.httpx, "post", _answer(""))
    assert "(no devolvió nada)" in llmcheck.structured("http://llm/v1", "m")["error"]
    monkeypatch.setattr(llmcheck.httpx, "post", _answer("Sure! Here are the entities: Alice, Atlas."))
    assert "(no devolvió JSON)" in llmcheck.structured("http://llm/v1", "m")["error"]


def test_the_quality_hint_warns_when_the_relation_does_not_come_back(monkeypatch):
    monkeypatch.setattr(llmcheck.httpx, "post", _answer(GOOD, LINKED))
    r = llmcheck.structured("http://llm/v1", "qwen2.5:14b-instruct", quality=True)
    assert r["ok"] and "warning" not in r
    monkeypatch.setattr(llmcheck.httpx, "post", _answer(GOOD, UNLINKED))           # llama3.2:3b: «Target entity not found… RUNS»
    r = llmcheck.structured("http://llm/v1", "llama3.2:3b-instruct", quality=True)
    assert r["ok"] and r["warning"] == llmcheck.WEAK


def test_an_endpoint_that_does_not_answer_is_not_a_structured_output_failure(monkeypatch):
    monkeypatch.setattr(llmcheck.httpx, "post", _answer(status=500))
    r = llmcheck.structured("http://llm/v1", "m")
    assert not r["ok"] and r["structured"] is None and r["error"].startswith("el endpoint respondió HTTP 500")
    with pytest.raises(RuntimeError) as e:
        llmcheck.require("http://llm/v1", "m")
    assert not isinstance(e.value, llmcheck.StructuredOutputError)

    def refuse(*a, **k):
        raise httpx.ConnectError("connection refused")
    monkeypatch.setattr(llmcheck.httpx, "post", refuse)
    assert llmcheck.structured("http://llm/v1", "m")["error"] == "no se pudo contactar con el endpoint: connection refused"


def test_the_decider_check_needs_one_letter_and_logprobs(monkeypatch):
    from mimirsynth import decider

    def answer(logprobs):
        def post(url, json=None, timeout=None, headers=None):  # noqa: A002
            ch = {"message": {"content": "B"}}
            if logprobs:
                ch["logprobs"] = {"content": [{"top_logprobs": [{"token": "B", "logprob": -0.05}, {"token": "A", "logprob": -3.0}]}]}
            return httpx.Response(200, json={"choices": [ch]}, request=httpx.Request("POST", url))
        return post
    monkeypatch.setattr(decider.httpx, "post", answer(True))
    r = llmcheck.decider("http://llm/v1", "m")
    assert r["ok"] and r["reply"].startswith("B (")
    monkeypatch.setattr(decider.httpx, "post", answer(False))
    r = llmcheck.decider("http://llm/v1", "m")
    assert not r["ok"] and r["error"] == llmcheck.NO_LOGPROBS
    with pytest.raises(RuntimeError):
        llmcheck.require_decider("http://llm/v1", "m")


# --- the failed ingestion, in words -------------------------------------------------------------------------------------------

def _raised(fn):
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        return e
    raise AssertionError("no exception")


def test_ingestion_failures_caused_by_the_model_output_are_put_into_words():
    from graphiti_core.llm_client.errors import EmptyResponseError
    from graphiti_core.prompts.extract_nodes import ExtractedEntities
    as_list = _raised(lambda: ExtractedEntities(**json.loads(FENCED_LIST.strip("`json\n"))))     # gemma: the issue's raw exception
    assert "argument after ** must be a mapping, not list" in str(as_list)
    other_keys = _raised(lambda: ExtractedEntities(**{"entities": []}))
    empty = _raised(lambda: json.loads(""))                                                        # gpt-oss: «Expecting value: line 1 column 1»
    cases = {as_list: "devolvió una lista", other_keys: "devolvió JSON con otras claves", empty: "no devolvió JSON",
             EmptyResponseError("LLM returned an empty response"): "no devolvió nada"}
    for exc, cause in cases.items():
        msg = llmcheck.ingest_failure(exc)
        assert msg == llmcheck.INGEST.replace("{{cause}}", cause), exc
        assert msg.startswith("El LLM no devolvió la respuesta estructurada que necesita la ingesta")
    wrapped = RuntimeError("extraction failed")
    wrapped.__cause__ = as_list
    assert "devolvió una lista" in llmcheck.ingest_failure(wrapped)
    assert llmcheck.ingest_failure(RuntimeError("LLM caído")) is None                              # anything else stays as it was
    from pydantic import BaseModel
    class Mine(BaseModel):  # noqa: E301
        x: int
    assert llmcheck.ingest_failure(_raised(lambda: Mine(x="no"))) is None                         # a validation error of our own


def test_a_failed_ingestion_shows_the_words_and_the_job_keeps_the_raw_error(client, monkeypatch):  # noqa: F811
    from graphiti_core.prompts.extract_nodes import ExtractedEntities

    from mimirsynth import ingest
    from mimirsynth.config import settings
    from mimirsynth.models import Job
    from mimirsynth.store import _factory
    monkeypatch.setattr(settings, "llm_base_url", "http://x"); monkeypatch.setattr(settings, "llm_model", "m")

    async def fake(graph, name, body, source, desc, ref, ontology=None, report=None):
        ExtractedEntities(**[{"name": "Alice"}])
    monkeypatch.setattr(ingest, "add_episode", fake)
    client.post("/api/brains", json={"slug": "ing420", "name": "Ing 420"})
    pid = client.post("/api/brains/ing420/proposals", json={"name": "lista", "body": "Alice Moreno maintains Atlas."}).json()["id"]
    p = {x["id"]: x for x in client.get("/api/brains/ing420/proposals").json()["items"]}[pid]
    assert p["status"] == "failed" and p["ingest_error"].startswith("El LLM no devolvió la respuesta estructurada")
    assert "(devolvió una lista)" in p["ingest_error"] and "must be a mapping" not in p["ingest_error"]
    with _factory()() as db:
        j = db.query(Job).filter(Job.kind == "proposal.ingest").order_by(Job.id.desc()).first()
        assert j.error.startswith("El LLM no devolvió") and any("must be a mapping, not list" in line["msg"] for line in j.log)


# --- where the check is used --------------------------------------------------------------------------------------------------

@pytest.fixture()
def engine(client):  # noqa: F811
    """Adds an LLM engine and makes it the default; afterwards it goes and the default before comes back (the test database is shared)."""
    before = next((e["id"] for e in client.get("/api/llm-engines").json() if e["is_default"]), None)
    made = []

    def add(name: str, model: str) -> int:
        eid = client.post("/api/llm-engines", json={"name": name, "base_url": f"http://{name}/v1", "model": model}).json()["id"]
        client.post(f"/api/llm-engines/{eid}/default")
        made.append(eid)
        return eid
    yield add
    for eid in made:
        client.delete(f"/api/llm-engines/{eid}")
    if before:
        client.post(f"/api/llm-engines/{before}/default")


def test_admin_test_and_health_use_the_structured_check(client, engine, monkeypatch):  # noqa: F811
    from mimirsynth import aistatus
    eid = engine("s420", "gemma4:31b-cloud")
    monkeypatch.setattr(llmcheck.httpx, "post", _answer(FENCED_LIST))
    r = client.post(f"/api/llm-engines/{eid}/test").json()
    assert not r["ok"] and "la ingesta fallará con este modelo" in r["error"]
    monkeypatch.setattr(llmcheck.httpx, "post", _answer(GOOD, UNLINKED))
    r = client.post(f"/api/llm-engines/{eid}/test").json()
    assert r["ok"] and r["reply"].startswith("devuelve salida estructurada") and r["warning"] == llmcheck.WEAK
    monkeypatch.setattr(aistatus, "_probe", lambda *a: 768)
    monkeypatch.setattr(llmcheck.httpx, "post", _answer("", reasoning="thinking"))
    s = client.get("/api/ai-status?check=true").json()
    assert s["llm"]["healthy"] is False and "no devolvió nada, solo su razonamiento" in s["llm"]["error"]
    assert s["llm"]["error"].endswith("la ingesta fallará con este modelo")                     # not cut halfway: it stays translatable


def test_the_health_notice_names_the_structured_output(client, engine, monkeypatch):  # noqa: F811
    from mimirsynth import notify
    engine("h420", "m")
    seen = []
    monkeypatch.setattr(notify, "_fail", lambda event, title, body, key: seen.append((event, title, body, key)))
    monkeypatch.setattr(notify, "_ok", lambda event, key: None)
    monkeypatch.setattr(llmcheck.httpx, "post", _answer(FENCED_KEYS))
    notify.check_health()
    llm = [s for s in seen if s[3] == "llm"]
    assert llm and llm[0][1] == "El modelo LLM no devuelve la salida estructurada que necesita la ingesta"
    assert "devolvió JSON con otras claves" in llm[0][2]


def test_the_wizard_does_not_pass_the_llm_step_on_a_model_that_fails_it(client, engine, monkeypatch):  # noqa: F811
    from mimirsynth import setupwizard
    engine("w420", "gpt-oss:120b-cloud")
    try:
        monkeypatch.setattr(llmcheck.httpx, "post", _answer(""))
        r = client.post("/api/setup/steps/llm", json={"action": "done"})
        assert r.status_code == 409 and r.json()["detail"] == (
            "el motor LLM responde, pero no con un JSON que cumpla el esquema (no devolvió nada): la ingesta fallará con este modelo. "
            "Prueba con otro modelo, o sáltate este paso")
        assert client.get("/api/llm-engines").json()                                           # the engine itself is kept
        monkeypatch.setattr(llmcheck.httpx, "post", _answer(GOOD))
        assert client.post("/api/setup/steps/llm", json={"action": "done"}).status_code == 200
    finally:
        from mimirsynth.models import AppSetting
        from mimirsynth.store import _factory
        with _factory()() as db:
            db.query(AppSetting).filter(AppSetting.key == setupwizard.KEY).delete()
            db.commit()


def test_every_text_of_the_check_has_its_english_entry():
    from mimirsynth import i18n_extract
    cat = i18n_extract.read_catalog(i18n_extract.CATALOG)
    texts = [llmcheck.FAILED, llmcheck.OK, llmcheck.WEAK, llmcheck.INGEST, llmcheck.FENCED, llmcheck.UNREACHABLE, llmcheck.HTTP,
             llmcheck.NO_LOGPROBS, *llmcheck.CAUSES.values(), "El modelo LLM no devuelve la salida estructurada que necesita la ingesta"]
    assert [t for t in texts if not cat.get(t)] == []
    from mimirsynth.i18n import translate
    msg = llmcheck._fill(llmcheck.FAILED, cause=llmcheck._fill(llmcheck.FENCED, cause=llmcheck._fill(llmcheck.CAUSES["keys_named"], keys="entities")))
    assert translate(msg, "en") == ("answers, but not with JSON that matches the schema (it wrapped it in ``` and returned JSON with other keys: "
                                    "entities): ingestion will fail with this model")
