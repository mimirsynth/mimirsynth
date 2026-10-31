"""Posibles contradicciones entre hechos vigentes (#113).

Graphiti invalida un hecho cuando la extracción ve que otro lo contradice, pero no siempre: dos episodios redactados de forma distinta
pueden dejar vigentes a la vez «X está en A» y «X está en B». Aquí se buscan, sin LLM, los hechos vigentes con el mismo sujeto y la
misma relación (tras normalizar formato y alias) y destinos **distintos del mismo tipo de entidad**, en las relaciones que la
ontología marca como **funcionales** (un solo valor a la vez). Por defecto ninguna lo es, tampoco en los paquetes: medido en un grafo
real, «ubicado en» mezclaba hosts, URLs, VLANs y servicios, y una marca puesta de antemano daba sobre todo falsos positivos.

Se propone quedarse con el hecho de fecha de validez (`valid_at`) más reciente. Si alguna fecha es solo la de aprendizaje
(`created_at`: cuándo se supo, no cuándo fue cierto), la propuesta no se da por clara y decide el curador. Al resolver se invalidan
los demás con esa fecha; se puede deshacer como cualquier invalidación.

Para medir antes de marcar relaciones como funcionales, el modo «todas las relaciones» cuenta los candidatos de cada relación sin
cambiar nada; también desde la línea de comandos:  python -m mimirsynth.conflicts <grafo> [--brain-id N]

Generic relations (`RELATES_TO` and the like, what the extractor writes when no type fits) are never compared: they hold every kind of
link, so a single-value mark on them only produces noise. A group a curator marks as «not a contradiction» stays hidden while its facts
are the same ones (rc.1 feedback on #141).
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import jobs, notify
from .db import rows
from .deps import BrainCtx, audit, brain_access
from .models import ConflictDismissal
from .vocab import alias_map, canon_rel, resolve

router = APIRouter(prefix="/api/brains/{slug}/conflicts")
curator = brain_access("curator")
MAX_FACTS = 50000   # hechos vigentes que se leen por análisis
MAX_GROUPS = 200    # grupos que se devuelven (los recuentos sí son completos)
GENERIC = {"RELATES_TO", "RELATED_TO", "IS_RELATED_TO", "ASSOCIATED_WITH", "CONNECTED_TO", "LINKED_TO", "MENTIONS"}


def generic(relation: str | None) -> bool:
    """A relation name that says nothing about what links two entities, so it can never be single-valued."""
    return canon_rel(relation) in GENERIC

QUERY = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.invalid_at IS NULL AND r.expired_at IS NULL "
         "RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, r.valid_at AS valid_at, r.created_at AS created_at, "
         "a.uuid AS source_uuid, a.name AS source, b.uuid AS target_uuid, b.name AS target, labels(b) AS target_labels "
         "ORDER BY coalesce(r.valid_at, r.created_at) DESC, r.uuid LIMIT $n")   # si se trunca, siempre los mismos: los más recientes


def _norm(s) -> str:
    return " ".join(str(s or "").lower().split())


def _when(f: dict) -> str:
    return str(f.get("valid_at") or f.get("created_at") or "")


def _type(f: dict) -> str:
    """Tipo de entidad del destino (la etiqueta que no es `Entity`); sin tipo, cuenta como su propio grupo."""
    return ",".join(sorted(x for x in f.get("target_labels") or [] if x != "Entity")) or "Entity"


def functional_relations(onto: dict | None) -> set[str]:
    """Relaciones marcadas como funcionales en la ontología del brain, normalizadas como las del grafo (HostedOn → HOSTED_ON)."""
    return {canon_rel(t["name"]) for t in (onto or {}).get("edge_types", []) if t.get("functional") and not generic(t["name"])}


def find(facts: list[dict], amap: dict | None = None, only: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """Agrupa los hechos vigentes por (sujeto, relación, tipo del destino) y devuelve los grupos con dos destinos distintos o más, y
    el recuento por relación. Con `only`, solo esas relaciones.
    - Solo se comparan destinos del mismo tipo de entidad: «X ubicado en Host A» y «X ubicado en VLAN B» no se contradicen.
    - Dos destinos con el mismo nombre salvo mayúsculas y espacios son el mismo destino (eso es un duplicado del vocabulario).
    - La propuesta solo es clara si el ganador es estrictamente más reciente y todas las fechas son de validez (`valid_at`)."""
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    sources: dict[str, set] = defaultdict(set)
    for f in facts:
        rel = resolve(f.get("name"), amap)
        if rel in GENERIC or (only is not None and rel not in only):
            continue
        by_key[(f["source_uuid"], rel, _type(f))].append(f)
        sources[rel].add(f["source_uuid"])
    groups, hit = [], defaultdict(set)
    for (src, rel, ttype), fs in by_key.items():
        if len({_norm(f["target"]) for f in fs}) < 2:
            continue
        fs = sorted(fs, key=_when, reverse=True)
        keep = fs[0]
        losers = [f for f in fs if _norm(f["target"]) != _norm(keep["target"])]
        dated = all(f.get("valid_at") for f in [keep, *losers])
        hit[rel].add(src)
        groups.append({"source": keep["source"], "source_uuid": src, "relation": rel, "target_type": ttype,
                       "facts": [{k: f.get(k) for k in ("uuid", "fact", "target", "target_uuid", "valid_at", "created_at")} for f in fs],
                       "suggestion": {"keep": keep["uuid"], "invalidate": [f["uuid"] for f in losers], "dated_by": "valid_at" if dated else "created_at",
                                      "clear": dated and all(_when(keep) > _when(f) for f in losers)}})
    groups.sort(key=lambda g: (-len(g["facts"]), g["relation"], _norm(g["source"])))
    # De menor a mayor proporción: las relaciones de un solo valor de verdad son las de pocos casos, no las de muchos.
    stats = sorted(({"relation": r, "sources": len(s), "groups": len(hit.get(r, ())),
                     "ratio": round(len(hit.get(r, ())) / len(s), 3) if s else 0} for r, s in sources.items()),
                   key=lambda x: (x["groups"] == 0, x["ratio"], x["relation"]))
    return groups, stats


def _hidden(g: dict, dismissed: list[dict]) -> dict | None:
    """The dismissal that covers a group: same subject, relation and target type, and no fact the curator did not see."""
    uuids = {f["uuid"] for f in g["facts"]}
    return next((d for d in dismissed if (d["source_uuid"], d["relation"], d["target_type"]) == (g["source_uuid"], g["relation"], g["target_type"])
                 and uuids <= set(d["facts"])), None)


def scan(graph, amap: dict | None, functional: set[str], all_relations: bool = False, dismissed: list[dict] | None = None) -> dict:
    facts = rows(graph.query(QUERY, {"n": MAX_FACTS}))
    groups, stats = find(facts, amap, None if all_relations else functional)
    for s in stats:
        s["functional"] = s["relation"] in functional
    shown, seen = [], set()
    for g in groups:
        d = _hidden(g, dismissed or [])
        if d:
            seen.add(d["id"])
        else:
            shown.append(g)
    return {"scanned": len(facts), "truncated": len(facts) >= MAX_FACTS, "functional": sorted(functional), "total": len(shown),
            "groups": shown[:MAX_GROUPS], "generic_facts": sum(1 for f in facts if resolve(f.get("name"), amap) in GENERIC),
            "dismissed": [{k: d[k] for k in ("id", "source", "relation", "target_type", "created_at")} | {"facts": len(d["facts"])}
                          for d in dismissed or [] if d["id"] in seen],
            **({"by_relation": stats} if all_relations else {})}


def _dismissals(db, brain_id: int) -> list[dict]:
    return [{"id": d.id, "source_uuid": d.source_uuid, "source": d.source, "relation": d.relation, "target_type": d.target_type,
             "facts": d.facts or [], "created_at": d.created_at}
            for d in db.scalars(select(ConflictDismissal).where(ConflictDismissal.brain_id == brain_id).order_by(ConflictDismissal.id.desc()))]


def _brain_functional(db, brain_id: int) -> set[str]:
    from .ontology import get_ontology
    return functional_relations(get_ontology(db, brain_id))


@router.get("")
def list_conflicts(all: bool = False, ctx: BrainCtx = Depends(curator)):
    """Posibles contradicciones en las relaciones funcionales del brain. Con `all`, en todas las relaciones y con el recuento por
    relación: sirve para medir antes de marcar una relación como funcional. Solo lee."""
    return scan(ctx.graph, alias_map(ctx.db, ctx.brain.id), _brain_functional(ctx.db, ctx.brain.id), all, _dismissals(ctx.db, ctx.brain.id))


class DismissIn(BaseModel):
    source_uuid: str = Field(min_length=1, max_length=64)
    source: str = Field("", max_length=255)
    relation: str = Field(min_length=1, max_length=128)
    target_type: str = Field("Entity", max_length=255)
    facts: list[str] = Field(min_length=2, max_length=500)


@router.post("/dismiss", status_code=201)
def dismiss(body: DismissIn, ctx: BrainCtx = Depends(curator)):
    """«Not a contradiction»: the group stops showing until a fact the curator did not see joins it. Undone with DELETE."""
    d = ConflictDismissal(brain_id=ctx.brain.id, source_uuid=body.source_uuid, source=body.source, relation=canon_rel(body.relation),
                          target_type=body.target_type, facts=sorted(set(body.facts)), user_id=ctx.user.id)
    ctx.db.add(d)
    ctx.db.commit()
    audit(ctx.db, ctx.user, "conflict.dismiss", ctx.brain, id=d.id, source=body.source, relation=d.relation, facts=len(d.facts))
    return {"id": d.id}


@router.delete("/dismiss/{did}")
def undismiss(did: int, ctx: BrainCtx = Depends(curator)):
    """Shows a dismissed group again."""
    d = ctx.db.get(ConflictDismissal, did)
    if not d or d.brain_id != ctx.brain.id:
        raise HTTPException(404, "no encontrado")
    source, relation = d.source, d.relation
    ctx.db.delete(d)
    ctx.db.commit()
    audit(ctx.db, ctx.user, "conflict.undismiss", ctx.brain, id=did, source=source, relation=relation)
    return {"ok": True}


class ResolveIn(BaseModel):
    keep: str = Field(min_length=1, max_length=64)
    invalidate: list[str] = Field(min_length=1, max_length=50)


@router.post("/resolve")
def resolve_conflict(body: ResolveIn, ctx: BrainCtx = Depends(curator)):
    """Deja vigente `keep` e invalida los demás, con la fecha de `keep` si es posterior (así la línea temporal dice cuándo cambió) o
    con la de ahora si no. Cada invalidación queda en el historial del vocabulario y se puede deshacer."""
    from .entity_types import _record
    if body.keep in body.invalidate:
        raise HTTPException(400, "el hecho que se conserva no puede invalidarse a la vez")
    q = ("MATCH (a:Entity)-[r:RELATES_TO {uuid:$u}]->(b:Entity) RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, r.valid_at AS valid_at, "
         "r.created_at AS created_at, r.invalid_at AS invalid_at, r.expired_at AS expired_at, a.uuid AS source_uuid, b.name AS target, "
         "labels(b) AS target_labels")
    amap = alias_map(ctx.db, ctx.brain.id)
    got = {}
    for u in [body.keep, *body.invalidate]:
        r = rows(ctx.graph.query(q, {"u": u}))
        if not r:
            raise HTTPException(404, "hecho no encontrado")
        got[u] = r[0]
    keep = got[body.keep]
    if keep["invalid_at"] or keep["expired_at"]:
        raise HTTPException(409, "el hecho que se conserva ya no está vigente")   # si no, no quedaría ninguno vigente
    for u in body.invalidate:
        f = got[u]
        if f["invalid_at"] or f["expired_at"]:
            raise HTTPException(409, "uno de los hechos ya está invalidado")
        if f["source_uuid"] != keep["source_uuid"] or resolve(f["name"], amap) != resolve(keep["name"], amap) or _type(f) != _type(keep):
            raise HTTPException(400, "los hechos no tienen el mismo sujeto, la misma relación y el mismo tipo de destino")
    now = datetime.now(timezone.utc).isoformat()
    items = [{"u": u, "at": _when(keep) if keep.get("valid_at") and _when(keep) > _when(got[u]) else now} for u in body.invalidate]
    ctx.graph.query("UNWIND $items AS it MATCH ()-[r:RELATES_TO {uuid: it.u}]->() SET r.invalid_at = it.at, r.expired_at = $n",
                    {"items": items, "n": now})   # todas en una consulta: no queda una resolución a medias
    ops = []
    for u in body.invalidate:
        f = got[u]
        op = _record(ctx, "fact.invalidate", f"Invalidado por contradicción con «{(keep['fact'] or '')[:60]}»: «{(f['fact'] or '')[:60]}»",
                     uuid=u, before={"invalid_at": f["invalid_at"], "expired_at": f["expired_at"]})
        ops.append(op.id)
    audit(ctx.db, ctx.user, "conflict.resolve", ctx.brain, keep=body.keep, invalidated=body.invalidate)
    return {"ok": True, "ops": ops}


# --- aviso periódico --------------------------------------------------------------------------

@jobs.register("conflicts.scan", "Buscar contradicciones entre hechos", limit=1)
def _job_scan(ctx: "jobs.JobCtx", p: dict) -> dict:
    from .db import graph
    from .models import Brain
    from .store import _factory
    with _factory()() as db:
        b = db.get(Brain, ctx.brain_id)
        if not b:
            return {}
        functional, amap, name, slug, gname = _brain_functional(db, b.id), alias_map(db, b.id), b.name, b.slug, b.graph_name
        dismissed = _dismissals(db, b.id)
    if not functional:
        return {"total": 0, "functional": []}
    ctx.progress(0, 0, "leyendo los hechos vigentes")
    out = scan(graph(gname), amap, functional, dismissed=dismissed)
    key = f"conflicts:{slug}"
    if out["total"]:
        notify.emit("conflicts.found", f"«{name}» tiene {out['total']} posibles contradicciones entre hechos",
                    f"Hechos vigentes con el mismo sujeto y la misma relación funcional ({', '.join(out['functional'])}) y destinos distintos. "
                    "Revísalos en Vocabulario → Contradicciones.", severity="info", brain_id=ctx.brain_id, key=key)
    else:
        notify.resolve("conflicts.found", key, "Ya no hay contradicciones pendientes.")
    return {"total": out["total"], "scanned": out["scanned"]}


def check_all() -> list[int]:
    """Lanza la búsqueda en cada brain que tenga alguna relación funcional (lo llama el ciclo de avisos, una vez al día)."""
    from .models import Brain, BrainOntology
    from .store import _factory
    with _factory()() as db:
        ids = [o.brain_id for o in db.scalars(select(BrainOntology)) if functional_relations(o.data)]
        brains = [b.id for b in db.scalars(select(Brain).where(Brain.id.in_(ids)))] if ids else []
    return [jobs.submit("conflicts.scan", b, {}, "Buscar contradicciones entre hechos", dedupe_key=f"conflicts.scan:{b}") for b in brains]


def main(argv: list[str]) -> int:
    """Medición en solo lectura sobre un grafo: recuento de candidatos por relación y los grupos más grandes."""
    if not argv or argv[0].startswith("-"):
        print("uso: python -m mimirsynth.conflicts <grafo> [--brain-id N] [--top N]", file=sys.stderr)
        return 2
    from .db import graph
    gname, amap, functional, top = argv[0], None, set(), 20
    if "--brain-id" in argv:
        from .store import _factory
        bid = int(argv[argv.index("--brain-id") + 1])
        with _factory()() as db:
            amap, functional = alias_map(db, bid), _brain_functional(db, bid)
    if "--top" in argv:
        top = int(argv[argv.index("--top") + 1])
    out = scan(graph(gname), amap, functional, all_relations=True)
    out["groups"] = out["groups"][:top]
    out.pop("dismissed")
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
