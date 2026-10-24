"""Registro de alias del vocabulario (no destructivo): variantes de relación -> nombre canónico por brain.
Se aplica al leer (hechos, grafo, recall, vocabulario); los datos del grafo no se tocan."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from .deps import BrainCtx, admin_of_brain, audit, reader
from .models import VocabAlias

router = APIRouter(prefix="/api/brains/{slug}/vocab")


def canon_rel(name: str | None) -> str:
    """Normalización sintáctica de relaciones: RelatesTo / RELATES_TO / relates-to -> RELATES_TO."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", (name or "").strip())
    return re.sub(r"[\s\-]+", "_", s).upper()


def alias_map(db, brain_id: int) -> dict[str, str]:
    """alias normalizado -> canónico, para relaciones del brain."""
    return {a.alias: a.canonical for a in db.scalars(select(VocabAlias).where(VocabAlias.brain_id == brain_id, VocabAlias.kind == "relation"))}


def resolve(name: str | None, amap: dict[str, str] | None = None) -> str:
    c = canon_rel(name)
    seen = set()
    while amap and c in amap and c not in seen:  # sigue cadenas A->B->C sin ciclos
        seen.add(c)
        c = amap[c]
    return c


class AliasIn(BaseModel):
    alias: str = Field(min_length=1, max_length=200)
    canonical: str = Field(min_length=1, max_length=200)


def _out(a: VocabAlias) -> dict:
    return {"id": a.id, "alias": a.alias, "canonical": a.canonical, "created_at": a.created_at}


@router.get("/aliases")
def list_aliases(ctx: BrainCtx = Depends(reader)):
    items = ctx.db.scalars(select(VocabAlias).where(VocabAlias.brain_id == ctx.brain.id, VocabAlias.kind == "relation").order_by(VocabAlias.canonical, VocabAlias.alias))
    return [_out(a) for a in items]


@router.post("/aliases", status_code=201)
def add_alias(body: AliasIn, ctx: BrainCtx = Depends(admin_of_brain)):
    alias, canonical = canon_rel(body.alias), canon_rel(body.canonical)
    if not alias or not canonical:
        raise HTTPException(400, "alias y canónico no pueden estar vacíos")
    if alias == canonical:
        raise HTTPException(400, "el alias coincide con el canónico")
    amap = alias_map(ctx.db, ctx.brain.id)
    if resolve(canonical, amap) == alias:
        raise HTTPException(409, "crearía un ciclo de alias")
    if alias in amap:
        raise HTTPException(409, f"{alias} ya es alias de {amap[alias]}")
    a = VocabAlias(brain_id=ctx.brain.id, kind="relation", alias=alias, canonical=canonical, created_by=ctx.user.id)
    ctx.db.add(a)
    ctx.db.commit()
    audit(ctx.db, ctx.user, "vocab.alias.add", ctx.brain, alias=alias, canonical=canonical)
    return _out(a)


@router.delete("/aliases/{aid}", status_code=204)
def delete_alias(aid: int, ctx: BrainCtx = Depends(admin_of_brain)):
    a = ctx.db.get(VocabAlias, aid)
    if not a or a.brain_id != ctx.brain.id:
        raise HTTPException(404, "alias no encontrado")
    detail = {"alias": a.alias, "canonical": a.canonical}
    ctx.db.delete(a)
    ctx.db.commit()
    audit(ctx.db, ctx.user, "vocab.alias.delete", ctx.brain, **detail)
