"""Posibles contradicciones entre hechos vigentes (#113).

Graphiti invalida un hecho cuando la extracción ve que otro lo contradice, pero no siempre: dos episodios redactados de forma distinta
pueden dejar vigentes a la vez «X está en A» y «X está en B». Aquí se buscan, sin LLM, los hechos vigentes con el mismo sujeto y la
misma relación (tras normalizar formato y alias) y destinos distintos, en las relaciones que la ontología marca como **funcionales**
(un solo valor a la vez: «está en», «informa a»). Por defecto ninguna lo es: muchas relaciones parecen de un solo valor y no lo son.

Se propone quedarse con el hecho de fecha más reciente (`valid_at`, o `created_at` si no la tiene) y, al resolver, invalidar los
demás con esa fecha. La resolución la decide un curador y se puede deshacer como cualquier invalidación.

Para medir antes de marcar relaciones como funcionales, el modo «todas las relaciones» cuenta los candidatos de cada relación sin
cambiar nada; también desde la línea de comandos:  python -m mimirsynth.conflicts <grafo> [--brain-id N]
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
from .vocab import alias_map, canon_rel, resolve

router = APIRouter(prefix="/api/brains/{slug}/conflicts")
curator = brain_access("curator")
MAX_FACTS = 50000   # hechos vigentes que se leen por análisis
MAX_GROUPS = 200    # grupos que se devuelven (los recuentos sí son completos)

QUERY = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.invalid_at IS NULL AND r.expired_at IS NULL "
         "RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, r.valid_at AS valid_at, r.created_at AS created_at, "
         "a.uuid AS source_uuid, a.name AS source, b.uuid AS target_uuid, b.name AS target LIMIT $n")


def _norm(s) -> str:
    return " ".join(str(s or "").lower().split())


def _when(f: dict) -> str:
    return str(f.get("valid_at") or f.get("created_at") or "")


def functional_relations(onto: dict | None) -> set[str]:
    """Relaciones marcadas como funcionales en la ontología del brain, normalizadas como las del grafo (HostedOn → HOSTED_ON)."""
    return {canon_rel(t["name"]) for t in (onto or {}).get("edge_types", []) if t.get("functional")}


def find(facts: list[dict], amap: dict | None = None, only: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """Agrupa los hechos vigentes por (sujeto, relación) y devuelve los grupos con dos destinos distintos o más, y el recuento por
    relación. Con `only`, solo esas relaciones. Dos destinos con el mismo nombre salvo mayúsculas y espacios son el mismo destino
    (dos nodos de la misma cosa no son una contradicción, son un duplicado del vocabulario)."""
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    sources: dict[str, set] = defaultdict(set)
    for f in facts:
        rel = resolve(f.get("name"), amap)
        if only is not None and rel not in only:
            continue
        by_key[(f["source_uuid"], rel)].append(f)
        sources[rel].add(f["source_uuid"])
    groups, per_rel = [], defaultdict(int)
    for (src, rel), fs in by_key.items():
        if len({_norm(f["target"]) for f in fs}) < 2:
            continue
        fs = sorted(fs, key=_when, reverse=True)
        keep = fs[0]
        losers = [f for f in fs if _norm(f["target"]) != _norm(keep["target"])]
        per_rel[rel] += 1
        groups.append({"source": keep["source"], "source_uuid": src, "relation": rel,
                       "facts": [{k: f.get(k) for k in ("uuid", "fact", "target", "target_uuid", "valid_at", "created_at")} for f in fs],
                       "suggestion": {"keep": keep["uuid"], "invalidate": [f["uuid"] for f in losers],
                                      "clear": all(_when(keep) > _when(f) for f in losers)}})   # «clear»: el ganador es estrictamente más reciente
    groups.sort(key=lambda g: (-len(g["facts"]), g["relation"], _norm(g["source"])))
    stats = sorted(({"relation": r, "sources": len(s), "groups": per_rel.get(r, 0),
                     "ratio": round(per_rel.get(r, 0) / len(s), 3) if s else 0} for r, s in sources.items()),
                   key=lambda x: (-x["groups"], x["relation"]))
    return groups, stats


def scan(graph, amap: dict | None, functional: set[str], all_relations: bool = False) -> dict:
    facts = rows(graph.query(QUERY, {"n": MAX_FACTS}))
    groups, stats = find(facts, amap, None if all_relations else functional)
    for s in stats:
        s["functional"] = s["relation"] in functional
    return {"scanned": len(facts), "truncated": len(facts) >= MAX_FACTS, "functional": sorted(functional), "total": len(groups),
            "groups": groups[:MAX_GROUPS], **({"by_relation": stats} if all_relations else {})}


def _brain_functional(db, brain_id: int) -> set[str]:
    from .ontology import get_ontology
    return functional_relations(get_ontology(db, brain_id))


@router.get("")
def list_conflicts(all: bool = False, ctx: BrainCtx = Depends(curator)):
    """Posibles contradicciones en las relaciones funcionales del brain. Con `all`, en todas las relaciones y con el recuento por
    relación: sirve para medir antes de marcar una relación como funcional. Solo lee."""
    return scan(ctx.graph, alias_map(ctx.db, ctx.brain.id), _brain_functional(ctx.db, ctx.brain.id), all)


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
         "r.created_at AS created_at, r.invalid_at AS invalid_at, r.expired_at AS expired_at, a.uuid AS source_uuid, b.name AS target")
    amap = alias_map(ctx.db, ctx.brain.id)
    got = {}
    for u in [body.keep, *body.invalidate]:
        r = rows(ctx.graph.query(q, {"u": u}))
        if not r:
            raise HTTPException(404, "hecho no encontrado")
        got[u] = r[0]
    keep = got[body.keep]
    for u in body.invalidate:
        f = got[u]
        if f["invalid_at"] or f["expired_at"]:
            raise HTTPException(409, "uno de los hechos ya está invalidado")
        if f["source_uuid"] != keep["source_uuid"] or resolve(f["name"], amap) != resolve(keep["name"], amap):
            raise HTTPException(400, "los hechos no tienen el mismo sujeto y la misma relación")
    now = datetime.now(timezone.utc).isoformat()
    ops = []
    for u in body.invalidate:
        f = got[u]
        at = _when(keep) if _when(keep) > _when(f) else now
        ctx.graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() SET r.invalid_at = $at, r.expired_at = $n", {"u": u, "at": at, "n": now})
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
    if not functional:
        return {"total": 0, "functional": []}
    ctx.progress(0, 0, "leyendo los hechos vigentes")
    out = scan(graph(gname), amap, functional)
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
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
