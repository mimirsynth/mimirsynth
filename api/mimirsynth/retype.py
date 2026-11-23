"""Corrector de tipos: el decisor propone el tipo de cada entidad (opciones cerradas = la ontología del brain) y un administrador
del brain aprueba. Aplicar cambia la etiqueta de tipo del nodo en el grafo; es reversible. Graphiti no reetiqueta nodos existentes.
Qué se revisa y qué se descarta antes del decisor lo decide el paquete de ontología del brain (bloque `retype`), no un dominio fijo."""
import logging
import re
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from . import decider, jobs
from .db import graph, rows
from .deciders_admin import default_decider
from .deps import BrainCtx, admin_of_brain, audit, curator_of_brain
from .models import Brain, RetypeSuggestion
from .ontology import ALIASES, NAME, get_ontology, presets
from .secretbox import unseal
from .store import _factory

log = logging.getLogger("mimirsynth.retype")
router = APIRouter(prefix="/api/brains/{slug}/retype")
entity_router = APIRouter(prefix="/api/brains/{slug}/entities")  # the type of one entity, changed by hand (#179)
# Cómo se revisa un brain cuyo paquete no dice nada (ontología a mano, paquete retirado): solo los comodines y las reglas de cualquier dominio.
MINIMAL = {"review_first": ["Object", "Thing", "Topic"], "doubtful_rules": []}
# Si la ontología tiene tipos para errores o procedimientos, la pregunta del decisor no los excluye.
ERROR_TYPES = {"Bug", "Incident", "Issue", "Error", "Problem"}
PROCEDURE_TYPES = {"Runbook", "Procedure", "Howto"}
_PROGRESS: dict[int, dict] = {}
_FILE = re.compile(r"\.(py|js|ts|tsx|json|ya?ml|md|sh|conf|cfg|toml|log|txt|html|css|service|env)\b", re.I)
_VERSION = re.compile(r"(\s[vV]?\d+(\.\d+){1,3}([-.\w]*)?$)|(\b[vV]\d+\.\d+)")
_PROBLEM = re.compile(r"\b(bug|error|issue|fix|fallo|problema)\b", re.I)
# Reglas técnicas, en el orden en que se comprueban; cada paquete activa las suyas en `retype.doubtful_rules`.
RULES = {
    "file": (lambda n: bool(re.search(r"[\\/]", n) or _FILE.search(n)), "ruta o nombre de fichero"),
    "option": (lambda n: n.startswith("-"), "opción de línea de comandos"),
    "code": (lambda n: bool(re.search(r"[=()]|::", n)), "expresión de código"),
    "version": (lambda n: bool(_VERSION.search(n)), "versión en el nombre (¿fusionar con la entidad base?)"),
    "problem": (lambda n: bool(_PROBLEM.search(n)), "descripción de un problema"),
}


def profile(onto: dict | None) -> dict:
    """Cómo revisa el corrector un brain: el bloque `retype` de su paquete de ontología (o el mínimo) y los tipos que tiene."""
    name = ((onto or {}).get("preset") or {}).get("name", "")
    block = (presets().get(ALIASES.get(name, name)) or {}).get("retype") or MINIMAL
    types = {t["name"] for t in (onto or {}).get("entity_types", [])}
    rules = set(block["doubtful_rules"]) - ({"version"} if "Software" in types else set())   # «Debian 13» is a Software (#467)
    return {"review_first": list(block["review_first"]), "rules": frozenset(rules), "types": types}


def doubtful_reason(name: str, rules: frozenset[str] | set[str]) -> str:
    """Heurística barata: nombres que no son una entidad concreta (no tiene sentido darles un tipo). La de frase vale en cualquier
    dominio; las técnicas solo si el paquete del brain las activa."""
    n = (name or "").strip()
    for key in ("file", "option", "code", "version"):
        if key in rules and RULES[key][0](n):
            return RULES[key][1]
    if len(n.split()) >= 5:
        return "frase, no un nombre propio"
    if "problem" in rules and RULES["problem"][0](n):
        return RULES["problem"][1]
    return ""
_LOCK = threading.Lock()


def _entity_question(types: set[str]) -> str:
    no = ["una frase", "un fichero", "una opción"]
    no += [] if types & ERROR_TYPES else ["un error"]
    no += [] if types & PROCEDURE_TYPES else ["un procedimiento"]
    return ("¿Es una entidad concreta con nombre propio (una persona, organización, lugar, objeto, servicio, proyecto…), y no "
            + ", ".join(no[:-1]) + " o " + no[-1] + "?")


def _priority(t: str, types: set[str], first: list[str]) -> int | None:
    """Prioridad de revisión según el tipo actual (menor = antes): sin tipo, tipo ajeno a la ontología, tipo que el paquete revisa
    primero. None: no se revisa."""
    if not t:
        return 0
    if t not in types:
        return 1
    return 2 if t in first else None


def rank(cands: list[dict], prof: dict, skip: set[str], limit: int) -> list[dict]:
    """Cola del análisis: por prioridad y, a igual prioridad, por uuid, para que dos análisis seguidos no la reordenen."""
    keyed = [(_priority(c["type"], prof["types"], prof["review_first"]), c["uuid"], c) for c in cands if c["uuid"] not in skip]
    return [c for _, _, c in sorted((k for k in keyed if k[0] is not None), key=lambda k: k[:2])][:limit]


def _candidates(graph_name: str, prof: dict, skip: set[str], limit: int) -> list[dict]:
    q = ("MATCH (n:Entity) WITH n, [l IN labels(n) WHERE l <> 'Entity'] AS ts "
         "WHERE size(ts) = 0 OR NOT ts[0] IN $types OR ts[0] IN $first "
         "RETURN n.uuid AS uuid, n.name AS name, coalesce(ts[0], '') AS type, left(coalesce(n.summary, ''), 400) AS summary")
    found = rows(graph(graph_name).query(q, {"types": sorted(prof["types"]), "first": prof["review_first"]}))
    return rank(found, prof, skip, limit)


def _facts(graph_name: str, uuid: str) -> list[str]:
    q = "MATCH (n:Entity {uuid:$u})-[r:RELATES_TO]-() RETURN r.fact AS f LIMIT 4"
    return [r["f"] for r in rows(graph(graph_name).query(q, {"u": uuid})) if r["f"]]


NEIGHBOURS = 8      # entities offered as «fold into» for one that is not an entity (#467)
CALIBRATION = 20    # suggestions decided one by one before «Apply all visible» is allowed: they measure the decider's confidence (#467)
_NEIGHBOURS = ("MATCH (n:Entity {uuid:$u})-[r:RELATES_TO]-(b:Entity) WHERE b.uuid <> $u AND r.invalid_at IS NULL AND r.expired_at IS NULL "
               "RETURN b.uuid AS uuid, b.name AS name, count(r) AS facts ORDER BY facts DESC, name LIMIT $n")


def neighbours(g, uuid: str) -> list[dict]:
    """The entities it shares current facts with, the most shared first: where a name that is not an entity can be folded."""
    return rows(g.query(_NEIGHBOURS, {"u": uuid, "n": NEIGHBOURS}))


def _one_line(s) -> str:
    """A name as the decider reads it: on one line, so it cannot forge another option or line of the prompt."""
    return " ".join(str(s or "").split())[:120]


def _fold_target(d, key: str, state: str, name: str, near: list[dict]) -> tuple[str, str, float | None]:
    """The neighbour the decider says this name is a detail of (a flag of a tool, a file of a project), or nothing. The name itself is
    in the state (the data block); the question only refers to it."""
    if not near:
        return "", "", None
    r = decider.decide(d.base_url, d.model, key, state,
                       "La entidad descrita no parece una entidad propia. ¿De cuál de estas entidades es un detalle (una opción, un fichero, "
                       "un campo, una versión, una fecha, una parte)?", [_one_line(x["name"]) for x in near] + ["De ninguna de ellas"])
    if r["index"] >= len(near):
        return "", "", None
    return near[r["index"]]["uuid"], near[r["index"]]["name"][:500], r["prob"]


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
        prof = profile(onto)
        question = _entity_question(prof["types"])
        skip = set(db.scalars(select(RetypeSuggestion.entity_uuid).where(RetypeSuggestion.brain_id == brain_id)))
        brain = db.get(Brain, brain_id)
        context = decider.scope(brain.name, brain.description, onto) if brain else ""
        cands = _candidates(graph_name, prof, skip, limit)
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
                facts = _facts(graph_name, c["uuid"])
                state = decider.with_scope(f"Entidad: {c['name']}\nResumen: {c['summary'][:300]}\nHechos:\n" + "\n".join(f"- {f[:160]}" for f in facts), context)
                why = doubtful_reason(c["name"], prof["rules"])
                conf = None
                if not why:
                    ent = decider.decide(d.base_url, d.model, key, state, question, ["Sí", "No"])
                    if ent["letter"] == "B" and ent["prob"] >= 0.7:
                        why, conf = f"el decisor no la ve como una entidad concreta ({ent['prob']})", ent["prob"]
                if why:   # not an entity: where it belongs, if one of its neighbours is the place (#467)
                    try:
                        fu, fn, fc = _fold_target(d, key, state, c["name"], neighbours(graph(graph_name), c["uuid"]))
                    except Exception as e:  # noqa: BLE001  (without a place to fold it, it is still doubtful)
                        log.warning("retype %s: no fold target: %s", c["uuid"], e.__class__.__name__)
                        fu, fn, fc = "", "", None
                    db.add(RetypeSuggestion(brain_id=brain_id, entity_uuid=c["uuid"], name=c["name"][:500], current_type=c["type"], status="doubtful",
                                            reason=why, confidence=conf, fold_uuid=fu, fold_name=fn, fold_confidence=fc))
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
                log.warning("retype %s: %s", c["uuid"], e.__class__.__name__)
                if job:
                    job.note(f"«{c['name'][:60]}»: {str(e)[:150]}")
                db.rollback()
                _PROGRESS[brain_id]["error"] = str(e)[:150]
            _PROGRESS[brain_id]["done"] += 1
        _PROGRESS[brain_id]["running"] = False


@jobs.register("retype.scan", "Corrector de tipos", limit=1)
def _job_scan(ctx, p: dict) -> dict:
    from .usage import scope
    try:
        with scope(ctx.brain_id, "retype"):
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


class TypeIn(BaseModel):
    type: str = Field(min_length=1, max_length=64)


def _ontology_type(ctx: BrainCtx, name: str) -> str:
    """The same closed list the corrector offers: a type of the brain's ontology, never free text."""
    onto = get_ontology(ctx.db, ctx.brain.id) or {"entity_types": []}
    if name not in {t["name"] for t in onto["entity_types"]}:
        raise HTTPException(400, "ese tipo no está en la ontología del brain")
    return name


def _out(s: RetypeSuggestion, rules: frozenset[str]) -> dict:
    st = _eff_status(s, rules)
    return {"id": s.id, "entity_uuid": s.entity_uuid, "name": s.name, "current_type": s.current_type, "suggested_type": s.suggested_type,
            "confidence": s.confidence, "status": st, "previous_type": s.previous_type, "chosen_type": s.chosen_type or None,
            "applied_at": s.applied_at,
            "fold": {"uuid": s.fold_uuid, "name": s.fold_name, "confidence": s.fold_confidence} if s.fold_uuid else None, "op": s.op_id,
            "reason": s.reason or (doubtful_reason(s.name, rules) if s.status == "pending" else ("ninguno de los tipos de la ontología encaja" if st == "none" else ""))}


FOLDING_STUCK = timedelta(minutes=10)   # a fold still «folding» after this was cut short (a restart): the row is doubtful again


def _stuck(s: RetypeSuggestion) -> bool:
    at = s.applied_at
    return s.status == "folding" and (at is None or (at if at.tzinfo else at.replace(tzinfo=timezone.utc)) < datetime.now(timezone.utc) - FOLDING_STUCK)


def _eff_status(s: RetypeSuggestion, rules: frozenset[str]) -> str:
    """Las propuestas antiguas cuyo nombre no es una entidad concreta (según las reglas del brain) pasan a «dudosas» sin volver a analizarlas."""
    if _stuck(s):
        return "doubtful"
    if s.status == "pending" and doubtful_reason(s.name, rules):
        return "doubtful"
    if s.status == "same" and not s.suggested_type:  # el decisor contestó «ninguno de los anteriores»: no es lo mismo que «ya correcto»
        return "none"
    return s.status


def pending_count(db, brain_id: int) -> int:
    """Type corrections waiting for an administrator to apply or discard them."""
    rules = profile(get_ontology(db, brain_id))["rules"]
    return sum(1 for r in db.scalars(select(RetypeSuggestion).where(RetypeSuggestion.brain_id == brain_id, RetypeSuggestion.status == "pending"))
               if _eff_status(r, rules) == "pending")


@router.get("")
def overview(status: str = "pending", min_conf: float = 0.0, limit: int = 300, ctx: BrainCtx = Depends(admin_of_brain)):
    onto = get_ontology(ctx.db, ctx.brain.id)
    rules = profile(onto)["rules"]
    allrows = ctx.db.scalars(select(RetypeSuggestion).where(RetypeSuggestion.brain_id == ctx.brain.id)).all()
    counts: dict[str, int] = {}
    for r in allrows:
        counts[_eff_status(r, rules)] = counts.get(_eff_status(r, rules), 0) + 1
    in_status = sorted((r for r in allrows if _eff_status(r, rules) == status), key=lambda r: -(r.confidence or 0))
    shown = [r for r in in_status if status != "pending" or (r.confidence or 0) >= min_conf]
    return {"ontology": bool(onto), "decider": default_decider(ctx.db) is not None, "counts": counts, "hidden_below_threshold": len(in_status) - len(shown),
            "calibration": calibration(allrows, min_conf),
            "progress": _PROGRESS.get(ctx.brain.id, {"running": False, "done": 0, "total": 0, "error": None}), "items": [_out(r, rules) for r in shown[:min(limit, 1000)]]}


def calibration(allrows, min_conf: float) -> dict:
    """How far the decider's confidence holds in this brain (#467): of the type suggestions a curator decided one by one, how many;
    and of those at or above `min_conf`, the share applied and kept (not rejected, not reverted). Bulk apply waits for CALIBRATION."""
    alone = [r for r in allrows if r.alone and r.suggested_type and r.status in ("applied", "rejected", "reverted")]
    above = [r for r in alone if (r.confidence or 0) >= min_conf]
    kept = sum(1 for r in above if r.status == "applied" and not r.chosen_type)   # applied as another type: the decider missed
    return {"needed": CALIBRATION, "decided": len(alone), "above": len(above), "precision": round(kept / len(above), 3) if above else None}


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


def _pick(ctx: BrainCtx, ids: list[int], status: str, rules: frozenset[str]) -> list[RetypeSuggestion]:
    """Filas con ese estado real; las dudosas por heurística no se pueden aplicar como cambio de tipo."""
    rows_ = ctx.db.scalars(select(RetypeSuggestion).where(RetypeSuggestion.brain_id == ctx.brain.id, RetypeSuggestion.id.in_(ids), RetypeSuggestion.status == status)).all()
    return [r for r in rows_ if status != "pending" or not doubtful_reason(r.name, rules)]


@router.post("/apply")
def apply(body: IdsIn, ctx: BrainCtx = Depends(admin_of_brain)):
    onto = get_ontology(ctx.db, ctx.brain.id) or {"entity_types": []}
    allowed = {t["name"] for t in onto["entity_types"]}
    alone = len(set(body.ids)) == 1
    if not alone:   # in bulk only once the decider's confidence has been measured against the curators' own decisions (#467)
        cal = calibration(ctx.db.scalars(select(RetypeSuggestion).where(RetypeSuggestion.brain_id == ctx.brain.id)).all(), 0.0)
        if cal["decided"] < CALIBRATION:
            raise HTTPException(409, f"antes de aplicar en bloque, decide al menos {CALIBRATION} propuestas una a una (llevas {cal['decided']}): "
                                     "así se mide cuánto acierta el decisor en este brain")
    n = 0
    for s in _pick(ctx, body.ids, "pending", profile(onto)["rules"]):
        if s.suggested_type not in allowed:
            continue
        _set_label(ctx.brain.graph_name, s.entity_uuid, s.current_type, s.suggested_type)
        s.previous_type, s.status, s.applied_at, s.alone = s.current_type, "applied", datetime.now(timezone.utc), alone
        n += 1
    ctx.db.commit()
    audit(ctx.db, ctx.user, "retype.apply", ctx.brain, count=n)
    return {"applied": n}


@router.post("/reject")
def reject(body: IdsIn, ctx: BrainCtx = Depends(admin_of_brain)):
    items = list(ctx.db.scalars(select(RetypeSuggestion).where(RetypeSuggestion.brain_id == ctx.brain.id, RetypeSuggestion.id.in_(body.ids),
                                                              RetypeSuggestion.status.in_(["pending", "doubtful"]))))
    alone = len(set(body.ids)) == 1
    rules = profile(get_ontology(ctx.db, ctx.brain.id))["rules"]
    for s in items:   # a doubtful one was never offered as a type to apply: rejecting it says nothing of the decider's types
        s.status, s.alone = "rejected", alone and _eff_status(s, rules) == "pending"
    ctx.db.commit()
    return {"rejected": len(items)}


@router.post("/{sid}/apply-as")
def apply_as(sid: int, body: TypeIn, ctx: BrainCtx = Depends(admin_of_brain)):
    """Applies a pending suggestion with another type of the ontology than the one the decider proposed; reverted like any other."""
    new = _ontology_type(ctx, body.type)
    s = ctx.db.get(RetypeSuggestion, sid)
    if not s or s.brain_id != ctx.brain.id or s.status != "pending":
        raise HTTPException(404, "no hay una propuesta pendiente con ese id")
    if new == s.current_type:
        raise HTTPException(409, "la entidad ya tiene ese tipo")
    _set_label(ctx.brain.graph_name, s.entity_uuid, s.current_type, new)
    # the type the decider proposed, picked from the list, is still the decider's: only another one is a miss
    s.chosen_type = new if new != s.suggested_type else ""
    s.previous_type, s.status, s.applied_at, s.alone = s.current_type, "applied", datetime.now(timezone.utc), True
    ctx.db.commit()
    audit(ctx.db, ctx.user, "retype.apply", ctx.brain, count=1, id=sid, type=new)
    return {"applied": 1}


@router.post("/{sid}/revert")
def revert(sid: int, ctx: BrainCtx = Depends(admin_of_brain)):
    s = ctx.db.get(RetypeSuggestion, sid)
    if s and s.brain_id == ctx.brain.id and s.status == "folded" and s.op_id:
        from .entity_types import revert_op
        return revert_op(s.op_id, ctx)   # the vocabulary change puts the entity, its facts and this row back
    if not s or s.brain_id != ctx.brain.id or s.status != "applied":
        raise HTTPException(404, "no hay un cambio aplicado con ese id")
    _set_label(ctx.brain.graph_name, s.entity_uuid, s.chosen_type or s.suggested_type, s.previous_type)
    s.status = "reverted"
    ctx.db.commit()
    audit(ctx.db, ctx.user, "retype.revert", ctx.brain, id=sid)
    return {"ok": True}


class FoldIn(BaseModel):
    into: str | None = Field(None, max_length=64)   # one of its neighbours; empty: the one the decider proposed


@router.get("/{sid}/neighbours")
def fold_options(sid: int, ctx: BrainCtx = Depends(admin_of_brain)):
    """Where a doubtful entity can be folded: the entities it shares current facts with."""
    s = ctx.db.get(RetypeSuggestion, sid)
    if not s or s.brain_id != ctx.brain.id:
        raise HTTPException(404, "no hay una propuesta con ese id")
    moves = rows(ctx.graph.query("MATCH (n:Entity {uuid:$u})-[r:RELATES_TO]-() RETURN count(r) AS n", {"u": s.entity_uuid}))
    return {"items": neighbours(ctx.graph, s.entity_uuid), "proposed": s.fold_uuid or None, "moves": moves[0]["n"] if moves else 0}


@router.post("/{sid}/fold")
def fold(sid: int, body: FoldIn, ctx: BrainCtx = Depends(admin_of_brain)):
    """«Not an entity → fold into X» (#467): the doubtful entity's facts move to X and its name becomes an alias of X, as a merge of
    duplicates does; the node is left as a `Merged` tombstone, so no orphan is left. Recorded as a vocabulary change: undone from this
    row or from Recent changes."""
    from sqlalchemy import update
    from .entity_types import _merge_all, _record, done
    s = ctx.db.get(RetypeSuggestion, sid)
    rules = profile(get_ontology(ctx.db, ctx.brain.id))["rules"]
    if not s or s.brain_id != ctx.brain.id or _eff_status(s, rules) != "doubtful":
        raise HTTPException(404, "no hay una propuesta dudosa con ese id")
    into = body.into or s.fold_uuid
    near = {x["uuid"]: x for x in neighbours(ctx.graph, s.entity_uuid)}
    if not into or into not in near:
        raise HTTPException(409, "elige una de las entidades con las que comparte hechos vigentes")
    found = rows(ctx.graph.query("MATCH (n:Entity {uuid:$u}) RETURN n.name AS name", {"u": s.entity_uuid}))
    if not found:
        raise HTTPException(404, "la entidad ya no está en el grafo")
    # one fold of this row at a time: a double click or a second administrator finds it taken
    now = datetime.now(timezone.utc)
    free = RetypeSuggestion.status.in_(("pending", "doubtful")) | ((RetypeSuggestion.status == "folding") & (RetypeSuggestion.applied_at < now - FOLDING_STUCK))
    took = ctx.db.execute(update(RetypeSuggestion).where(RetypeSuggestion.id == sid, free).values(status="folding", applied_at=now)).rowcount
    ctx.db.commit()
    if not took:
        raise HTTPException(409, "esa propuesta ya se está fusionando o ya se fusionó")
    keeper = {"uuid": into, "name": str(near[into]["name"] or into)}
    label = f"«{s.name[:80]}» no es una entidad: fusionada en «{keeper['name'][:80]}»"
    # no copy of the graph: one entity's facts are undone from the merge's own record, and a copy per fold would push out the
    # snapshots of larger merges (they keep the last two)
    snap, entries = None, []
    try:
        _merge_all(ctx.graph, keeper, [{"uuid": s.entity_uuid, "name": found[0]["name"] or s.name}], entries)
        _keep_between(ctx.graph, keeper["uuid"], s.entity_uuid, entries[0])
    except Exception as e:  # what was already moved is recorded, so it can be undone like the rest
        log.warning("retype fold %s: %s", sid, e.__class__.__name__)
        ctx.db.rollback()
        s = ctx.db.get(RetypeSuggestion, sid)
        entries = done(entries)
        if entries:
            op = _record(ctx, "entity.merge", label + " (incompleto)", keeper=keeper, entries=entries, snapshot=snap, onto_before=None, suggestion=sid)
            s.status, s.op_id, s.applied_at, s.alone = "folded", op.id, datetime.now(timezone.utc), True
        else:
            s.status = "doubtful"
        ctx.db.commit()
        if entries:
            raise HTTPException(500, "no se pudo fusionar del todo; lo hecho se puede deshacer en «Fusionadas»") from None
        raise HTTPException(500, "no se pudo fusionar; no se ha cambiado nada") from None
    op = _record(ctx, "entity.merge", label, keeper=keeper, entries=entries, snapshot=snap, onto_before=None, suggestion=sid)
    s = ctx.db.get(RetypeSuggestion, sid)
    s.status, s.op_id, s.applied_at, s.alone = "folded", op.id, datetime.now(timezone.utc), True
    if body.into and body.into != s.fold_uuid:
        s.fold_uuid, s.fold_name, s.fold_confidence = into, keeper["name"][:500], None
    ctx.db.commit()
    audit(ctx.db, ctx.user, "retype.fold", ctx.brain, id=sid)
    return {"folded": 1, "op": op.id}


def _keep_between(g, keeper: str, gone: str, entry: dict) -> None:
    """The facts between the folded name and the entity it joins («tool has a --help flag») would stay on the tombstone, out of
    recall. They become facts of the entity itself, and are recorded in the merge's own lists, so undoing the merge puts them back
    between the two ends."""
    for direction, pat in (("out", "(d)-[r:RELATES_TO]->(k)"), ("in", "(k)-[r:RELATES_TO]->(d)")):
        p = {"d": gone, "k": keeper}
        ids = [x["u"] for x in rows(g.query(f"MATCH (d:Merged {{uuid:$d}}), (k:Entity {{uuid:$k}}), {pat} RETURN r.uuid AS u", p))]
        if ids:
            g.query(f"MATCH (d:Merged {{uuid:$d}}), (k:Entity {{uuid:$k}}), {pat} CREATE (k)-[r2:RELATES_TO]->(k) SET r2 = properties(r) DELETE r", p)
            entry["moved"].setdefault(f"RELATES_TO:{direction}", []).extend(ids)


def unfold(db, brain_id: int, sid: int | None) -> None:
    """The fold of a suggestion was undone (from Recent changes or its row): it is doubtful again."""
    s = db.get(RetypeSuggestion, sid) if sid else None
    if s and s.brain_id == brain_id and s.status == "folded":
        s.status, s.op_id, s.applied_at = "doubtful", None, None


# --- One entity, by hand (#179) ---------------------------------------------------------------------
# A curator picks the type from the entity page. It goes to the vocabulary history (kind `entity.retype`) with the labels it had,
# so «Recent changes» can undo it, and it takes the entity out of the corrector: a pending suggestion is marked superseded and,
# if there was none, a superseded row keeps the next analysis from proposing it again.
SUPERSEDE = ("pending", "doubtful", "applied")  # an applied one could no longer be reverted safely: its label is gone


@entity_router.put("/{uuid}/type")
def set_entity_type(uuid: str, body: TypeIn, ctx: BrainCtx = Depends(curator_of_brain)):
    from .entity_types import _record
    new = _ontology_type(ctx, body.type)
    found = rows(ctx.graph.query("MATCH (n:Entity {uuid:$u}) RETURN n.name AS name, [l IN labels(n) WHERE l <> 'Entity'] AS labels", {"u": uuid}))
    if not found:
        raise HTTPException(404, "entidad no encontrada")
    name, before = found[0]["name"] or "", found[0]["labels"]
    if before == [new]:
        raise HTTPException(409, "la entidad ya tiene ese tipo")
    for old in before:
        if old != new:
            _set_label(ctx.brain.graph_name, uuid, old, "")
    _set_label(ctx.brain.graph_name, uuid, "", new)
    s = ctx.db.scalar(select(RetypeSuggestion).where(RetypeSuggestion.brain_id == ctx.brain.id, RetypeSuggestion.entity_uuid == uuid))
    suggestion = None
    if s is None:
        s = RetypeSuggestion(brain_id=ctx.brain.id, entity_uuid=uuid, name=name[:500], current_type=before[0] if before else "", status="superseded")
        ctx.db.add(s)
        ctx.db.flush()
        suggestion = {"id": s.id, "created": True}
    elif s.status in SUPERSEDE:
        suggestion = {"id": s.id, "status": s.status}
        s.status = "superseded"
    old = ", ".join(before) or "(sin tipo)"
    op = _record(ctx, "entity.retype", f"Cambiado el tipo de «{name[:80]}»: {old} → {new}", uuid=uuid, name=name, before=before, after=new, suggestion=suggestion)
    return {"ok": True, "op": op.id, "summary": op.summary, "labels": [new]}


def undo_entity_type(ctx: BrainCtx, d: dict) -> None:
    """Puts back the labels the entity had and the corrector suggestion as it was."""
    if d["after"] not in d["before"]:
        _set_label(ctx.brain.graph_name, d["uuid"], d["after"], "")
    for old in d["before"]:
        _set_label(ctx.brain.graph_name, d["uuid"], "", old)
    sug = d.get("suggestion") or {}
    s = ctx.db.get(RetypeSuggestion, sug["id"]) if sug else None
    if s and s.brain_id == ctx.brain.id and s.status == "superseded":
        if sug.get("created"):
            ctx.db.delete(s)
        else:
            s.status = sug["status"]
