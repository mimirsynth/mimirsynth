"""Corrector de tipos: el decisor propone el tipo de cada entidad (opciones cerradas = la ontología del brain) y un administrador
del brain aprueba. Aplicar cambia la etiqueta de tipo del nodo en el grafo; es reversible. Graphiti no reetiqueta nodos existentes."""
import logging
import re
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from . import decider, jobs
from .db import graph, rows
from .deciders_admin import default_decider
from .deps import BrainCtx, admin_of_brain, audit
from .models import Brain, RetypeSuggestion
from .ontology import NAME, get_ontology
from .secretbox import unseal
from .store import _factory

log = logging.getLogger("mimirsynth.retype")
router = APIRouter(prefix="/api/brains/{slug}/retype")
# Tipos genéricos que suelen ser clasificaciones erróneas de entidades de infraestructura: se revisan primero.
SUSPECT = ["Object", "Organization", "Location", "Topic", "Document", "Preference", "Requirement", "Procedure", "Event", "Person"]
_PROGRESS: dict[int, dict] = {}
_FILE = re.compile(r"\.(py|js|ts|tsx|json|ya?ml|md|sh|conf|cfg|toml|log|txt|html|css|service|env)\b", re.I)
_VERSION = re.compile(r"(\s[vV]?\d+(\.\d+){1,3}([-.\w]*)?$)|(\b[vV]\d+\.\d+)")
_PROBLEM = re.compile(r"\b(bug|error|issue|fix|fallo|problema)\b", re.I)


def doubtful_reason(name: str) -> str:
    """Heurística barata: nombres que no son una entidad concreta de infraestructura (no tiene sentido darles un tipo)."""
    n = (name or "").strip()
    if re.search(r"[\\/]", n) or _FILE.search(n):
        return "ruta o nombre de fichero"
    if n.startswith("-"):
        return "opción de línea de comandos"
    if re.search(r"[=()]|::", n):
        return "expresión de código"
    if _VERSION.search(n):
        return "versión en el nombre (¿fusionar con la entidad base?)"
    if len(n.split()) >= 5:
        return "frase, no un nombre propio"
    if _PROBLEM.search(n):
        return "descripción de un problema"
    return ""
_LOCK = threading.Lock()


def _candidates(graph_name: str, skip: set[str], limit: int) -> list[dict]:
    q = ("MATCH (n:Entity) WITH n, [l IN labels(n) WHERE l <> 'Entity'] AS ts "
         "WHERE size(ts) = 0 OR ts[0] IN $suspect "
         "RETURN n.uuid AS uuid, n.name AS name, coalesce(ts[0], '') AS type, left(coalesce(n.summary, ''), 400) AS summary")
    out = [r for r in rows(graph(graph_name).query(q, {"suspect": SUSPECT})) if r["uuid"] not in skip]
    return out[:limit]


def _facts(graph_name: str, uuid: str) -> list[str]:
    q = "MATCH (n:Entity {uuid:$u})-[r:RELATES_TO]-() RETURN r.fact AS f LIMIT 4"
    return [r["f"] for r in rows(graph(graph_name).query(q, {"u": uuid})) if r["f"]]


def _set_label(graph_name: str, uuid: str, old: str, new: str) -> None:
    for t in (old, new):
        if t and not NAME.match(t):
            raise HTTPException(400, f"tipo inválido: {t}")
    g = graph(graph_name)
    if old:
        g.query(f"MATCH (n:Entity {{uuid:$u}}) REMOVE n:`{old}`", {"u": uuid})
    if new:
        g.query(f"MATCH (n:Entity {{uuid:$u}}) SET n:`{new}`", {"u": uuid})


def _options(onto: dict) -> tuple[list[str], list[str]]:
    types = [t["name"] for t in onto["entity_types"]]
    labels = [f'{t["name"]}: {t["description"][:110]}' for t in onto["entity_types"]] + ["Ninguno de los anteriores"]
    return types, labels


def scan(brain_id: int, graph_name: str, limit: int, job=None) -> None:
    with _factory()() as db:
        onto = get_ontology(db, brain_id)
        d = default_decider(db)
        if not onto or not d:
            return
        types, labels = _options(onto)
        skip = set(db.scalars(select(RetypeSuggestion.entity_uuid).where(RetypeSuggestion.brain_id == brain_id)))
        brain = db.get(Brain, brain_id)
        context = decider.scope(brain.name, brain.description, onto) if brain else ""
        cands = _candidates(graph_name, skip, limit)
        _PROGRESS[brain_id] = {"running": True, "done": 0, "total": len(cands), "error": None}
        key = unseal(d.api_key_enc)
        for c in cands:
            if job:
                job.progress(_PROGRESS[brain_id]["done"], len(cands), f"analizando «{c['name'][:60]}»")
                try:
                    job.check()
                except Exception:
                    _PROGRESS[brain_id]["running"] = False
                    raise
            try:
                why = doubtful_reason(c["name"])
                if why:
                    db.add(RetypeSuggestion(brain_id=brain_id, entity_uuid=c["uuid"], name=c["name"][:500], current_type=c["type"], status="doubtful", reason=why))
                    db.commit()
                    _PROGRESS[brain_id]["done"] += 1
                    continue
                facts = _facts(graph_name, c["uuid"])
                state = decider.with_scope(f"Entidad: {c['name']}\nResumen: {c['summary'][:300]}\nHechos:\n" + "\n".join(f"- {f[:160]}" for f in facts), context)
                ent = decider.decide(d.base_url, d.model, key, state, "¿Es una entidad concreta con nombre propio (una persona, organización, lugar, objeto, servicio, proyecto…), y no una frase, un fichero, una opción, un error o un procedimiento?", ["Sí", "No"])
                if ent["letter"] == "B" and ent["prob"] >= 0.7:
                    db.add(RetypeSuggestion(brain_id=brain_id, entity_uuid=c["uuid"], name=c["name"][:500], current_type=c["type"], status="doubtful",
                                            reason=f"el decisor no la ve como una entidad concreta ({ent['prob']})", confidence=ent["prob"]))
                    db.commit()
                    _PROGRESS[brain_id]["done"] += 1
                    continue
                r = decider.decide(d.base_url, d.model, key, state, "¿Qué tipo de entidad es, según los tipos de la ontología de este brain?", labels)
                sug = types[r["index"]] if r["index"] < len(types) else ""
                status = "pending" if sug and sug != c["type"] else "same"
                db.add(RetypeSuggestion(brain_id=brain_id, entity_uuid=c["uuid"], name=c["name"][:500], current_type=c["type"], suggested_type=sug,
                                        confidence=r["prob"], status=status))
                db.commit()
            except Exception as e:  # noqa: BLE001
                log.warning("retype %s: %s", c["name"], e)
                if job:
                    job.note(f"«{c['name'][:60]}»: {str(e)[:150]}")
                db.rollback()
                _PROGRESS[brain_id]["error"] = str(e)[:150]
            _PROGRESS[brain_id]["done"] += 1
        _PROGRESS[brain_id]["running"] = False


@jobs.register("retype.scan", "Corrector de tipos", limit=1)
def _job_scan(ctx, p: dict) -> dict:
    try:
        scan(ctx.brain_id, p["graph"], p["limit"], ctx)
    finally:
        if ctx.brain_id in _PROGRESS:
            _PROGRESS[ctx.brain_id]["running"] = False
    pr = _PROGRESS.get(ctx.brain_id, {})
    if pr.get("error"):
        raise RuntimeError(f"terminó con errores; el último: {pr['error']}")
    return {"analyzed": pr.get("done", 0)}


class ScanIn(BaseModel):
    limit: int = Field(100, ge=1, le=1000)


class IdsIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=2000)


def _out(s: RetypeSuggestion) -> dict:
    return {"id": s.id, "entity_uuid": s.entity_uuid, "name": s.name, "current_type": s.current_type, "suggested_type": s.suggested_type,
            "confidence": s.confidence, "status": _eff_status(s), "previous_type": s.previous_type, "reason": s.reason or (doubtful_reason(s.name) if s.status == "pending" else ("ninguno de los tipos de la ontología encaja" if _eff_status(s) == "none" else ""))}


def _eff_status(s: RetypeSuggestion) -> str:
    """Las propuestas antiguas cuyo nombre no es una entidad concreta pasan a «dudosas» sin volver a analizarlas."""
    if s.status == "pending" and doubtful_reason(s.name):
        return "doubtful"
    if s.status == "same" and not s.suggested_type:  # el decisor contestó «ninguno de los anteriores»: no es lo mismo que «ya correcto»
        return "none"
    return s.status


@router.get("")
def overview(status: str = "pending", min_conf: float = 0.0, limit: int = 300, ctx: BrainCtx = Depends(admin_of_brain)):
    onto = get_ontology(ctx.db, ctx.brain.id)
    allrows = ctx.db.scalars(select(RetypeSuggestion).where(RetypeSuggestion.brain_id == ctx.brain.id)).all()
    counts: dict[str, int] = {}
    for r in allrows:
        counts[_eff_status(r)] = counts.get(_eff_status(r), 0) + 1
    in_status = sorted((r for r in allrows if _eff_status(r) == status), key=lambda r: -(r.confidence or 0))
    shown = [r for r in in_status if status != "pending" or (r.confidence or 0) >= min_conf]
    return {"ontology": bool(onto), "decider": default_decider(ctx.db) is not None, "counts": counts, "hidden_below_threshold": len(in_status) - len(shown),
            "progress": _PROGRESS.get(ctx.brain.id, {"running": False, "done": 0, "total": 0, "error": None}), "items": [_out(r) for r in shown[:min(limit, 1000)]]}


@router.post("/scan", status_code=202)
def start_scan(body: ScanIn, bg: BackgroundTasks, ctx: BrainCtx = Depends(admin_of_brain)):
    if not get_ontology(ctx.db, ctx.brain.id):
        raise HTTPException(409, "el brain no tiene ontología: aplica un paquete antes")
    if not default_decider(ctx.db):
        raise HTTPException(409, "no hay un decisor configurado (Administración → Proveedores IA)")
    with _LOCK:
        if _PROGRESS.get(ctx.brain.id, {}).get("running"):
            raise HTTPException(409, "ya hay un análisis en curso")
        _PROGRESS[ctx.brain.id] = {"running": True, "done": 0, "total": body.limit, "error": None}
    audit(ctx.db, ctx.user, "retype.scan", ctx.brain, limit=body.limit)
    return {"started": True, "job": jobs.submit("retype.scan", ctx.brain.id, {"limit": body.limit, "graph": ctx.brain.graph_name},
                                                 f"Corrector de tipos: analizar hasta {body.limit} entidades", ctx.user.id, dedupe_key=f"retype.scan:{ctx.brain.id}")}


def _pick(ctx: BrainCtx, ids: list[int], status: str) -> list[RetypeSuggestion]:
    """Filas con ese estado real; las dudosas por heurística no se pueden aplicar como cambio de tipo."""
    rows_ = ctx.db.scalars(select(RetypeSuggestion).where(RetypeSuggestion.brain_id == ctx.brain.id, RetypeSuggestion.id.in_(ids), RetypeSuggestion.status == status)).all()
    return [r for r in rows_ if status != "pending" or not doubtful_reason(r.name)]


@router.post("/apply")
def apply(body: IdsIn, ctx: BrainCtx = Depends(admin_of_brain)):
    onto = get_ontology(ctx.db, ctx.brain.id) or {"entity_types": []}
    allowed = {t["name"] for t in onto["entity_types"]}
    n = 0
    for s in _pick(ctx, body.ids, "pending"):
        if s.suggested_type not in allowed:
            continue
        _set_label(ctx.brain.graph_name, s.entity_uuid, s.current_type, s.suggested_type)
        s.previous_type, s.status, s.applied_at = s.current_type, "applied", datetime.now(timezone.utc)
        n += 1
    ctx.db.commit()
    audit(ctx.db, ctx.user, "retype.apply", ctx.brain, count=n)
    return {"applied": n}


@router.post("/reject")
def reject(body: IdsIn, ctx: BrainCtx = Depends(admin_of_brain)):
    items = list(ctx.db.scalars(select(RetypeSuggestion).where(RetypeSuggestion.brain_id == ctx.brain.id, RetypeSuggestion.id.in_(body.ids),
                                                              RetypeSuggestion.status.in_(["pending", "doubtful"]))))
    for s in items:
        s.status = "rejected"
    ctx.db.commit()
    return {"rejected": len(items)}


@router.post("/{sid}/revert")
def revert(sid: int, ctx: BrainCtx = Depends(admin_of_brain)):
    s = ctx.db.get(RetypeSuggestion, sid)
    if not s or s.brain_id != ctx.brain.id or s.status != "applied":
        raise HTTPException(404, "no hay un cambio aplicado con ese id")
    _set_label(ctx.brain.graph_name, s.entity_uuid, s.suggested_type, s.previous_type)
    s.status = "reverted"
    ctx.db.commit()
    audit(ctx.db, ctx.user, "retype.revert", ctx.brain, id=sid)
    return {"ok": True}
