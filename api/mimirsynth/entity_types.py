"""Tipos de entidad editables: catálogo de la ontología del brain + reetiquetado de los nodos del grafo (renombrar / fusionar).
Todo cambio se registra en `vocab_ops` con lo necesario para deshacerlo."""
import copy

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from datetime import datetime, timezone

from .db import client, graph, rows
from .deps import BrainCtx, admin_of_brain, audit, curator_of_brain, reader
from .roles import allows
from .models import BrainOntology, VocabAlias, VocabOp
from .ontology import NAME

router = APIRouter(prefix="/api/brains/{slug}/vocab")
EMPTY = {"entity_types": [], "edge_types": [], "edge_type_map": [], "instructions": ""}


class TypeIn(BaseModel):
    name: str
    description: str = Field(min_length=3, max_length=1500)


class DescIn(BaseModel):
    description: str = Field(min_length=3, max_length=1500)


class MoveIn(BaseModel):
    to: str


def _check(name: str) -> str:
    if not NAME.match(name or ""):
        raise HTTPException(400, "nombre inválido: PascalCase sin espacios (p. ej. Service)")
    if name == "Entity":
        raise HTTPException(400, "«Entity» es la etiqueta base de Graphiti")
    return name


def _onto(ctx: BrainCtx) -> dict:
    row = ctx.db.get(BrainOntology, ctx.brain.id)
    return copy.deepcopy(row.data) if row and row.data else copy.deepcopy(EMPTY)


def _save(ctx: BrainCtx, data: dict) -> None:
    row = ctx.db.get(BrainOntology, ctx.brain.id)
    if row:
        row.data = data
    else:
        ctx.db.add(BrainOntology(brain_id=ctx.brain.id, data=data))
    ctx.db.flush()


def _counts(ctx: BrainCtx) -> dict[str, int]:
    res = rows(ctx.graph.query(
        "MATCH (n:Entity) WITH [l IN labels(n) WHERE l <> 'Entity'] AS ls "
        "UNWIND (CASE WHEN size(ls)=0 THEN ['(sin tipo)'] ELSE ls END) AS label RETURN label, count(*) AS count"))
    return {r["label"]: r["count"] for r in res}


def _record(ctx: BrainCtx, kind: str, summary: str, **detail) -> VocabOp:
    op = VocabOp(brain_id=ctx.brain.id, kind=kind, summary=summary, detail=detail, user_id=ctx.user.id)
    ctx.db.add(op)
    ctx.db.commit()
    audit(ctx.db, ctx.user, f"vocab.{kind}", ctx.brain, summary=summary)
    return op


@router.get("/types")
def list_types(ctx: BrainCtx = Depends(reader)):
    onto = _onto(ctx)
    counts = _counts(ctx)
    defined = {t["name"]: t["description"] for t in onto["entity_types"]}
    items = [{"name": n, "description": d, "in_ontology": True, "count": counts.get(n, 0)} for n, d in defined.items()]
    items += [{"name": n, "description": "", "in_ontology": False, "count": c} for n, c in counts.items() if n not in defined and n != "(sin tipo)"]
    items.sort(key=lambda i: (-i["count"], i["name"]))
    ops = ctx.db.scalars(select(VocabOp).where(VocabOp.brain_id == ctx.brain.id).order_by(VocabOp.id.desc()).limit(15))
    return {"items": items, "untyped": counts.get("(sin tipo)", 0),
            "ops": [{"id": o.id, "kind": o.kind, "summary": o.summary, "status": o.status, "created_at": o.created_at} for o in ops]}


@router.get("/types/{name}/preview")
def preview(name: str, to: str, ctx: BrainCtx = Depends(reader)):
    _check(name); _check(to)
    q = lambda extra="": rows(ctx.graph.query(f"MATCH (n:Entity:`{name}`) {extra} RETURN count(n) AS n"))[0]["n"]  # noqa: E731
    onto = _onto(ctx)
    return {"entities": q(), "already_target": q(f"WHERE n:`{to}`"), "target_in_ontology": any(t["name"] == to for t in onto["entity_types"]),
            "sample": [r["name"] for r in rows(ctx.graph.query(f"MATCH (n:Entity:`{name}`) RETURN n.name AS name LIMIT 8"))]}


@router.post("/types", status_code=201)
def create_type(body: TypeIn, ctx: BrainCtx = Depends(admin_of_brain)):
    _check(body.name)
    onto = _onto(ctx)
    if any(t["name"] == body.name for t in onto["entity_types"]):
        raise HTTPException(409, "ese tipo ya existe en la ontología")
    before = copy.deepcopy(onto)
    onto["entity_types"].append({"name": body.name, "description": body.description})
    _save(ctx, onto)
    _record(ctx, "type.create", f"Añadido el tipo {body.name}", onto_before=before)
    return {"ok": True}


@router.put("/types/{name}")
def edit_type(name: str, body: DescIn, ctx: BrainCtx = Depends(admin_of_brain)):
    _check(name)
    onto = _onto(ctx)
    t = next((t for t in onto["entity_types"] if t["name"] == name), None)
    if not t:
        raise HTTPException(404, "el tipo no está en la ontología (créalo primero)")
    before = copy.deepcopy(onto)
    t["description"] = body.description
    _save(ctx, onto)
    _record(ctx, "type.edit", f"Editada la descripción de {name}", onto_before=before)
    return {"ok": True}


@router.delete("/types/{name}")
def delete_type(name: str, ctx: BrainCtx = Depends(admin_of_brain)):
    """Quita el tipo de la ontología (no toca el grafo: las entidades conservan su etiqueta)."""
    _check(name)
    onto = _onto(ctx)
    if not any(t["name"] == name for t in onto["entity_types"]):
        raise HTTPException(404, "el tipo no está en la ontología")
    before = copy.deepcopy(onto)
    onto["entity_types"] = [t for t in onto["entity_types"] if t["name"] != name]
    onto["edge_type_map"] = [m for m in onto["edge_type_map"] if name not in (m["source"], m["target"])]
    _save(ctx, onto)
    _record(ctx, "type.delete", f"Quitado el tipo {name} de la ontología", onto_before=before)
    return {"ok": True}


@router.post("/types/{name}/move")
def move_type(name: str, body: MoveIn, ctx: BrainCtx = Depends(admin_of_brain)):
    """Renombra el tipo `name` a `to`, o lo fusiona si `to` ya existe: reetiqueta sus entidades y ajusta la ontología."""
    _check(name); _check(body.to)
    if name == body.to:
        raise HTTPException(400, "el origen y el destino coinciden")
    g = graph(ctx.brain.graph_name)
    all_ids = [r["u"] for r in rows(g.query(f"MATCH (n:Entity:`{name}`) RETURN n.uuid AS u"))]
    both = {r["u"] for r in rows(g.query(f"MATCH (n:Entity:`{name}`:`{body.to}`) RETURN n.uuid AS u"))}
    moved = [u for u in all_ids if u not in both]
    onto = _onto(ctx)
    before = copy.deepcopy(onto)
    defined = {t["name"]: t for t in onto["entity_types"]}
    if name in defined and body.to not in defined:           # renombrar: el destino hereda la descripción
        defined[name]["name"] = body.to
        merged = False
    else:                                                    # fusionar: el origen desaparece de la ontología
        onto["entity_types"] = [t for t in onto["entity_types"] if t["name"] != name]
        merged = body.to in defined
    for m in onto["edge_type_map"]:
        m["source"] = body.to if m["source"] == name else m["source"]
        m["target"] = body.to if m["target"] == name else m["target"]
    seen, uniq = set(), []                                   # el mapa puede quedar con pares repetidos tras fusionar
    for m in onto["edge_type_map"]:
        k = (m["source"], m["target"])
        if k in seen:
            prev = next(x for x in uniq if (x["source"], x["target"]) == k)
            prev["edge_types"] = sorted(set(prev["edge_types"]) | set(m["edge_types"]))
        else:
            seen.add(k); uniq.append(m)
    onto["edge_type_map"] = uniq
    if all_ids:
        g.query(f"MATCH (n:Entity:`{name}`) REMOVE n:`{name}` SET n:`{body.to}`")
    _save(ctx, onto)
    verb = "Fusionado" if merged else "Renombrado"
    _record(ctx, "type.merge" if verb == "Fusionado" else "type.rename", f"{verb} {name} → {body.to} ({len(all_ids)} entidades)",
            onto_before=before, frm=name, to=body.to, moved=moved, both=sorted(both))
    return {"ok": True, "entities": len(all_ids)}


@router.post("/ops/{oid}/revert")
def revert_op(oid: int, ctx: BrainCtx = Depends(curator_of_brain)):
    op = ctx.db.get(VocabOp, oid)
    if not op or op.brain_id != ctx.brain.id:
        raise HTTPException(404, "cambio no encontrado")
    if not op.kind.startswith("fact.") and not allows(ctx.role, "admin"):
        raise HTTPException(403, "solo un administrador del brain puede deshacer cambios de vocabulario")
    if op.status != "applied":
        raise HTTPException(409, "ese cambio ya está revertido")
    later = next((o.id for o in ctx.db.scalars(select(VocabOp).where(VocabOp.brain_id == ctx.brain.id, VocabOp.id > oid, VocabOp.status == "applied"))
                  if not o.detail.get("auto")), None)  # las fusiones automáticas al ingerir no bloquean el deshacer
    if later:
        raise HTTPException(409, "hay cambios posteriores: deshaz primero el más reciente")
    d = op.detail
    if op.kind.startswith("fact."):
        from .facts_admin import undo
        undo(ctx, op.kind, d)
        op.status = "reverted"
        ctx.db.commit()
        audit(ctx.db, ctx.user, "vocab.revert", ctx.brain, summary=op.summary)
        return {"ok": True}
    if op.kind == "entity.merge":
        _undo_merge(ctx, d)
        op.status = "reverted"
        ctx.db.commit()
        audit(ctx.db, ctx.user, "vocab.revert", ctx.brain, summary=op.summary)
        return {"ok": True}
    if "frm" in d:
        g = graph(ctx.brain.graph_name)
        for chunk_ids, remove_to in ((d.get("moved", []), True), (d.get("both", []), False)):
            for i in range(0, len(chunk_ids), 500):
                ids = chunk_ids[i:i + 500]
                rm = f"REMOVE n:`{d['to']}` " if remove_to else ""
                g.query(f"MATCH (n:Entity) WHERE n.uuid IN $ids {rm}SET n:`{d['frm']}`", {"ids": ids})
    onto = _onto(ctx)
    for k in ("entity_types", "edge_types", "edge_type_map", "instructions"):
        if k in d["onto_before"]:
            onto[k] = d["onto_before"][k]
    _save(ctx, onto)
    op.status = "reverted"
    ctx.db.commit()
    audit(ctx.db, ctx.user, "vocab.revert", ctx.brain, summary=op.summary)
    return {"ok": True}


# --- Tipos de relación, reglas del mapa e instrucciones (ontología) --------------------------------

class RelIn(BaseModel):
    name: str
    description: str = Field(min_length=3, max_length=1500)


class MapIn(BaseModel):
    source: str
    target: str
    edge_types: list[str] = Field(max_length=60)


class InstrIn(BaseModel):
    instructions: str = Field("", max_length=4000)


def _validated(ctx: BrainCtx, onto: dict) -> dict:
    """Comprueba la coherencia de la ontología resultante con las mismas reglas que al aplicar un paquete."""
    from .ontology import OntologyIn, validate_ontology
    validate_ontology(OntologyIn(**onto))
    return onto


def _done(op: VocabOp) -> dict:
    return {"ok": True, "op": op.id, "summary": op.summary}


@router.post("/relations", status_code=201)
def create_relation(body: RelIn, ctx: BrainCtx = Depends(admin_of_brain)):
    _check(body.name)
    onto = _onto(ctx)
    if any(t["name"] == body.name for t in onto["edge_types"]):
        raise HTTPException(409, "ese tipo de relación ya existe en la ontología")
    before = copy.deepcopy(onto)
    onto["edge_types"].append({"name": body.name, "description": body.description})
    _save(ctx, _validated(ctx, onto))
    return _done(_record(ctx, "relation.create", f"Añadido el tipo de relación {body.name}", onto_before=before))


@router.put("/relations/{name}")
def edit_relation(name: str, body: DescIn, ctx: BrainCtx = Depends(admin_of_brain)):
    onto = _onto(ctx)
    t = next((t for t in onto["edge_types"] if t["name"] == name), None)
    if not t:
        raise HTTPException(404, "el tipo de relación no está en la ontología")
    before = copy.deepcopy(onto)
    t["description"] = body.description
    _save(ctx, onto)
    return _done(_record(ctx, "relation.edit", f"Editada la descripción de la relación {name}", onto_before=before))


@router.delete("/relations/{name}")
def delete_relation(name: str, ctx: BrainCtx = Depends(admin_of_brain)):
    """Quita el tipo de relación de la ontología y de las reglas del mapa (las reglas que se quedan sin relaciones desaparecen). No toca el grafo."""
    onto = _onto(ctx)
    if not any(t["name"] == name for t in onto["edge_types"]):
        raise HTTPException(404, "el tipo de relación no está en la ontología")
    before = copy.deepcopy(onto)
    onto["edge_types"] = [t for t in onto["edge_types"] if t["name"] != name]
    for m in onto["edge_type_map"]:
        m["edge_types"] = [e for e in m["edge_types"] if e != name]
    onto["edge_type_map"] = [m for m in onto["edge_type_map"] if m["edge_types"]]
    _save(ctx, _validated(ctx, onto))
    return _done(_record(ctx, "relation.delete", f"Quitado el tipo de relación {name} de la ontología", onto_before=before))


@router.put("/map")
def set_map_rule(body: MapIn, ctx: BrainCtx = Depends(admin_of_brain)):
    """Crea o sustituye la regla (origen, destino): qué relaciones se permiten entre esos dos tipos. Sin relaciones, la regla se elimina."""
    onto = _onto(ctx)
    before = copy.deepcopy(onto)
    rest = [m for m in onto["edge_type_map"] if (m["source"], m["target"]) != (body.source, body.target)]
    existed = len(rest) != len(onto["edge_type_map"])
    edges = list(dict.fromkeys(body.edge_types))
    onto["edge_type_map"] = rest + ([{"source": body.source, "target": body.target, "edge_types": edges}] if edges else [])
    if not existed and not edges:
        raise HTTPException(404, "esa regla no existe")
    _save(ctx, _validated(ctx, onto))
    verb = "Quitada" if not edges else ("Actualizada" if existed else "Añadida")
    return _done(_record(ctx, "map.set", f"{verb} la regla {body.source} → {body.target}", onto_before=before))


@router.put("/instructions")
def set_instructions(body: InstrIn, ctx: BrainCtx = Depends(admin_of_brain)):
    onto = _onto(ctx)
    before = copy.deepcopy(onto)
    onto["instructions"] = body.instructions.strip()
    _save(ctx, onto)
    return _done(_record(ctx, "instructions.edit", "Editadas las instrucciones de extracción", onto_before=before))


# --- Fusión de entidades duplicadas ---------------------------------------------------------------
# Las aristas (RELATES_TO, MENTIONS) del duplicado se recrean sobre la entidad principal conservando uuid y propiedades
# (embedding incluido). El duplicado queda como «lápida»: pierde la etiqueta Entity (Graphiti y la UI dejan de verlo) y guarda
# `merged_into`. Las aristas entre duplicado y principal no se mueven. Deshacer = devolver las aristas por uuid y restaurar la etiqueta.
REL_TYPES = ("RELATES_TO", "MENTIONS")
SNAP_KEEP = 2


class MergeIn(BaseModel):
    keeper: str
    merge: list[str] = Field(min_length=1, max_length=50)


class KeyIn(BaseModel):
    key: str = Field(min_length=1, max_length=300)


def _entity(g, uuid: str) -> dict:
    r = rows(g.query("MATCH (n:Entity {uuid:$u}) RETURN n.uuid AS uuid, n.name AS name", {"u": uuid}))
    if not r:
        raise HTTPException(404, f"entidad no encontrada o ya fusionada: {uuid}")
    return r[0]


def _check_merge(g, body: MergeIn) -> tuple[dict, list[dict]]:
    if body.keeper in body.merge:
        raise HTTPException(400, "la entidad principal no puede estar entre las que se fusionan")
    return _entity(g, body.keeper), [_entity(g, u) for u in dict.fromkeys(body.merge)]


@router.post("/duplicates/preview")
def merge_preview(body: MergeIn, ctx: BrainCtx = Depends(reader)):
    g = graph(ctx.brain.graph_name)
    keeper, dups = _check_merge(g, body)
    out = []
    for d in dups:
        c = {}
        for t in REL_TYPES:
            c[f"{t}_out"] = rows(g.query(f"MATCH (d:Entity {{uuid:$d}})-[r:{t}]->(b) WHERE b.uuid <> $k RETURN count(r) AS n", {"d": d["uuid"], "k": keeper["uuid"]}))[0]["n"]
            c[f"{t}_in"] = rows(g.query(f"MATCH (a)-[r:{t}]->(d:Entity {{uuid:$d}}) WHERE a.uuid <> $k RETURN count(r) AS n", {"d": d["uuid"], "k": keeper["uuid"]}))[0]["n"]
        loops = rows(g.query("MATCH (d:Entity {uuid:$d})-[r]-(k:Entity {uuid:$k}) RETURN count(r) AS n", {"d": d["uuid"], "k": keeper["uuid"]}))[0]["n"]
        repeated = rows(g.query(
            "MATCH (d:Entity {uuid:$d})-[r:RELATES_TO]-(b), (k:Entity {uuid:$k})-[r2:RELATES_TO]-(b) WHERE b.uuid <> $k AND r.fact = r2.fact RETURN count(r) AS n",
            {"d": d["uuid"], "k": keeper["uuid"]}))[0]["n"]
        out.append({"uuid": d["uuid"], "name": d["name"], "facts": c["RELATES_TO_out"] + c["RELATES_TO_in"],
                    "mentions": c["MENTIONS_out"] + c["MENTIONS_in"], "between": loops, "repeated_facts": repeated})
    return {"keeper": keeper, "items": out}


def _snapshot(ctx: BrainCtx) -> str:
    """Copia de seguridad del grafo antes de fusionar (nombre con «_»: no aparece en la lista de grafos). Conserva las últimas SNAP_KEEP."""
    name = f"_snap_{ctx.brain.graph_name}_{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    c = client()
    c.select_graph(ctx.brain.graph_name).copy(name)
    snaps = sorted(x for x in c.list_graphs() if x.startswith(f"_snap_{ctx.brain.graph_name}_"))
    for old in snaps[:-SNAP_KEEP]:
        c.select_graph(old).delete()
    return name


@router.post("/duplicates/merge")
def merge_entities(body: MergeIn, ctx: BrainCtx = Depends(admin_of_brain)):
    g = graph(ctx.brain.graph_name)
    keeper, dups = _check_merge(g, body)
    snap = _snapshot(ctx)
    entries = []
    try:
        _merge_all(g, keeper, dups, entries)
    except Exception as e:  # deja constancia de lo ya hecho para poder deshacerlo
        if entries:
            _record(ctx, "entity.merge", f"Fusión incompleta → {keeper['name']} (error: {str(e)[:120]})", keeper=keeper, entries=entries, snapshot=snap, onto_before=None)
        raise HTTPException(500, f"la fusión falló: {e}")
    names = ", ".join(e["name"] for e in entries)
    _record(ctx, "entity.merge", f"Fusionado {names} → {keeper['name']}", keeper=keeper, entries=entries, snapshot=snap, onto_before=None)
    return {"ok": True, "snapshot": snap, "merged": len(entries)}


def _merge_all(g, keeper: dict, dups: list[dict], entries: list[dict]) -> None:
    for d in dups:
        moved = {}
        for t in REL_TYPES:
            for direction in ("out", "in"):
                pat = f"(d)-[r:{t}]->(b)" if direction == "out" else f"(b)-[r:{t}]->(d)"
                new = f"(k)-[r2:{t}]->(b)" if direction == "out" else f"(b)-[r2:{t}]->(k)"
                p = {"d": d["uuid"], "k": keeper["uuid"]}
                ids = [x["u"] for x in rows(g.query(f"MATCH (d:Entity {{uuid:$d}}), {pat} WHERE b.uuid <> $k RETURN r.uuid AS u", p))]
                if ids:
                    g.query(f"MATCH (k:Entity {{uuid:$k}}), (d:Entity {{uuid:$d}}), {pat} WHERE b.uuid <> $k CREATE {new} SET r2 = properties(r) DELETE r", p)
                    moved[f"{t}:{direction}"] = ids
        g.query("MATCH (d:Entity {uuid:$d}), (k:Entity {uuid:$k}) REMOVE d:Entity SET d:Merged, d.merged_into=$k, d.merged_at=$at "
                "SET k.aliases = coalesce(k.aliases, []) + [$name]", {"d": d["uuid"], "k": keeper["uuid"], "at": datetime.now(timezone.utc).isoformat(), "name": d["name"]})
        entries.append({"uuid": d["uuid"], "name": d["name"], "moved": moved})


def _undo_merge(ctx: BrainCtx, d: dict) -> None:
    g = graph(ctx.brain.graph_name)
    for e in reversed(d["entries"]):
        for key, ids in e["moved"].items():
            t, direction = key.split(":")
            p = {"d": e["uuid"], "k": d["keeper"]["uuid"], "u": ids}
            if direction == "out":
                g.query(f"MATCH (d:Merged {{uuid:$d}}), (k:Entity {{uuid:$k}})-[r:{t}]->(b) WHERE r.uuid IN $u CREATE (d)-[r2:{t}]->(b) SET r2 = properties(r) DELETE r", p)
            else:
                g.query(f"MATCH (d:Merged {{uuid:$d}}), (k:Entity {{uuid:$k}}), (b)-[r:{t}]->(k) WHERE r.uuid IN $u CREATE (b)-[r2:{t}]->(d) SET r2 = properties(r) DELETE r", p)
        g.query("MATCH (d:Merged {uuid:$d}) REMOVE d:Merged SET d:Entity REMOVE d.merged_into, d.merged_at", {"d": e["uuid"]})
        g.query("MATCH (k:Entity {uuid:$k}) SET k.aliases = [x IN coalesce(k.aliases, []) WHERE x <> $n]", {"k": d["keeper"]["uuid"], "n": e["name"]})


@router.post("/duplicates/ignore", status_code=201)
def ignore_group(body: KeyIn, ctx: BrainCtx = Depends(admin_of_brain)):
    """Marca un grupo de posibles duplicados como «no son duplicados» (reutiliza vocab_aliases con kind='dup_ignore')."""
    key = body.key.strip().lower()
    if not ctx.db.scalar(select(VocabAlias.id).where(VocabAlias.brain_id == ctx.brain.id, VocabAlias.kind == "dup_ignore", VocabAlias.alias == key)):
        ctx.db.add(VocabAlias(brain_id=ctx.brain.id, kind="dup_ignore", alias=key, canonical="", created_by=ctx.user.id))
        ctx.db.commit()
        audit(ctx.db, ctx.user, "vocab.duplicates.ignore", ctx.brain, key=key)
    return {"ok": True}


@router.delete("/duplicates/ignore")
def unignore_group(key: str, ctx: BrainCtx = Depends(admin_of_brain)):
    a = ctx.db.scalar(select(VocabAlias).where(VocabAlias.brain_id == ctx.brain.id, VocabAlias.kind == "dup_ignore", VocabAlias.alias == key.strip().lower()))
    if a:
        ctx.db.delete(a)
        ctx.db.commit()
    return {"ok": True}
