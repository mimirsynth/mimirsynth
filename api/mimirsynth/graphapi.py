"""Rutas de lectura del grafo de un brain: /api/brains/{slug}/... (requieren rol de lector o superior)."""
from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .db import fact_status, parse_ts, rows
from sqlalchemy import select

from .deps import BrainCtx, reader
from .i18n import language, tr
from .models import VocabAlias
from .reembed import is_shadow
from .vocab import alias_map, canon_rel, resolve  # noqa: F401  (canon_rel se reexporta)

router = APIRouter(prefix="/api/brains/{slug}")

FACT_RETURN = (
    "r.uuid AS uuid, r.name AS name, r.fact AS fact, r.valid_at AS valid_at, r.invalid_at AS invalid_at, "
    "r.expired_at AS expired_at, r.created_at AS created_at, r.reference_time AS reference_time, "
    "r.episodes AS episodes, a.name AS source, a.uuid AS source_uuid, b.name AS target, b.uuid AS target_uuid"
)


def _fact(row: dict, at: datetime | None = None, amap: dict | None = None) -> dict:
    row["name_raw"] = row.get("name")
    row["name"] = resolve(row.get("name"), amap)
    row["status"] = fact_status(row.get("valid_at"), row.get("invalid_at"), row.get("expired_at"), at)
    row["episodes"] = row.get("episodes") or []
    return row


@router.get("/overview")
def overview(ctx: BrainCtx = Depends(reader)):
    G = ctx.graph
    one = lambda q: G.query(q).result_set[0][0]  # noqa: E731
    by_label = G.query(
        "MATCH (n:Entity) WITH [l IN labels(n) WHERE l <> 'Entity'] AS ls "
        "UNWIND (CASE WHEN size(ls)=0 THEN ['(sin tipo)'] ELSE ls END) AS l RETURN l AS label, count(*) AS count "
        "ORDER BY count DESC"
    )
    last = G.query("MATCH (e:Episodic) RETURN e.name AS name, e.created_at AS created_at ORDER BY e.created_at DESC LIMIT 1")
    return {
        "entities": one("MATCH (n:Entity) RETURN count(n)"),
        "episodes": one("MATCH (e:Episodic) RETURN count(e)"),
        "facts_total": one("MATCH ()-[r:RELATES_TO]->() RETURN count(r)"),
        "facts_invalidated": one("MATCH ()-[r:RELATES_TO]->() WHERE r.invalid_at IS NOT NULL RETURN count(r)"),
        "communities": one("MATCH (c:Community) RETURN count(c)"),
        "by_label": rows(by_label),
        "last_episode": rows(last)[0] if last.result_set else None,
        "first_episode_at": one("MATCH (e:Episodic) RETURN min(e.valid_at)"),
    }


@router.get("/overview/activity")
def activity(weeks: int = Query(26, ge=4, le=104), ctx: BrainCtx = Depends(reader)):
    """Datos para las gráficas del resumen: actividad semanal, estado de los hechos, relaciones y entidades principales, documentos."""
    from collections import Counter
    from datetime import timedelta

    from sqlalchemy import func, select

    from .models import Document
    G = ctx.graph
    am = alias_map(ctx.db, ctx.brain.id)
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    starts = [monday - timedelta(weeks=weeks - 1 - i) for i in range(weeks)]

    def bucket(ts) -> int | None:
        d = parse_ts(ts)
        if not d:
            return None
        i = (d - starts[0]).days // 7
        return i if 0 <= i < weeks else None

    eps, learned, invalidated = [0] * weeks, [0] * weeks, [0] * weeks
    for r in rows(G.query("MATCH (e:Episodic) RETURN e.created_at AS t")):
        i = bucket(r["t"])
        if i is not None:
            eps[i] += 1
    status, rels = Counter(), Counter()
    for r in rows(G.query("MATCH ()-[r:RELATES_TO]->() RETURN r.name AS name, r.valid_at AS v, r.invalid_at AS i, r.expired_at AS x, r.created_at AS c")):
        status[fact_status(r["v"], r["i"], r["x"], now)] += 1
        rels[resolve(r["name"], am)] += 1
        i = bucket(r["c"])
        if i is not None:
            learned[i] += 1
        j = bucket(r["i"])
        if j is not None:
            invalidated[j] += 1
    top_entities = rows(G.query("MATCH (n:Entity)-[r:RELATES_TO]-() WITH n, count(r) AS degree ORDER BY degree DESC LIMIT 8 "
                                "RETURN n.name AS name, degree, [l IN labels(n) WHERE l <> 'Entity'] AS labels"))
    docs = dict(ctx.db.execute(select(Document.status, func.count()).where(Document.brain_id == ctx.brain.id).group_by(Document.status)).all())
    chunks = ctx.db.scalar(select(func.coalesce(func.sum(Document.chunks), 0)).where(Document.brain_id == ctx.brain.id, Document.status == "active")) or 0
    return {
        "weeks": [d.date().isoformat() for d in starts],
        "episodes": eps, "facts_learned": learned, "facts_invalidated": invalidated,
        "fact_status": {"current": status["current"], "invalidated": status["invalidated"], "future": status["future"]},
        "top_relations": [{"name": k, "count": v} for k, v in rels.most_common(8)],
        "top_entities": top_entities,
        "documents": {"by_status": docs, "total": sum(docs.values()), "chunks": int(chunks)},
    }


def _until(d: str) -> str:
    """Fecha de fin inclusiva: «2026-10-23» cubre todo ese día (las marcas de tiempo son ISO, así que se comparan como texto)."""
    return d if "T" in d else d + "T99"


@router.get("/episodes/sources")
def episode_sources(ctx: BrainCtx = Depends(reader)):
    return rows(ctx.graph.query("MATCH (e:Episodic) RETURN e.source AS source, count(e) AS count ORDER BY count DESC"))


@router.get("/episodes")
def episodes(
    ctx: BrainCtx = Depends(reader),
    q: str = Query("", max_length=200),
    source: str = "",
    since: str = Query("", pattern=r"^(\d{4}-\d{2}-\d{2})?$"),
    until: str = Query("", pattern=r"^(\d{4}-\d{2}-\d{2})?$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Episodios (lo que se le contó al brain, tal cual), paginados y filtrables por texto, tipo de fuente y fechas de creación."""
    conds, par = [], {"skip": offset, "limit": limit}
    if q:
        conds.append("(toLower(e.name) CONTAINS toLower($q) OR toLower(e.content) CONTAINS toLower($q))")
        par["q"] = q
    if source:
        conds.append("e.source = $src")
        par["src"] = source
    if since:
        conds.append("e.created_at >= $since")
        par["since"] = since
    if until:
        conds.append("e.created_at <= $until")
        par["until"] = _until(until)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    total = rows(ctx.graph.query(f"MATCH (e:Episodic) {where} RETURN count(e) AS n", par))[0]["n"]
    res = ctx.graph.query(
        f"MATCH (e:Episodic) {where} RETURN e.uuid AS uuid, e.name AS name, e.source AS source, "
        "e.source_description AS description, e.created_at AS created_at, e.valid_at AS valid_at, "
        f"substring(e.content, 0, 400) AS snippet, size(e.entity_edges) AS facts ORDER BY e.created_at {order.upper()} SKIP $skip LIMIT $limit",
        par,
    )
    return {"total": total, "limit": limit, "offset": offset, "items": rows(res)}


@router.get("/episodes/{uuid}")
def episode(uuid: str, ctx: BrainCtx = Depends(reader)):
    G = ctx.graph
    ep = rows(G.query(
        "MATCH (e:Episodic {uuid:$u}) RETURN e.uuid AS uuid, e.name AS name, e.content AS content, "
        "e.source AS source, e.source_description AS description, e.created_at AS created_at, e.valid_at AS valid_at",
        {"u": uuid},
    ))
    if not ep:
        raise HTTPException(404, "episodio no encontrado")
    facts = rows(G.query(
        f"MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE $u IN r.episodes RETURN {FACT_RETURN} ORDER BY r.created_at",
        {"u": uuid},
    ))
    return {**ep[0], "facts": [_fact(f, amap=alias_map(ctx.db, ctx.brain.id)) for f in facts]}


def _fact_conds(q: str, since: str, until: str, raw_rel: list[str] | None) -> tuple[list[str], dict]:
    conds, par = [], {}
    if q:
        conds.append("(toLower(r.fact) CONTAINS toLower($q) OR toLower(a.name) CONTAINS toLower($q) OR toLower(b.name) CONTAINS toLower($q))")
        par["q"] = q
    if since:
        conds.append("coalesce(r.valid_at, r.created_at) >= $since")
        par["since"] = since
    if until:
        conds.append("coalesce(r.valid_at, r.created_at) <= $until")
        par["until"] = _until(until)
    if raw_rel is not None:
        conds.append("r.name IN $rels")
        par["rels"] = raw_rel
    return conds, par


def _raw_names(ctx: BrainCtx, rel: str) -> list[str]:
    """Nombres crudos en el grafo que se leen como la relación `rel` (los alias y el formato se normalizan al leer)."""
    am = alias_map(ctx.db, ctx.brain.id)
    names = [r["name"] for r in rows(ctx.graph.query("MATCH ()-[r:RELATES_TO]->() RETURN DISTINCT r.name AS name"))]
    return [n for n in names if n and resolve(n, am) == rel]


@router.get("/facts/relations")
def fact_relations(ctx: BrainCtx = Depends(reader)):
    """Relaciones que hay en el grafo con su nombre normalizado y cuántos hechos tienen, para el filtro de Hechos."""
    am = alias_map(ctx.db, ctx.brain.id)
    out: dict[str, int] = {}
    for r in rows(ctx.graph.query("MATCH ()-[r:RELATES_TO]->() RETURN r.name AS name, count(r) AS n")):
        k = resolve(r["name"], am)
        out[k] = out.get(k, 0) + r["n"]
    return sorted(({"name": k, "count": v} for k, v in out.items() if k), key=lambda x: -x["count"])


@router.get("/facts")
def facts(
    ctx: BrainCtx = Depends(reader),
    status: str = Query("all", pattern="^(all|current|invalidated)$"),
    q: str = Query("", max_length=200),
    since: str = Query("", pattern=r"^(\d{4}-\d{2}-\d{2})?$"),
    until: str = Query("", pattern=r"^(\d{4}-\d{2}-\d{2})?$"),
    rel: str = Query("", max_length=120),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Hechos paginados con filtros (texto, relación, fechas de cuando se aprendieron, estado). `counts` da el total por estado con el resto de filtros aplicados."""
    raw = _raw_names(ctx, rel) if rel else None
    conds, par = _fact_conds(q, since, until, raw)
    base = ("WHERE " + " AND ".join(conds)) if conds else ""
    counts = {"all": 0, "current": 0, "invalidated": 0}
    for r in rows(ctx.graph.query(f"MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) {base} RETURN r.invalid_at IS NULL AS cur, count(r) AS n", par)):
        counts["current" if r["cur"] else "invalidated"] += r["n"]
    counts["all"] = counts["current"] + counts["invalidated"]
    st = {"current": "r.invalid_at IS NULL", "invalidated": "r.invalid_at IS NOT NULL"}.get(status)
    allc = conds + ([st] if st else [])
    where = ("WHERE " + " AND ".join(allc)) if allc else ""
    res = ctx.graph.query(
        f"MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) {where} RETURN {FACT_RETURN} "
        f"ORDER BY coalesce(r.valid_at, r.created_at) {order.upper()} SKIP $skip LIMIT $limit",
        {**par, "skip": offset, "limit": limit},
    )
    am = alias_map(ctx.db, ctx.brain.id)
    return {"total": counts[status], "counts": counts, "limit": limit, "offset": offset, "items": [_fact(f, amap=am) for f in rows(res)]}


@router.get("/timeline")
def timeline(
    ctx: BrainCtx = Depends(reader),
    entity: str = Query("", max_length=200),
    since: str = Query("", pattern=r"^(\d{4}-\d{2}-\d{2})?$"),
    until: str = Query("", pattern=r"^(\d{4}-\d{2}-\d{2})?$"),
    rel: str = Query("", max_length=120),
    limit: int = Query(200, ge=1, le=1000),
):
    """Eventos bi-temporales: cada hecho aporta 'aprendido' (valid_at) y, si procede, 'dejó de ser cierto' (invalid_at)."""
    raw = _raw_names(ctx, rel) if rel else None
    conds, par = _fact_conds(entity, since, until, raw)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    res = ctx.graph.query(
        f"MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) {where} RETURN {FACT_RETURN} "
        "ORDER BY coalesce(r.valid_at, r.created_at) DESC LIMIT $limit",
        {**par, "limit": limit},
    )
    events = []
    am = alias_map(ctx.db, ctx.brain.id)
    for f in (_fact(x, amap=am) for x in rows(res)):
        when = f["valid_at"] or f["created_at"]
        events.append({**f, "event": "learned", "at": when})
        if f["invalid_at"]:
            events.append({**f, "event": "invalidated", "at": f["invalid_at"]})
    events.sort(key=lambda e: parse_ts(e["at"]) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return events[:limit]


# --- Procedencia: de qué orígenes viene cada nodo y cada hecho del visor -------------------------
GROUPINGS = ("label", "source", "document", "author", "token")
_PROMOTED = re.compile(r"^documento (\d+) · trozo")  # source_description de un pasaje promovido a memoria (docbridge.promote)
_DOC_KIND = {"upload": "document", "directory": "directory", "wiki": "wiki"}


def _chunks(xs: list, n: int = 1000):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def _episode_origins(ctx: BrainCtx, kinds_of: dict[str, str], lang: str) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Orígenes de cada episodio según cada agrupación ({episodio: {agrupación: clave}}) y el nombre visible de cada clave.
    Episodio → `Episodic.source` (`kinds_of`) y, si salió de una propuesta, su autor, su token y el documento del que se promovió."""
    from .models import ApiToken, DocSource, Document, Proposal, User
    out: dict[str, dict[str, str]] = {e: {"source": s} for e, s in kinds_of.items() if s}
    names: dict[str, str] = {}
    kinds = {"text": tr("Texto", lang), "message": tr("Mensaje", lang), "json": "JSON", "document": tr("Documento", lang),
             "directory": tr("Carpeta de archivos", lang), "wiki": "Wiki"}
    ids = sorted(kinds_of)
    docs: dict[str, int] = {}
    for part in _chunks(ids):
        q = (select(Proposal.episode_uuid, Proposal.source_description, Proposal.author_id, User.name, Proposal.token_id, ApiToken.name)
             .join(User, User.id == Proposal.author_id).outerjoin(ApiToken, ApiToken.id == Proposal.token_id)
             .where(Proposal.brain_id == ctx.brain.id, Proposal.episode_uuid.in_(part)))
        for ep, desc, uid, uname, tid, tname in ctx.db.execute(q):
            o = out.setdefault(ep, {})
            o["author"], names[f"author:{uid}"] = f"author:{uid}", uname or f"#{uid}"
            if tid:
                o["token"], names[f"token:{tid}"] = f"token:{tid}", tname or f"#{tid}"
            m = _PROMOTED.match(desc or "")
            if m:
                docs[ep] = int(m.group(1))
    if docs:
        found = {d: (title or fname, kind) for d, title, fname, kind in ctx.db.execute(
            select(Document.id, Document.title, Document.filename, DocSource.kind).join(DocSource, DocSource.id == Document.source_id)
            .where(Document.brain_id == ctx.brain.id, Document.id.in_(set(docs.values()))))}
        for ep, d in docs.items():
            if d in found:
                title, kind = found[d]
                out[ep]["document"], names[f"document:{d}"] = f"document:{d}", title or f"#{d}"
                out[ep]["source"] = _DOC_KIND.get(kind, "document")
    for o in out.values():
        if "source" in o:
            s = o["source"]
            o["source"] = f"source:{s}"
            names.setdefault(o["source"], kinds.get(s, s))
    return out, names


def _provenance(ctx: BrainCtx, nodes: list[dict], links: list[dict], group_by: str, lang: str) -> dict:
    """Añade a cada nodo y hecho `provenance` (claves de origen por agrupación), `sources` (las de `group_by`) y `source_count`.
    Un nodo viene de los episodios que lo mencionan y de los de sus hechos visibles; un hecho, de los de `r.episodes` (`_episodes`).
    Devuelve el catálogo de orígenes por agrupación, de mayor a menor, con su nombre y cuántos nodos y hechos respalda."""
    node_eps: dict[str, set[str]] = {n["uuid"]: set() for n in nodes}
    kinds_of: dict[str, str] = {}  # episodio → Episodic.source, leído junto con las menciones para no buscar cada episodio aparte
    if node_eps:
        for r in rows(ctx.graph.query("MATCH (e:Episodic)-[:MENTIONS]->(n:Entity) WHERE n.uuid IN $ids "
                                      "RETURN n.uuid AS uuid, toLower(coalesce(e.source, '')) AS kind, collect(DISTINCT e.uuid) AS eps", {"ids": list(node_eps)})):
            eps = [x for x in r["eps"] if x]
            node_eps[r["uuid"]].update(eps)
            kinds_of.update(dict.fromkeys(eps, r["kind"]))
    for link in links:
        for end in (link["source_uuid"], link["target_uuid"]):
            if end in node_eps:
                node_eps[end].update(link["_episodes"])
    missing = sorted({e for x in links for e in x["_episodes"]} - kinds_of.keys())
    for part in _chunks(missing):  # episodios de un hecho que no mencionan a sus extremos: raros
        for r in rows(ctx.graph.query("MATCH (e:Episodic) WHERE e.uuid IN $eps RETURN e.uuid AS uuid, toLower(coalesce(e.source, '')) AS source", {"eps": part})):
            kinds_of[r["uuid"]] = r["source"]
    for e in missing:
        kinds_of.setdefault(e, "")  # episodio ya borrado: sin tipo, pero aún puede tener propuesta
    origins, names = _episode_origins(ctx, kinds_of, lang)
    tally: dict[str, dict[str, list[int]]] = {g: {} for g in GROUPINGS}

    def fill(item: dict, eps: set[str], labels: list[str] | None, slot: int) -> None:
        prov = {g: sorted({origins[e][g] for e in eps if g in origins.get(e, {})}) for g in GROUPINGS if g != "label"}
        prov["label"] = [f"label:{x}" for x in labels] if labels else []
        for g, keys in prov.items():
            for k in keys:
                tally[g].setdefault(k, [0, 0])[slot] += 1
        item["provenance"], item["sources"], item["source_count"] = prov, prov[group_by], len(prov[group_by])

    for n in nodes:
        fill(n, node_eps[n["uuid"]], n.get("labels") or [], 0)
    for link in links:
        fill(link, set(link["_episodes"]), None, 1)
    names.update({k: k.removeprefix("label:") for k in tally["label"]})
    return {g: sorted(({"key": k, "name": names.get(k, k), "nodes": c[0], "facts": c[1]} for k, c in t.items()), key=lambda x: (-x["nodes"], -x["facts"], x["name"]))
            for g, t in tally.items()}


@router.get("/graph")
def graph_view(
    request: Request,
    ctx: BrainCtx = Depends(reader),
    seeds: int = Query(25, ge=1, le=100),
    depth: int = Query(1, ge=0, le=2),
    cap: int = Query(300, ge=10, le=1000),
    node: str = "",
    as_of: str = "",
    include_invalidated: bool = True,
    group_by: str = Query("", pattern="^(" + "|".join(GROUPINGS) + ")?$"),
):
    """Subgrafo recortado: semillas por grado (o un nodo concreto), expansión hasta `depth` saltos, tope `cap` nodos.
    Con `group_by`, cada nodo y hecho lleva su procedencia: `sources`/`source_count` según esa agrupación y `provenance` con todas,
    para que el visor cambie de agrupación sin volver a pedir el grafo; `groups` es el catálogo de orígenes de cada agrupación.
    Sin él no se calcula: en un brain grande puede costar más que el propio subgrafo."""
    G = ctx.graph
    at = parse_ts(as_of) if as_of else None
    if node:
        ids = {node}
    else:
        res = G.query(
            "MATCH (n:Entity) OPTIONAL MATCH (n)-[r:RELATES_TO]-() WITH n, count(r) AS d "
            "ORDER BY d DESC LIMIT $k RETURN n.uuid AS uuid",
            {"k": seeds},
        )
        ids = {r["uuid"] for r in rows(res)}
    frontier = set(ids)
    for _ in range(depth):
        if not frontier or len(ids) >= cap:
            break
        res = G.query(
            "MATCH (n:Entity)-[:RELATES_TO]-(m:Entity) WHERE n.uuid IN $ids "
            "WITH DISTINCT m.uuid AS uuid LIMIT $cap RETURN uuid",
            {"ids": list(frontier), "cap": cap},
        )
        new = {r["uuid"] for r in rows(res)} - ids
        for u in list(new)[: max(0, cap - len(ids))]:
            ids.add(u)
        frontier = new
    edges = rows(G.query(
        f"MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE a.uuid IN $ids AND b.uuid IN $ids RETURN {FACT_RETURN}",
        {"ids": list(ids)},
    ))
    links = []
    am = alias_map(ctx.db, ctx.brain.id)
    for e in (_fact(x, at, am) for x in edges):
        if e["status"] == "future" or (e["status"] == "invalidated" and not include_invalidated):
            continue
        links.append({k: e[k] for k in ("uuid", "name", "fact", "valid_at", "invalid_at", "status", "source_uuid", "target_uuid")}
                      | {"source": e["source_uuid"], "target": e["target_uuid"], "_episodes": e["episodes"]})
    nodes = rows(G.query(
        "MATCH (n:Entity) WHERE n.uuid IN $ids OPTIONAL MATCH (n)-[r:RELATES_TO]-() "
        "RETURN n.uuid AS uuid, n.name AS name, [l IN labels(n) WHERE l <> 'Entity'] AS labels, "
        "substring(n.summary, 0, 300) AS summary, count(r) AS degree",
        {"ids": list(ids)},
    ))
    out = {"nodes": nodes, "links": links, "truncated": len(ids) >= cap}
    if group_by:
        out |= {"group_by": group_by, "groups": _provenance(ctx, nodes, links, group_by, language(request))}
    for link in links:
        del link["_episodes"]
    return out


# --- Vocabulario: relaciones y entidades ------------------------------------------------------
GENERIC_RELS = {"RELATES_TO", "MENTIONED_IN", "PARTICIPATES_IN", "ASSOCIATED_WITH", "RELATED_TO"}
_VERSION = re.compile(r"\s*[\(\[]?\bv?\d+(\.\d+){1,3}[\w.\-]*[\)\]]?\s*$", re.I)


def _entity_key(name: str) -> str:
    s = _VERSION.sub("", name or "").strip().lower()
    return re.sub(r"[\s_\-]+", " ", s)


@router.get("/vocabulary")
def vocabulary(ctx: BrainCtx = Depends(reader)):
    G = ctx.graph
    rel_rows = rows(G.query("MATCH ()-[r:RELATES_TO]->() RETURN r.name AS name, count(*) AS n"))
    am = alias_map(ctx.db, ctx.brain.id)
    canon: dict[str, dict] = {}
    for r in rel_rows:
        c = resolve(r["name"], am)
        d = canon.setdefault(c, {"name": c, "facts": 0, "variants": [], "generic": c in GENERIC_RELS})
        d["facts"] += r["n"]
        d["variants"].append({"raw": r["name"], "facts": r["n"]})
    relations = sorted(canon.values(), key=lambda d: -d["facts"])
    total = sum(d["facts"] for d in relations) or 1
    tail = [d for d in relations if d["facts"] <= 2]
    labels = rows(G.query(
        "MATCH (n:Entity) WITH [l IN labels(n) WHERE l <> 'Entity'] AS ls "
        "UNWIND (CASE WHEN size(ls)=0 THEN ['(sin tipo)'] ELSE ls END) AS label RETURN label, count(*) AS count ORDER BY count DESC"
    ))
    ents = rows(G.query(
        "MATCH (n:Entity) OPTIONAL MATCH (n)-[r:RELATES_TO]-() "
        "RETURN n.uuid AS uuid, n.name AS name, [l IN labels(n) WHERE l <> 'Entity'] AS labels, count(r) AS degree"
    ))
    groups: dict[str, list] = {}
    for e in ents:
        groups.setdefault(_entity_key(e["name"]), []).append(e)
    ignored = {a.alias for a in ctx.db.scalars(select(VocabAlias).where(VocabAlias.brain_id == ctx.brain.id, VocabAlias.kind == "dup_ignore"))}
    dups = sorted(
        ({"key": k, "members": sorted(v, key=lambda x: -x["degree"])} for k, v in groups.items() if len(v) > 1 and k and k not in ignored),
        key=lambda g: -sum(m["degree"] for m in g["members"]),
    )
    return {
        "summary": {
            "relation_types_raw": len(rel_rows),
            "relation_types_canonical": len(relations),
            "facts": total if relations else 0,
            "generic_facts": sum(d["facts"] for d in relations if d["generic"]),
            "generic_pct": round(100 * sum(d["facts"] for d in relations if d["generic"]) / total, 1),
            "long_tail_types": len(tail),
            "long_tail_facts": sum(d["facts"] for d in tail),
            "entities": len(ents),
            "duplicate_groups": len(dups),
            "duplicate_ignored": len(ignored),
        },
        "ignored_duplicates": sorted(ignored),
        "relations": relations,
        "labels": labels,
        "duplicates": dups[:200],
    }


# --- Consola Cypher de solo lectura -----------------------------------------------------------
import re  # noqa: E402

from falkordb.edge import Edge  # noqa: E402
from falkordb.node import Node  # noqa: E402
from falkordb.path import Path as FPath  # noqa: E402
from pydantic import BaseModel  # noqa: E402

_WRITE = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH)\b", re.I)
_HIDE = {"name_embedding", "fact_embedding", "summary_embedding", "embedding"}
MAX_ROWS = 500


class CypherReq(BaseModel):
    query: str


def _props(p: dict) -> dict:
    return {k: (v if not isinstance(v, list) or len(v) < 50 else f"[{len(v)} valores]") for k, v in (p or {}).items() if k not in _HIDE and not is_shadow(k)}


def _node(n: Node) -> dict:
    return {"_type": "node", "id": str(n.id), "labels": n.labels, "properties": _props(n.properties)}


def _edge(e: Edge) -> dict:
    return {"_type": "edge", "id": str(e.id), "relation": e.relation, "source": str(e.src_node), "target": str(e.dest_node),
            "properties": _props(e.properties)}


def _val(v, nodes: dict, edges: dict):
    if isinstance(v, Node):
        d = _node(v); nodes[d["id"]] = d; return d
    if isinstance(v, Edge):
        d = _edge(v); edges[d["id"]] = d; return d
    if isinstance(v, FPath):
        for n in v.nodes():
            d = _node(n); nodes[d["id"]] = d
        for e in v.edges():
            d = _edge(e); edges[d["id"]] = d
        return {"_type": "path", "length": v.edge_count()}
    if isinstance(v, list):
        return [_val(x, nodes, edges) for x in v]
    if isinstance(v, dict):
        return {k: _val(x, nodes, edges) for k, x in v.items()}
    return v


@router.post("/query")
def cypher(req: CypherReq, ctx: BrainCtx = Depends(reader)):
    """Ejecuta Cypher SOLO LECTURA (GRAPH.RO_QUERY; además se rechazan palabras de escritura)."""
    q = req.query.strip().rstrip(";")
    if not q:
        raise HTTPException(400, "consulta vacía")
    if _WRITE.search(q):
        raise HTTPException(400, "solo se permiten consultas de lectura")
    import time

    t = time.time()
    try:
        res = ctx.graph.ro_query(q, timeout=15000)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)) from e
    nodes: dict = {}
    edges: dict = {}
    columns = [h[1] if isinstance(h, (list, tuple)) else h for h in res.header]
    rws = [[_val(c, nodes, edges) for c in r] for r in res.result_set[:MAX_ROWS]]
    return {"columns": columns, "rows": rws, "truncated": len(res.result_set) > MAX_ROWS, "total": len(res.result_set),
            "nodes": list(nodes.values()), "edges": [e for e in edges.values() if e["source"] in nodes and e["target"] in nodes],
            "ms": round((time.time() - t) * 1000)}
