"""Recall, índice de texto y tokens de API por brain."""
import asyncio
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import appsettings, index
from .config import settings
from .deps import SCOPES, BrainCtx, audit, aware, brain_access, hash_token, reader, token_allows, token_expired
from .i18n import language
from .models import ApiToken, Brain, now
from .recall import recall
from .roles import ROLES, rank
from .store import _factory

router = APIRouter(prefix="/api/brains/{slug}")
curator = brain_access("curator")


class RecallIn(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    facts: int = Field(8, ge=0, le=30)
    chunks: int = Field(4, ge=0, le=15)
    max_chars: int = Field(6000, ge=500, le=30000)
    docs: int | None = Field(None, ge=0, le=6, description="pasajes documentales máximos; 0 = sin documentos; vacío = el valor por defecto de la instancia")
    federated: bool = Field(True, description="incluir lo que otros brains prestan a este (federación); false = solo lo propio")


def docs_for(request: Request, body: "RecallIn") -> int | None:
    """Passages the recall may bring: none for a token without the `documents` scope, neither its own nor lent ones (#133)."""
    return body.docs if token_allows(getattr(request.state, "token", None), "documents") else 0


def federated_kwargs(ctx: BrainCtx, body: "RecallIn") -> dict:
    """Orígenes prestados a este brain; vacío (y sin argumento extra) si no hay concesiones o se pide solo lo propio."""
    from .federation import sources_for
    src = sources_for(ctx.db, ctx.brain) if body.federated else []
    return {"sources": src} if src else {}


@router.post("/recall")
def do_recall(body: RecallIn, request: Request, ctx: BrainCtx = Depends(reader)):
    try:
        out = recall(ctx.brain.id, ctx.brain.graph_name, body.query, body.facts, body.chunks, body.max_chars, n_docs=docs_for(request, body),
                     lang=language(request), **federated_kwargs(ctx, body))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"recall falló: {e}") from e
    from . import ratings
    return {**out, "recall_id": ratings.log(ctx, body.query, out)}  # to rate what it returned (#110)


@router.get("/index/status")
def index_status(ctx: BrainCtx = Depends(reader)):
    return index.status(ctx.brain.id)


@router.post("/index/sync")
def index_sync(ctx: BrainCtx = Depends(curator)):
    try:
        res = index.sync_brain(ctx.brain.id, ctx.brain.graph_name)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"sincronización falló: {e}") from e
    audit(ctx.db, ctx.user, "index.sync", ctx.brain, **res)
    return res


# ---- tokens de API (agentes / MCP) ----
TOKEN_MAX_ROLE = "curator"  # un token nunca administra


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = "reader"
    scopes: list[str] | None = Field(None, description="recall, documents, propose; empty: all of them")
    days: int | None = Field(None, ge=1, le=3650, description="days until it expires; empty: it never expires")


def _scopes(v: list[str] | None) -> list[str] | None:
    if v is None:
        return None
    if not v or set(v) - set(SCOPES):
        raise HTTPException(400, f"alcance de token inválido: elige entre {', '.join(SCOPES)}")
    return None if set(v) == set(SCOPES) else [x for x in SCOPES if x in v]  # every scope is the same as none listed


def _max_days(days: int | None) -> None:
    cap = appsettings.get("token_max_days")
    if cap and (days is None or days > cap):
        raise HTTPException(400, f"en esta instancia un token caduca como mucho a los {cap} días")


def _new_token(db, user_id: int, brain_id: int, name: str, role: str, scopes: list[str] | None, days: int | None) -> tuple[ApiToken, str]:
    raw = "mst_" + secrets.token_urlsafe(32)
    t = ApiToken(user_id=user_id, brain_id=brain_id, name=name, role=role, prefix=raw[:10], token_hash=hash_token(raw), scopes=scopes,
                 expires_at=now() + timedelta(days=days) if days else None)
    db.add(t); db.commit()
    return t, raw


def token_out(t: ApiToken) -> dict:
    """What a list of tokens shows: its scopes, when it expires, and whether a rotation replaced it (it works until its grace ends)."""
    return {"id": t.id, "name": t.name, "role": t.role, "prefix": t.prefix, "created_at": t.created_at, "last_used_at": t.last_used_at,
            "scopes": list(t.scopes) if t.scopes is not None else list(SCOPES), "all_scopes": t.scopes is None,
            "expires_at": aware(t.expires_at), "expired": token_expired(t), "replaced_by": t.replaced_by}


@router.post("/tokens", status_code=201)
def create_token(body: TokenIn, ctx: BrainCtx = Depends(reader)):
    if ctx.db is None or body.role not in ROLES or rank(body.role) > rank(TOKEN_MAX_ROLE):
        raise HTTPException(400, f"rol de token inválido (máximo {TOKEN_MAX_ROLE})")
    if rank(body.role) > rank(ctx.role):
        raise HTTPException(403, "no puedes crear un token con más rol que el tuyo")
    scopes = _scopes(body.scopes)
    _max_days(body.days)
    t, raw = _new_token(ctx.db, ctx.user.id, ctx.brain.id, body.name, body.role, scopes, body.days)
    audit(ctx.db, ctx.user, "token.create", ctx.brain, name=body.name, role=body.role, scopes=scopes, days=body.days)
    return {**token_out(t), "token": raw}  # el token solo se muestra ahora


@router.get("/tokens")
def list_tokens(ctx: BrainCtx = Depends(reader)):
    q = select(ApiToken).where(ApiToken.brain_id == ctx.brain.id, ApiToken.revoked.is_(False))
    if rank(ctx.role) < rank("admin"):
        q = q.where(ApiToken.user_id == ctx.user.id)
    return [{**token_out(t), "owner": t.user.email or t.user.name, "mine": t.user_id == ctx.user.id} for t in ctx.db.scalars(q.order_by(ApiToken.id.desc()))]


class RotateIn(BaseModel):
    grace_hours: int = Field(24, ge=0, le=168, description="hours the old token keeps working, so the agents that use it can be updated")


@router.post("/tokens/{token_id}/rotate", status_code=201)
def rotate_token(token_id: int, body: RotateIn, ctx: BrainCtx = Depends(reader)):
    """A new token with the same name, role, scopes and lifetime; the old one keeps working for the grace period and then expires.
    Only its owner rotates it: the new token is shown once, to whoever asks for it."""
    t = ctx.db.get(ApiToken, token_id)
    if not t or t.brain_id != ctx.brain.id or t.revoked or t.user_id != ctx.user.id:
        raise HTTPException(404, "token no encontrado")
    if t.replaced_by or token_expired(t):
        raise HTTPException(409, "este token ya se ha rotado o ha caducado: crea uno nuevo")
    if rank(t.role) > rank(ctx.role):
        raise HTTPException(403, "no puedes crear un token con más rol que el tuyo")
    days = max(1, round((aware(t.expires_at) - aware(t.created_at)).total_seconds() / 86400)) if t.expires_at else None
    cap = appsettings.get("token_max_days")
    if cap and (days is None or days > cap):  # the instance's maximum applies to the new one
        days = cap
    new, raw = _new_token(ctx.db, t.user_id, t.brain_id, t.name, t.role, t.scopes, days)
    grace_end = now() + timedelta(hours=body.grace_hours)
    t.replaced_by = new.id
    t.expires_at = min(aware(t.expires_at), grace_end) if t.expires_at else grace_end
    t.revoked = not body.grace_hours
    ctx.db.commit()
    audit(ctx.db, ctx.user, "token.rotate", ctx.brain, name=t.name, grace_hours=body.grace_hours, days=days)
    return {**token_out(new), "token": raw, "old_expires_at": aware(t.expires_at)}


@router.delete("/tokens/{token_id}")
def revoke_token(token_id: int, ctx: BrainCtx = Depends(reader)):
    t = ctx.db.get(ApiToken, token_id)
    if not t or t.brain_id != ctx.brain.id or (t.user_id != ctx.user.id and rank(ctx.role) < rank("admin")):
        raise HTTPException(404, "token no encontrado")
    t.revoked = True; ctx.db.commit()
    audit(ctx.db, ctx.user, "token.revoke", ctx.brain, name=t.name)
    return {"ok": True}


WARN_DAYS = 7  # how long before it expires a token is announced


def check_expiring() -> int:
    """Announces once each token that expires within WARN_DAYS (called daily by the notifications loop). A rotated token is not
    announced: its replacement is already there."""
    from . import notify
    limit, n = now() + timedelta(days=WARN_DAYS), 0
    with _factory()() as db:
        q = select(ApiToken, Brain).join(Brain, Brain.id == ApiToken.brain_id).where(
            ApiToken.revoked.is_(False), ApiToken.replaced_by.is_(None), ApiToken.expiry_warned_at.is_(None),
            ApiToken.expires_at.is_not(None), ApiToken.expires_at <= limit)
        for t, b in db.execute(q).all():
            if token_expired(t):
                continue
            day, owner = aware(t.expires_at).strftime("%Y-%m-%d"), t.user.email or t.user.name
            notify.emit("token.expiring", f"El token «{t.name}» de «{b.name}» caduca el {day}",
                        f"Token {t.prefix}… de {owner}. Rótalo en Administración → Acceso al brain → Tokens de API (o en Mi cuenta) "
                        "y actualiza el agente que lo usa; si ya no se usa, revócalo.", severity="info", brain_id=b.id, key=f"token:{t.id}")
            t.expiry_warned_at = now()
            n += 1
        db.commit()
    return n


# ---- sincronización periódica del índice ----
async def periodic_sync():
    if appsettings.get("index_sync_minutes") <= 0 or not index.enabled():
        return
    await asyncio.sleep(5)
    while True:
        try:
            with _factory()() as db:
                brains = [(b.id, b.graph_name) for b in db.scalars(select(Brain))]
            for bid, g in brains:
                await asyncio.to_thread(index.sync_brain, bid, g)
        except Exception:  # noqa: BLE001  (no tumbar el servidor por un fallo del embedder o del grafo)
            pass
        await asyncio.sleep(appsettings.get("index_sync_minutes") * 60)
