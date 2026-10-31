"""Entity page (#127): everything known about one entity and how it changed, in a single call.

Facts are grouped by direction and canonical relation, oldest first, so each group reads as the evolution of one piece of data
(«runs on: A → B → C»). `as_of` says which facts were current on a given day (validity time, as in the graph view); each fact also
keeps its learning date (`created_at`), because the two are different axes. A functional relation (#113) with more than one current
value is flagged instead of hidden. A lent entity (federation) is read with `origin` and is read-only. Generic relations
(`RELATES_TO` and the like) are marked `generic` and go last: their «evolution» says little, so the page shows them apart."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from .conflicts import functional_relations, generic
from .db import fact_status, graph, parse_ts, rows
from .deps import BrainCtx, reader
from .graphapi import FACT_RETURN
from .ontology import get_ontology
from .vocab import alias_map, resolve

router = APIRouter(prefix="/api/brains/{slug}/entities")
MAX_FACTS = 2000      # facts read per entity; beyond that the page says it is truncated
MAX_EPISODES = 20


def _norm(s) -> str:
    return " ".join(str(s or "").split()).lower()


def _source(ctx: BrainCtx, origin: str):
    """The graph, alias map and functional relations to read from: this brain's, or those of a brain that lends its graph to it."""
    if not origin or origin == ctx.brain.slug:
        return ctx.graph, alias_map(ctx.db, ctx.brain.id), functional_relations(get_ontology(ctx.db, ctx.brain.id)), ""
    from .federation import sources_for
    src = next((s for s in sources_for(ctx.db, ctx.brain) if s.slug == origin and s.scope in ("graph", "both")), None)
    if not src:
        raise HTTPException(404, "ese brain no presta su grafo a este")
    return graph(src.graph_name), alias_map(ctx.db, src.brain_id), functional_relations(get_ontology(ctx.db, src.brain_id)), src.slug


@router.get("/{uuid}")
def entity_page(uuid: str, as_of: str = Query("", max_length=40), origin: str = Query("", max_length=64), ctx: BrainCtx = Depends(reader)):
    G, amap, functional, lent = _source(ctx, origin)
    at = parse_ts(as_of) if as_of else None
    if as_of and not at:
        raise HTTPException(400, "fecha no válida")
    found = rows(G.query("MATCH (n:Entity {uuid:$u}) RETURN n.uuid AS uuid, n.name AS name, [l IN labels(n) WHERE l <> 'Entity'] AS labels, "
                         "n.summary AS summary, n.aliases AS aliases, n.created_at AS created_at", {"u": uuid}))
    if not found:
        raise HTTPException(404, "entidad no encontrada")
    ent = found[0]
    ent["aliases"] = [a for a in (ent["aliases"] or []) if isinstance(a, str)]
    total = G.query("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE a.uuid = $u OR b.uuid = $u RETURN count(r)", {"u": uuid}).result_set[0][0]
    facts = rows(G.query(f"MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE a.uuid = $u OR b.uuid = $u RETURN {FACT_RETURN}, "
                         "[l IN labels(a) WHERE l <> 'Entity'] AS source_labels, [l IN labels(b) WHERE l <> 'Entity'] AS target_labels "
                         "ORDER BY coalesce(r.valid_at, r.created_at) DESC, r.uuid LIMIT $n", {"u": uuid, "n": MAX_FACTS}))
    groups: dict[tuple[str, str], dict] = {}
    neighbors: dict[str, dict] = {}
    hidden = 0
    for f in facts:
        status = fact_status(f["valid_at"], f["invalid_at"], f["expired_at"], at)
        if status == "future":  # not yet true on that day
            hidden += 1
            continue
        out = f["source_uuid"] == uuid
        other = {"uuid": f["target_uuid"] if out else f["source_uuid"], "name": f["target"] if out else f["source"],
                 "labels": f["target_labels"] if out else f["source_labels"]}
        relation = resolve(f["name"], amap)
        item = {"uuid": f["uuid"], "fact": f["fact"], "status": status, "valid_at": f["valid_at"], "invalid_at": f["invalid_at"],
                "created_at": f["created_at"], "other": other, "episodes": len(f["episodes"] or [])}
        g = groups.setdefault((("out" if out else "in"), relation), {"relation": relation, "direction": "out" if out else "in",
                                                                    "functional": relation in functional, "generic": generic(relation),
                                                                    "current": [], "previous": []})
        g["current" if status != "invalidated" else "previous"].append(item)
        nb = neighbors.setdefault(other["uuid"], {**other, "facts": 0, "current": 0})
        nb["facts"] += 1
        nb["current"] += status != "invalidated"
    when = lambda x: parse_ts(x["valid_at"] or x["created_at"]) or datetime.min.replace(tzinfo=timezone.utc)  # noqa: E731
    out_groups = []
    for g in groups.values():
        g["current"].sort(key=when)
        g["previous"].sort(key=when)
        # a single-valued relation with two different current values: possible contradiction (#113), shown rather than hidden
        g["conflict"] = g["functional"] and g["direction"] == "out" and len({_norm(x["other"]["name"]) for x in g["current"]}) > 1
        out_groups.append(g)
    out_groups.sort(key=lambda g: (g["generic"], not g["conflict"], -len(g["current"]), -len(g["previous"]), g["direction"] != "out", g["relation"]))
    episodes = rows(G.query("MATCH (e:Episodic)-[:MENTIONS]->(n:Entity {uuid:$u}) RETURN e.uuid AS uuid, e.name AS name, e.valid_at AS valid_at, "
                            "e.created_at AS created_at, e.source_description AS source ORDER BY coalesce(e.valid_at, e.created_at) DESC LIMIT $n",
                            {"u": uuid, "n": MAX_EPISODES}))
    n_episodes = G.query("MATCH (e:Episodic)-[:MENTIONS]->(n:Entity {uuid:$u}) RETURN count(e)", {"u": uuid}).result_set[0][0]
    return {
        "entity": {**ent, "origin": lent}, "read_only": bool(lent), "as_of": at.isoformat() if at else None,
        "facts": {"total": total, "shown": len(facts) - hidden, "not_yet": hidden, "truncated": total > len(facts)},
        "groups": out_groups,
        "neighbors": sorted(neighbors.values(), key=lambda n: (-n["current"], -n["facts"], n["name"] or "")),
        "episodes": {"total": n_episodes, "items": episodes},
    }


@router.get("")
def find_entities(q: str = Query(min_length=1, max_length=200), limit: int = Query(10, ge=1, le=50), ctx: BrainCtx = Depends(reader)):
    """Entities whose name or merged names contain `q`, exact matches first: to jump to an entity page by name."""
    key = _norm(q)
    res = rows(ctx.graph.query(
        "MATCH (n:Entity) WHERE toLower(n.name) CONTAINS $k OR any(a IN coalesce(n.aliases, []) WHERE toLower(a) CONTAINS $k) "
        "OPTIONAL MATCH (n)-[r:RELATES_TO]-(:Entity) RETURN n.uuid AS uuid, n.name AS name, [l IN labels(n) WHERE l <> 'Entity'] AS labels, "
        "count(r) AS facts ORDER BY facts DESC LIMIT $n", {"k": key, "n": limit * 3}))
    res.sort(key=lambda e: (_norm(e["name"]) != key, not _norm(e["name"]).startswith(key), -e["facts"]))
    return res[:limit]

