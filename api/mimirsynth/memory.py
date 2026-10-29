"""Recall, índice de texto y tokens de API por brain."""
import asyncio
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import appsettings, index
from .config import settings
from .deps import BrainCtx, audit, brain_access, hash_token, reader
from .i18n import language
from .models import ApiToken, Brain
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


def federated_kwargs(ctx: BrainCtx, body: "RecallIn") -> dict:
    """Orígenes prestados a este brain; vacío (y sin argumento extra) si no hay concesiones o se pide solo lo propio."""
    from .federation import sources_for
    src = sources_for(ctx.db, ctx.brain) if body.federated else []
    return {"sources": src} if src else {}


@router.post("/recall")
def do_recall(body: RecallIn, request: Request, ctx: BrainCtx = Depends(reader)):
    try:
        return recall(ctx.brain.id, ctx.brain.graph_name, body.query, body.facts, body.chunks, body.max_chars, n_docs=body.docs,
                      lang=language(request), **federated_kwargs(ctx, body))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"recall falló: {e}") from e


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


@router.post("/tokens", status_code=201)
def create_token(body: TokenIn, ctx: BrainCtx = Depends(reader)):
    if ctx.db is None or body.role not in ROLES or rank(body.role) > rank(TOKEN_MAX_ROLE):
        raise HTTPException(400, f"rol de token inválido (máximo {TOKEN_MAX_ROLE})")
    if rank(body.role) > rank(ctx.role):
        raise HTTPException(403, "no puedes crear un token con más rol que el tuyo")
    raw = "mst_" + secrets.token_urlsafe(32)
    t = ApiToken(user_id=ctx.user.id, brain_id=ctx.brain.id, name=body.name, role=body.role, prefix=raw[:10], token_hash=hash_token(raw))
    ctx.db.add(t); ctx.db.commit()
    audit(ctx.db, ctx.user, "token.create", ctx.brain, name=body.name, role=body.role)
    return {"id": t.id, "name": t.name, "role": t.role, "prefix": t.prefix, "token": raw}  # el token solo se muestra ahora


@router.get("/tokens")
def list_tokens(ctx: BrainCtx = Depends(reader)):
    q = select(ApiToken).where(ApiToken.brain_id == ctx.brain.id, ApiToken.revoked.is_(False))
    if rank(ctx.role) < rank("admin"):
        q = q.where(ApiToken.user_id == ctx.user.id)
    return [{"id": t.id, "name": t.name, "role": t.role, "prefix": t.prefix, "owner": t.user.email or t.user.name,
             "created_at": t.created_at, "last_used_at": t.last_used_at} for t in ctx.db.scalars(q.order_by(ApiToken.id.desc()))]


@router.delete("/tokens/{token_id}")
def revoke_token(token_id: int, ctx: BrainCtx = Depends(reader)):
    t = ctx.db.get(ApiToken, token_id)
    if not t or t.brain_id != ctx.brain.id or (t.user_id != ctx.user.id and rank(ctx.role) < rank("admin")):
        raise HTTPException(404, "token no encontrado")
    t.revoked = True; ctx.db.commit()
    audit(ctx.db, ctx.user, "token.revoke", ctx.brain, name=t.name)
    return {"ok": True}


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
