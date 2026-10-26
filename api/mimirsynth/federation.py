"""Federación entre brains: un brain concede a otro lectura acotada, revocable y auditada.

Reglas:
  · La concesión la crea un administrador del brain de ORIGEN (el que presta su conocimiento) hacia un brain de DESTINO donde también tiene acceso.
  · Solo lectura y sin transitividad: A→B y B→C no da a C acceso a A.
  · Alcance: `graph` (hechos y fragmentos de episodios), `docs` (documentos) o `both`.
  · En una consulta, los resultados del destino y de sus orígenes se fusionan con RRF y cada elemento prestado lleva su origen.
  · No se comparten embeddings, resúmenes de entidades ni nada que no sea el contenido consultado.
  · Revocar o caducar surte efecto en la siguiente consulta. Crear, cambiar y revocar queda en la auditoría."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .deps import BrainCtx, audit, brain_access, effective_role
from .models import Brain, BrainGrant, now
from .recall import Source

router = APIRouter(prefix="/api/brains/{slug}/grants")
reader = brain_access("reader")
admin = brain_access("admin")
SCOPES = ("graph", "docs", "both")
TOUCH_EVERY = timedelta(minutes=5)  # `last_used_at` se refresca como mucho cada tanto: no una escritura por consulta


def _aware(d: datetime | None) -> datetime | None:
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def _active(g: BrainGrant) -> bool:
    exp = _aware(g.expires_at)
    return exp is None or exp > now()


def sources_for(db: Session, brain: Brain) -> list[Source]:
    """Brains que han concedido lectura a `brain` y siguen vigentes (los caducados se ignoran)."""
    out, t = [], now()
    for g in db.scalars(select(BrainGrant).where(BrainGrant.target_brain_id == brain.id).order_by(BrainGrant.id)):
        if not _active(g):
            continue
        out.append(Source(brain_id=g.source.id, graph_name=g.source.graph_name, slug=g.source.slug, name=g.source.name, scope=g.scope))
        last = _aware(g.last_used_at)
        if last is None or t - last > TOUCH_EVERY:
            g.last_used_at = t
    db.commit()
    return out


def _out(g: BrainGrant) -> dict:
    return {"id": g.id, "scope": g.scope, "expires_at": g.expires_at, "active": _active(g), "created_at": g.created_at, "last_used_at": g.last_used_at,
            "source": {"slug": g.source.slug, "name": g.source.name}, "target": {"slug": g.target.slug, "name": g.target.name}}


@router.get("")
def list_grants(ctx: BrainCtx = Depends(reader)):
    """`received`: brains que prestan su conocimiento a este (los ve cualquier lector, porque aparecen como origen en las consultas).
    `given`: a quién presta este brain el suyo (solo administradores)."""
    q = select(BrainGrant)
    received = [_out(g) for g in ctx.db.scalars(q.where(BrainGrant.target_brain_id == ctx.brain.id).order_by(BrainGrant.id))]
    given = [_out(g) for g in ctx.db.scalars(q.where(BrainGrant.source_brain_id == ctx.brain.id).order_by(BrainGrant.id))] if ctx.role in ("admin", "owner") else []
    return {"received": received, "given": given}


class GrantIn(BaseModel):
    target: str  # slug del brain que recibe
    scope: str = "both"
    days: int | None = None  # vigencia en días; vacío = sin caducidad


def _expiry(days: int | None) -> datetime | None:
    if days is None:
        return None
    if not 1 <= days <= 3650:
        raise HTTPException(400, "la vigencia debe estar entre 1 y 3650 días")
    return now() + timedelta(days=days)


def _check_scope(scope: str) -> None:
    if scope not in SCOPES:
        raise HTTPException(400, f"alcance inválido (usa {', '.join(SCOPES)})")


@router.post("", status_code=201)
def create_grant(body: GrantIn, ctx: BrainCtx = Depends(admin)):
    _check_scope(body.scope)
    target = ctx.db.scalar(select(Brain).where(Brain.slug == body.target))
    if not target or effective_role(ctx.db, ctx.user, target) is None:  # no revelar brains ajenos; hay que tener acceso al destino
        raise HTTPException(404, "brain de destino no encontrado")
    if target.id == ctx.brain.id:
        raise HTTPException(400, "un brain no puede concederse lectura a sí mismo")
    if ctx.db.scalar(select(BrainGrant).where(BrainGrant.source_brain_id == ctx.brain.id, BrainGrant.target_brain_id == target.id)):
        raise HTTPException(409, "ya existe una concesión a ese brain: edítala o revócala")
    g = BrainGrant(source_brain_id=ctx.brain.id, target_brain_id=target.id, scope=body.scope, expires_at=_expiry(body.days), created_by=ctx.user.id)
    ctx.db.add(g); ctx.db.commit()
    audit(ctx.db, ctx.user, "grant.create", ctx.brain, target=target.slug, scope=g.scope, expires_at=g.expires_at.isoformat() if g.expires_at else None)
    return _out(g)


class GrantPatch(BaseModel):
    scope: str | None = None
    days: int | None = None  # nueva vigencia a partir de ahora
    no_expiry: bool = False


def _grant_of(ctx: BrainCtx, gid: int) -> BrainGrant:
    g = ctx.db.get(BrainGrant, gid)
    if not g or ctx.brain.id not in (g.source_brain_id, g.target_brain_id):
        raise HTTPException(404, "concesión no encontrada")
    return g


@router.patch("/{gid}")
def update_grant(gid: int, body: GrantPatch, ctx: BrainCtx = Depends(admin)):
    g = _grant_of(ctx, gid)
    if g.source_brain_id != ctx.brain.id:  # solo el que presta decide qué presta
        raise HTTPException(403, "solo el brain de origen puede cambiar la concesión")
    if body.scope is not None:
        _check_scope(body.scope); g.scope = body.scope
    if body.no_expiry:
        g.expires_at = None
    elif body.days is not None:
        g.expires_at = _expiry(body.days)
    ctx.db.commit()
    audit(ctx.db, ctx.user, "grant.update", ctx.brain, target=g.target.slug, scope=g.scope, expires_at=g.expires_at.isoformat() if g.expires_at else None)
    return _out(g)


@router.delete("/{gid}")
def revoke_grant(gid: int, ctx: BrainCtx = Depends(admin)):
    """Revoca el origen; el destino puede además renunciar a lo que se le presta."""
    g = _grant_of(ctx, gid)
    who = "source" if g.source_brain_id == ctx.brain.id else "target"
    detail = dict(source=g.source.slug, target=g.target.slug, scope=g.scope, by=who)
    ctx.db.delete(g); ctx.db.commit()
    audit(ctx.db, ctx.user, "grant.revoke", ctx.brain, **detail)
    return {"ok": True}
