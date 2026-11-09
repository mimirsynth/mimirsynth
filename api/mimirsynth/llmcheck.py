"""Does the LLM return what ingestion needs (#420)? Answering is not enough: graphiti-core asks the model for JSON that matches a schema
(`response_format` with a JSON schema) and turns it into its own objects. A model that ignores the schema, returns a list or returns
nothing passes a plain «say ok» and then fails every ingestion with a raw Python exception.

- `structured` sends the model the same request ingestion sends first: graphiti's entity-extraction prompt on a fixed sentence, with the
  JSON schema of its `ExtractedEntities`, the same temperature and token limit, and parses the answer the way graphiti does (a ```json
  fence is stripped, as graphiti strips it). With `quality`, a second request asks for the relation between the two entities, the way
  graphiti's edge extraction does, and warns when it does not come back (a model too small to link entities: 0 facts).
- `require` is the same check for the places that only need yes or no (the wizard's step, the health checks): it raises a
  `StructuredOutputError` with the reason in words.
- `ingest_failure` puts a failed ingestion into words when its cause is the model's output; the raw exception goes to the job's log.
- `decider` checks the decider's own mechanism: one letter of the options, with logprobs. Without them it can never approve alone.

Every text is in Spanish, the server's source language, with its English entry in the server catalogue."""
import json
import re
import time
from datetime import datetime, timezone

import httpx

from .i18n import T

SENTENCE = "Alice Moreno maintains the Atlas billing server."
TIMEOUT = 120  # a local model on a CPU reads the extraction prompt (about 1,500 tokens) slowly; the provider's own limit is the same

FAILED = T("responde, pero no con un JSON que cumpla el esquema ({{cause}}): la ingesta fallará con este modelo")
OK = T("devuelve salida estructurada: {{entities}}")
WEAK = T("devuelve salida estructurada, pero no relacionó las dos entidades de la frase de prueba: con este modelo la ingesta guardará "
        "entidades sin hechos. Suele pasar con modelos demasiado pequeños; prueba uno más grande")
INGEST = T("El LLM no devolvió la respuesta estructurada que necesita la ingesta ({{cause}}). Prueba con otro modelo: los modelos instruct "
          "(como qwen2.5:14b-instruct) suelen funcionar; los de razonamiento o los «cloud» servidos por Ollama a menudo no. "
          "El error original está en el detalle del trabajo.")
CAUSES = {
    "empty": T("no devolvió nada"),
    "reasoning": T("no devolvió nada, solo su razonamiento"),
    "list": T("devolvió una lista"),
    "not_json": T("no devolvió JSON"),
    "keys": T("devolvió JSON con otras claves"),
    "keys_named": T("devolvió JSON con otras claves: {{keys}}"),
    "fields": T("devolvió entidades sin los campos del esquema"),
}
FENCED = T("lo envolvió en ``` y {{cause}}")
UNREACHABLE = T("no se pudo contactar con el endpoint: {{v}}")  # the same texts as before, already in the catalogue
HTTP = T("el endpoint respondió HTTP {{status_code}}: {{text}}")


class StructuredOutputError(RuntimeError):
    """The model answers, but not with JSON that matches the schema: ingestion will fail with it."""


def _fill(template: str, **values) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(values[m.group(1)]), template)


def _client(base_url: str, model: str, api_key: str):
    """graphiti's own client, only to build the request as ingestion does (it is never used to send it)."""
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    return OpenAIGenericClient(config=LLMConfig(api_key=api_key or "none", model=model, base_url=base_url), client=object())


def _request(base_url: str, model: str, api_key: str, messages, response_model, timeout: float) -> tuple[dict, str]:
    """One request as graphiti's `OpenAIGenericClient` makes it. Returns (the message, its text); raises RuntimeError when the endpoint
    cannot be reached or does not answer 200."""
    from graphiti_core.llm_client.client import get_extraction_language_instruction
    c = _client(base_url, model, api_key)
    messages[0].content += get_extraction_language_instruction(None)
    body = {"model": model, "temperature": c.temperature, "max_tokens": c.max_tokens,
            "messages": [{"role": m.role, "content": c._clean_input(m.content)} for m in messages],
            "response_format": c._build_response_format(response_model)}
    try:
        r = httpx.post(f"{base_url.rstrip('/')}/chat/completions", json=body, timeout=timeout,
                       headers={"Authorization": f"Bearer {api_key}"} if api_key else {})
    except Exception as ex:  # noqa: BLE001
        raise RuntimeError(_fill(UNREACHABLE, v=str(ex)[:150])) from None
    if r.status_code != 200:
        raise RuntimeError(_fill(HTTP, status_code=r.status_code, text=r.text[:150]))
    try:
        msg = (r.json().get("choices") or [{}])[0].get("message") or {}
    except ValueError:
        msg = {}
    return msg, msg.get("content") or ""


def parse(msg: dict, text: str, model_cls) -> tuple[object | None, str]:
    """The answer as graphiti reads it: (the parsed object, "") or (None, why it failed, in words)."""
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    from pydantic import ValidationError
    fenced = text.strip().startswith("```")

    def why(code: str) -> str:
        return _fill(FENCED, cause=CAUSES[code]) if fenced else CAUSES[code]
    if not text.strip():
        return None, CAUSES["reasoning" if (msg.get("reasoning_content") or msg.get("reasoning")) else "empty"]
    try:
        data = json.loads(OpenAIGenericClient._strip_code_fences(text))
    except ValueError:
        return None, why("not_json")
    if isinstance(data, list):
        return None, why("list")
    if not isinstance(data, dict):
        return None, why("not_json")
    try:
        return model_cls(**data), ""
    except ValidationError:
        if set(model_cls.model_fields) & set(data):
            return None, why("fields")
        if not data:
            return None, why("keys")
        cause = _fill(CAUSES["keys_named"], keys=", ".join(sorted(data)[:6]))
        return None, _fill(FENCED, cause=cause) if fenced else cause


def _entities_prompt():
    from graphiti_core.prompts import prompt_library
    from graphiti_core.utils.maintenance.node_operations import _build_entity_types_context
    return prompt_library.extract_nodes.extract_text({
        "episode_content": SENTENCE, "episode_timestamp": datetime.now(timezone.utc).isoformat(), "previous_episodes": [],
        "custom_extraction_instructions": "", "entity_types": _build_entity_types_context(None), "source_description": "mimirsynth"})


def _edges_prompt(names: list[str]):
    from graphiti_core.prompts import prompt_library
    return prompt_library.extract_edges.edge({
        "episode_content": SENTENCE, "nodes": [{"name": n, "entity_types": ["Entity"]} for n in names], "previous_episodes": [],
        "reference_time": datetime.now(timezone.utc), "edge_types": [], "custom_extraction_instructions": ""})


def structured(base_url: str, model: str, api_key: str = "", quality: bool = False, timeout: float = TIMEOUT) -> dict:
    """{ok, ms, reply | error, warning?}: whether the model returns the structured output ingestion needs. `quality` adds the relation."""
    from graphiti_core.prompts.extract_edges import ExtractedEdges
    from graphiti_core.prompts.extract_nodes import ExtractedEntities
    t0 = time.monotonic()
    ms = lambda: int((time.monotonic() - t0) * 1000)  # noqa: E731
    try:
        msg, text = _request(base_url, model, api_key, _entities_prompt(), ExtractedEntities, timeout)
    except RuntimeError as e:
        return {"ok": False, "ms": ms(), "error": str(e), "structured": None}
    got, why = parse(msg, text, ExtractedEntities)
    if got is None:
        return {"ok": False, "ms": ms(), "error": _fill(FAILED, cause=why), "structured": False}
    names = [e.name for e in got.extracted_entities if e.name.strip()]
    out = {"ok": True, "ms": ms(), "reply": _fill(OK, entities=", ".join(names) or "—"), "structured": True}
    if quality:
        linked = False
        if len(names) >= 2:
            try:
                msg, text = _request(base_url, model, api_key, _edges_prompt(names), ExtractedEdges, timeout)
                edges, _ = parse(msg, text, ExtractedEdges)
                linked = bool(edges) and any(e.source_entity_name in names and e.target_entity_name in names
                                             and e.source_entity_name != e.target_entity_name for e in edges.edges)
            except RuntimeError:
                linked = True  # the endpoint failed on the second request: no verdict on the model's size
        if not linked:
            out["warning"] = WEAK
        out["ms"] = ms()
    return out


def require(base_url: str, model: str, api_key: str = "", timeout: float = TIMEOUT) -> None:
    """Raises RuntimeError when the endpoint does not answer and StructuredOutputError when the model's answer would fail ingestion."""
    r = structured(base_url, model, api_key, timeout=timeout)
    if not r["ok"]:
        raise (StructuredOutputError if r["structured"] is False else RuntimeError)(r["error"])


def ingest_failure(exc: BaseException) -> str | None:
    """A failed ingestion in words when the model's output caused it (empty, not JSON, a list, other keys), else None."""
    from graphiti_core.llm_client.errors import EmptyResponseError
    from pydantic import ValidationError
    seen, e = set(), exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        last = getattr(e, "last_attempt", None)  # tenacity's RetryError, when it does not reraise
        if last is not None and hasattr(last, "exception") and last.exception() is not None:
            e = last.exception()
            continue
        if isinstance(e, EmptyResponseError):
            return _fill(INGEST, cause=CAUSES["empty"])
        if isinstance(e, json.JSONDecodeError):
            return _fill(INGEST, cause=CAUSES["not_json"])
        if isinstance(e, TypeError) and "must be a mapping" in str(e):
            return _fill(INGEST, cause=CAUSES["list"])
        if isinstance(e, ValidationError) and _graphiti_model(e):
            return _fill(INGEST, cause=CAUSES["keys"])
        e = e.__cause__ or e.__context__
    return None


def _graphiti_model(e) -> bool:
    """A validation error of one of graphiti's prompt models (what the LLM answered), not of anything else."""
    import importlib
    import pkgutil

    import graphiti_core.prompts as gp
    title = getattr(e, "title", "") or ""
    for m in pkgutil.iter_modules(gp.__path__):
        if isinstance(getattr(importlib.import_module(f"graphiti_core.prompts.{m.name}"), title, None), type):
            return True
    return False


NO_LOGPROBS = T("responde, pero sin logprobs: el decisor no puede medir su confianza y nunca aprobará solo. Usa un modelo o un proveedor que los devuelva")


def decider(base_url: str, model: str, api_key: str = "", timeout: float = 60) -> dict:
    """The decider's own mechanism: one letter of the options with logprobs (it never asks for JSON). {ok, ms, reply | error}."""
    from . import decider as _decider
    t0 = time.monotonic()
    try:
        r = _decider.decide(base_url, model, api_key, "Entidad: 'Nextcloud'", "¿Qué tipo de entidad es?",
                            ["Persona", "Servicio de software", "Dispositivo físico", "Ubicación"], timeout=timeout)
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "ms": int((time.monotonic() - t0) * 1000), "error": str(getattr(ex, "detail", None) or ex)[:300]}
    ms = int((time.monotonic() - t0) * 1000)
    if not r["probs"]:
        return {"ok": False, "ms": ms, "error": NO_LOGPROBS}
    return {"ok": True, "ms": ms, "reply": f"{r['letter']} ({r['prob']}) {r['probs']}"}


def require_decider(base_url: str, model: str, api_key: str = "", timeout: float = 60) -> None:
    r = decider(base_url, model, api_key, timeout=timeout)
    if not r["ok"]:
        raise RuntimeError(r["error"])
