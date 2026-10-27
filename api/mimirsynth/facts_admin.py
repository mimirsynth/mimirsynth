"""Edición de hechos desde la UI (curador o superior): corregir texto (con nuevo embedding), cambiar el tipo de relación,
invalidar / reactivar y borrar. Cada cambio se registra en vocab_ops con el estado anterior para poder deshacerlo."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .db import rows
from .deps import BrainCtx, curator_of_brain
from .embed import get_embedder
from .entity_types import _record
from .reembed import is_shadow
from .vocab import canon_rel

router = APIRouter(prefix="/api/brains/{slug}/facts")
_HIDE = {"fact_embedding"}  # y las propiedades auxiliares de un cambio de modelo (reembed.is_shadow)


class EditIn(BaseModel):
    fact: str | None = Field(None, min_length=3, max_length=2000)
    name: str | None = Field(None, max_length=80)


def _get(ctx: BrainCtx, uuid: str) -> dict:
    r = rows(ctx.graph.query(
        "MATCH (a:Entity)-[r:RELATES_TO {uuid:$u}]->(b:Entity) RETURN r.name AS name, r.fact AS fact, r.invalid_at AS invalid_at, r.expired_at AS expired_at, "
        "a.name AS source, b.name AS target", {"u": uuid}))
    if not r:
        raise HTTPException(404, "hecho no encontrado")
    return r[0]


def _set_embedding(ctx: BrainCtx, uuid: str, text: str) -> None:
    v = get_embedder().embed([text])[0]
    ctx.graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() SET r.fact_embedding = vecf32($v)", {"u": uuid, "v": v})


def _label(f: dict) -> str:
    return f'«{(f["fact"] or "")[:60]}»'


@router.patch("/{uuid}")
def edit_fact(uuid: str, body: EditIn, ctx: BrainCtx = Depends(curator_of_brain)):
    cur = _get(ctx, uuid)
    name = canon_rel(body.name) if body.name else None
    if name and not (2 <= len(name) <= 60 and name.replace("_", "").isalnum()):
        raise HTTPException(400, "nombre de relación inválido (letras, números y _)")
    changes = {}
    if body.fact is not None and body.fact.strip() != (cur["fact"] or ""):
        changes["fact"] = body.fact.strip()
    if name and name != cur["name"]:
        changes["name"] = name
    if not changes:
        raise HTTPException(400, "no hay cambios")
    if "fact" in changes:  # primero el embedding: si el motor falla, no se toca nada
        vec = get_embedder().embed([changes["fact"]])[0]
    sets = ", ".join(f"r.{k} = ${k}" for k in changes) + (", r.fact_embedding = vecf32($v)" if "fact" in changes else "")
    ctx.graph.query(f"MATCH ()-[r:RELATES_TO {{uuid:$u}}]->() SET {sets}", {"u": uuid, **changes, **({"v": vec} if "fact" in changes else {})})
    op = _record(ctx, "fact.edit", f"Editado el hecho {_label(cur)}" + (f" (relación → {changes['name']})" if "name" in changes else ""),
                 uuid=uuid, before={k: cur[k] for k in changes}, after=changes)
    return {"ok": True, "op": op.id, "summary": op.summary}


@router.post("/{uuid}/invalidate")
def invalidate(uuid: str, ctx: BrainCtx = Depends(curator_of_brain)):
    cur = _get(ctx, uuid)
    if cur["invalid_at"]:
        raise HTTPException(409, "el hecho ya está invalidado")
    now = datetime.now(timezone.utc).isoformat()
    ctx.graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() SET r.invalid_at = $n, r.expired_at = $n", {"u": uuid, "n": now})
    op = _record(ctx, "fact.invalidate", f"Invalidado el hecho {_label(cur)}", uuid=uuid, before={"invalid_at": cur["invalid_at"], "expired_at": cur["expired_at"]})
    return {"ok": True, "op": op.id, "summary": op.summary}


@router.post("/{uuid}/reactivate")
def reactivate(uuid: str, ctx: BrainCtx = Depends(curator_of_brain)):
    cur = _get(ctx, uuid)
    if not cur["invalid_at"]:
        raise HTTPException(409, "el hecho ya está vigente")
    ctx.graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() SET r.invalid_at = NULL, r.expired_at = NULL", {"u": uuid})
    op = _record(ctx, "fact.reactivate", f"Reactivado el hecho {_label(cur)}", uuid=uuid, before={"invalid_at": cur["invalid_at"], "expired_at": cur["expired_at"]})
    return {"ok": True, "op": op.id, "summary": op.summary}


@router.delete("/{uuid}")
def delete_fact(uuid: str, ctx: BrainCtx = Depends(curator_of_brain)):
    cur = _get(ctx, uuid)
    r = rows(ctx.graph.query("MATCH (a:Entity)-[r:RELATES_TO {uuid:$u}]->(b:Entity) RETURN properties(r) AS p, a.uuid AS a, b.uuid AS b", {"u": uuid}))[0]
    props = {k: v for k, v in r["p"].items() if k not in _HIDE and not is_shadow(k)}
    ctx.graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() DELETE r", {"u": uuid})
    ctx.graph.query("MATCH (e:Episodic) WHERE $u IN coalesce(e.entity_edges, []) SET e.entity_edges = [x IN e.entity_edges WHERE x <> $u]", {"u": uuid})
    op = _record(ctx, "fact.delete", f"Borrado el hecho {_label(cur)}", uuid=uuid, props=props, source=r["a"], target=r["b"])
    return {"ok": True, "op": op.id, "summary": op.summary}


def undo(ctx: BrainCtx, kind: str, d: dict) -> None:
    uuid = d["uuid"]
    if kind == "fact.delete":
        ctx.graph.query("MATCH (a:Entity {uuid:$a}), (b:Entity {uuid:$b}) CREATE (a)-[r:RELATES_TO]->(b) SET r = $p", {"a": d["source"], "b": d["target"], "p": d["props"]})
        _set_embedding(ctx, uuid, d["props"].get("fact") or "")
        ctx.graph.query("MATCH (e:Episodic) WHERE e.uuid IN $eps AND NOT $u IN coalesce(e.entity_edges, []) SET e.entity_edges = coalesce(e.entity_edges, []) + [$u]",
                        {"u": uuid, "eps": d["props"].get("episodes") or []})
    elif kind == "fact.edit":
        b = d["before"]
        sets = ", ".join(f"r.{k} = ${k}" for k in b)
        ctx.graph.query(f"MATCH ()-[r:RELATES_TO {{uuid:$u}}]->() SET {sets}", {"u": uuid, **b})
        if "fact" in b:
            _set_embedding(ctx, uuid, b["fact"])
    else:  # invalidate / reactivate
        ctx.graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() SET r.invalid_at = $i, r.expired_at = $e", {"u": uuid, "i": d["before"]["invalid_at"], "e": d["before"]["expired_at"]})
