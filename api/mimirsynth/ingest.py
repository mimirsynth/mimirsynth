"""Ingesta: convierte propuestas aprobadas en episodios de Graphiti (graphiti-core como librería, sobre el FalkorDB del stack)."""
import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from . import appsettings, ontology as ontology_mod
from .config import settings

os.environ.setdefault("SEMAPHORE_LIMIT", str(settings.ingest_concurrency))  # antes de importar graphiti_core
log = logging.getLogger("mimirsynth.ingest")


def _engine() -> dict | None:
    """Motor por defecto de la base de datos; si no hay, el configurado por variables de entorno."""
    from . import llm
    from .store import _factory
    try:
        with _factory()() as db:
            e = llm.resolve(db)
        if e:
            return e
    except Exception:  # noqa: BLE001
        log.exception("no se pudo leer el motor LLM de la base de datos")
    if settings.llm_base_url and settings.llm_model:
        return {"base_url": settings.llm_base_url, "api_key": settings.llm_api_key, "model": settings.llm_model,
                "small_model": settings.llm_small_model or settings.llm_model}
    return None


def enabled() -> bool:
    return _engine() is not None


async def add_episode(graph_name: str, name: str, body: str, source: str, description: str, reference_time: datetime | None,
                      ontology: dict | None = None, report: dict | None = None) -> str:
    from graphiti_core import Graphiti
    from graphiti_core.cross_encoder.client import CrossEncoderClient
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    from graphiti_core.nodes import EpisodeType

    class NoRerank(CrossEncoderClient):  # add_episode no reordena; evita depender de una clave de OpenAI
        async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
            return [(p, 1.0) for p in passages]

    eng = _engine()
    if not eng:
        raise RuntimeError("no hay motor LLM configurado")
    llm = OpenAIGenericClient(config=LLMConfig(api_key=eng["api_key"] or "none", model=eng["model"], small_model=eng["small_model"], base_url=eng["base_url"]))
    from .embed import resolve_embedding
    ee = resolve_embedding()
    emb = OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key=ee["api_key"] or "none", embedding_model=ee["model"], base_url=ee["base_url"], embedding_dim=ee["dim"]))
    g = Graphiti(graph_driver=FalkorDriver(host=settings.falkor_host, port=settings.falkor_port, database=graph_name),
                 llm_client=llm, embedder=emb, cross_encoder=NoRerank())
    started = datetime.now(timezone.utc) - timedelta(seconds=5)
    try:
        res = await g.add_episode(name=name, episode_body=body, source=EpisodeType[source if source in EpisodeType.__members__ else "text"],
                                  source_description=description or "mimirsynth", reference_time=reference_time or datetime.now(timezone.utc),
                                  group_id=graph_name, **(ontology_mod.to_graphiti(ontology) if ontology else {}))
        if report is not None:
            allowed = {ontology_mod.canon(t["name"]) for t in (ontology or {}).get("edge_types", [])}
            names = [e.name for e in res.edges]
            report.update({"entities": len(res.nodes), "edges": len(names), "ontology": bool(ontology),
                           "off_ontology": sorted({n for n in names if allowed and ontology_mod.canon(n) not in allowed}),
                           "untyped_entities": sum(1 for n in res.nodes if not [l for l in n.labels if l not in ("Entity", "Entity_")]),
                           "_edges": [(str(e.uuid), e.name) for e in res.edges],
                           "_nodes": [(str(n.uuid), n.name, bool(n.created_at and n.created_at >= started)) for n in res.nodes]})
        return str(res.episode.uuid)
    finally:
        await g.close()


def ingest_proposal(pid: int, job=None) -> str:
    """Ejecuta la ingesta de una propuesta aprobada y deja el resultado en su estado (ingested | failed). Devuelve el error (vacío si fue bien)."""
    from .deps import audit
    from .models import Brain, Proposal
    from .store import _factory
    with _factory()() as db:
        p = db.get(Proposal, pid)
        if not p or p.status not in ("approved", "failed"):
            return ""
        brain = db.get(Brain, p.brain_id)
        try:
            onto = ontology_mod.get_ontology(db, brain.id)
            for attempt in range(1, appsettings.get("ingest_retries") + 1):
                rep: dict = {}
                try:
                    uuid = asyncio.run(add_episode(brain.graph_name, p.name, p.body, p.source, p.source_description, p.reference_time, ontology=onto, report=rep))
                    break
                except Exception as e:  # noqa: BLE001
                    msg = str(e).lower()
                    transient = "rate limit" in msg or "failed to generate completions" in msg or "error code: 5" in msg or "timed out" in msg
                    if attempt == appsettings.get("ingest_retries") or not transient:
                        raise
                    wait = 60 * attempt
                    log.warning("error transitorio del LLM (límite de tasa o 5xx) en la propuesta %s (intento %s): reintento en %ss", pid, attempt, wait)
                    if job:
                        job.retrying(f"error transitorio del LLM (intento {attempt}): reintento en {wait}s")
                    time.sleep(wait)
            from . import vocab_apply
            vocab_apply.apply(db, brain, rep)
            p.status, p.episode_uuid, p.ingest_error, p.ingested_at, p.ingest_report = "ingested", uuid, "", datetime.now(timezone.utc), rep or None
        except Exception as e:  # noqa: BLE001
            log.exception("ingesta fallida de la propuesta %s", pid)
            p.status, p.ingest_error = "failed", str(e)[:500]
        db.commit()
        err = p.ingest_error if p.status == "failed" else ""
        audit(db, None, f"proposal.{p.status}", brain, id=p.id)
        return err


def submit_ingest(pid: int, brain_id: int, name: str, user_id: int | None = None) -> int:
    from . import jobs
    return jobs.submit("proposal.ingest", brain_id, {"pid": pid}, f"Ingerir propuesta #{pid}: {name[:80]}", user_id, dedupe_key=f"proposal.ingest:{pid}")


def _register() -> None:
    from . import jobs

    @jobs.register("proposal.ingest", "Ingesta al grafo", limit=1, resume=False)
    def _job(ctx, p: dict) -> dict:
        ctx.progress(0, 0, "extrayendo hechos con el LLM")
        err = ingest_proposal(p["pid"], ctx)
        if err:
            raise RuntimeError(err)
        return {"proposal": p["pid"]}


_register()
