"""Cuarentena de aportaciones: los colaboradores proponen, los curadores aprueban o rechazan.

Una aportación aprobada queda lista para ingerir (extracción con Graphiti); eso es el paso siguiente.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from . import deciders_admin, ingest, secretguard
from .deps import BrainCtx, audit, brain_access
from .i18n import language, tr
from .models import Proposal, User
from .roles import allows

router = APIRouter(prefix="/api/brains/{slug}/proposals")
contributor = brain_access("contributor")
curator = brain_access("curator")
STATUSES = {"pending", "approved", "rejected", "ingested", "failed"}


class ProposalIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=50000)
    source: str = Field("text", pattern="^(text|message|json)$")
    source_description: str = Field("", max_length=255)
    reference_time: datetime | None = None
    confidence: float | None = Field(None, ge=0, le=1)


class ReviewIn(BaseModel):
    note: str = Field("", max_length=2000)


def _out(p: Proposal, full: bool = False) -> dict:
    d = {"id": p.id, "name": p.name, "source": p.source, "source_description": p.source_description, "confidence": p.confidence,
         "status": p.status, "author": p.author.email or p.author.name, "created_at": p.created_at, "reviewed_at": p.reviewed_at,
         "review_note": p.review_note, "reference_time": p.reference_time, "review_kind": p.review_kind, "decision": p.decision,
         "ingest_error": p.ingest_error, "ingest_report": p.ingest_report, "episode_uuid": p.episode_uuid, "ingested_at": p.ingested_at,
         "secrets": secretguard.describe(p.secret_findings)}
    d["body"] = p.body if full else p.body[:300]
    return d


@router.post("", status_code=201)
def submit(body: ProposalIn, request: Request, bg: BackgroundTasks, ctx: BrainCtx = Depends(contributor)):
    """Colaborador: entra en cuarentena (pending). Curador o superior: aprobada directamente, queda en el registro."""
    return _out(create(ctx, request, bg, body))


def create(ctx: BrainCtx, request: Request, bg: BackgroundTasks, body: ProposalIn) -> Proposal:
    """Alta de una propuesta (también la usa `remember` del MCP). Antes de guardar pasa por el detector de secretos del brain (#116)."""
    try:
        name, in_name = secretguard.guard(ctx.brain, body.name)
        text, in_body = secretguard.guard(ctx.brain, body.body)
    except secretguard.Blocked:
        rules = sorted({r for t in (body.name, body.body) for r in _blocked_rules(ctx, t)})
        audit(ctx.db, ctx.user, "proposal.blocked", ctx.brain, reason="secrets", rules=rules)
        labels = secretguard.labels(language(request))
        raise HTTPException(422, tr("La propuesta contiene secretos ({{labels}}). Quítalos y guarda solo dónde están (por ejemplo, en qué gestor de contraseñas).",
                                    language(request), labels=", ".join(labels[r] for r in rules)))
    found = [{**f, "field": "name"} for f in in_name] + [{**f, "field": "body"} for f in in_body]
    direct = allows(ctx.role, "curator") and not secretguard.flagged(found)  # con algo marcado, ni el curador que la envía la aprueba sin mirarla
    tok = getattr(request.state, "token", None)
    p = Proposal(brain_id=ctx.brain.id, author_id=ctx.user.id, token_id=tok.id if tok else None, name=name[:255], body=text, source=body.source,
                 source_description=body.source_description, reference_time=body.reference_time, confidence=body.confidence,
                 status="approved" if direct else "pending", secret_findings=found or None)
    if direct:
        p.reviewer_id, p.reviewed_at, p.review_kind = ctx.user.id, datetime.now(timezone.utc), "direct"
    ctx.db.add(p); ctx.db.commit()
    audit(ctx.db, ctx.user, "proposal.submit", ctx.brain, id=p.id, status=p.status, name=secretguard.safe_name(p), **({"secrets": found} if found else {}))
    if direct and ingest.enabled():
        ingest.submit_ingest(p.id, ctx.brain.id, secretguard.safe_name(p), ctx.user.id)
    elif not direct:
        bg.add_task(deciders_admin.triage_proposal, p.id)  # sin decisor configurado no hace nada; con secretos marcados, tampoco
    return p


def _blocked_rules(ctx: BrainCtx, text: str) -> list[str]:
    try:
        secretguard.guard(ctx.brain, text)
    except secretguard.Blocked as e:
        return e.rules
    return []


_AUTHOR = func.coalesce(User.email, User.name)
_SORTS = {"name": Proposal.name, "author": _AUTHOR, "conf": Proposal.confidence, "at": Proposal.id}  # el id sigue el orden de envío


@router.get("")
def list_proposals(status: str | None = None, q: str = Query("", max_length=200), author: int | None = None, sort: str = "at", order: str = "desc",
                   limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), ctx: BrainCtx = Depends(contributor)):
    """Los curadores ven todas; un colaborador solo las suyas. Paginado en el servidor (#88): `total` cuenta lo que pasa los filtros
    y `authors` lista los autores visibles para el filtro de la columna."""
    if status and status not in STATUSES:
        raise HTTPException(400, "estado inválido")
    if sort not in _SORTS:
        raise HTTPException(400, "orden inválido")
    base = select(Proposal).join(User, User.id == Proposal.author_id).where(Proposal.brain_id == ctx.brain.id)
    if not allows(ctx.role, "curator"):
        base = base.where(Proposal.author_id == ctx.user.id)
    authors = ctx.db.execute(base.with_only_columns(User.id, _AUTHOR).distinct().order_by(_AUTHOR)).all()
    if status:
        base = base.where(Proposal.status == status)
    if author:
        base = base.where(Proposal.author_id == author)
    if q.strip():
        base = base.where(Proposal.name.ilike("%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"))
    total = ctx.db.scalar(select(func.count()).select_from(base.subquery()))
    key = _SORTS[sort].asc() if order == "asc" else _SORTS[sort].desc()
    rows = ctx.db.scalars(base.order_by(key.nulls_last(), Proposal.id.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "limit": limit, "offset": offset, "authors": [{"id": i, "name": n} for i, n in authors], "items": [_out(p) for p in rows]}


@router.get("/counts")
def counts(ctx: BrainCtx = Depends(contributor)):
    """Número de propuestas por estado (un colaborador solo cuenta las suyas)."""
    q = select(Proposal.status, func.count()).where(Proposal.brain_id == ctx.brain.id).group_by(Proposal.status)
    if not allows(ctx.role, "curator"):
        q = q.where(Proposal.author_id == ctx.user.id)
    out = {k: 0 for k in sorted(STATUSES)}
    out.update({st: n for st, n in ctx.db.execute(q)})
    out["all"] = sum(out.values())
    return out


def _get(ctx: BrainCtx, pid: int) -> Proposal:
    p = ctx.db.get(Proposal, pid)
    if not p or p.brain_id != ctx.brain.id:
        raise HTTPException(404, "propuesta no encontrada")
    return p


@router.get("/{pid}")
def get_proposal(pid: int, ctx: BrainCtx = Depends(contributor)):
    p = _get(ctx, pid)
    if p.author_id != ctx.user.id and not allows(ctx.role, "curator"):
        raise HTTPException(404, "propuesta no encontrada")
    return _out(p, full=True)


def _review(ctx: BrainCtx, pid: int, status: str, note: str) -> dict:
    p = _get(ctx, pid)
    if p.status != "pending":
        raise HTTPException(409, f"la propuesta ya está {p.status}")
    p.status, p.reviewer_id, p.reviewed_at, p.review_note, p.review_kind = status, ctx.user.id, datetime.now(timezone.utc), note, "human"
    ctx.db.commit()
    audit(ctx.db, ctx.user, f"proposal.{status}", ctx.brain, id=p.id, note=note)
    return _out(p)


@router.post("/{pid}/approve")
def approve(pid: int, body: ReviewIn, bg: BackgroundTasks, ctx: BrainCtx = Depends(curator)):
    out = _review(ctx, pid, "approved", body.note)
    if ingest.enabled():
        ingest.submit_ingest(pid, ctx.brain.id, secretguard.safe_name(_get(ctx, pid)), ctx.user.id)
    return out


@router.post("/{pid}/ingest")
def retry_ingest(pid: int, bg: BackgroundTasks, ctx: BrainCtx = Depends(curator)):
    """Lanza (o reintenta) la ingesta de una propuesta aprobada o fallida."""
    if not ingest.enabled():
        raise HTTPException(503, "ingesta no configurada (MIMIRSYNTH_LLM_BASE_URL y MIMIRSYNTH_LLM_MODEL)")
    p = _get(ctx, pid)
    if p.status not in ("approved", "failed"):
        raise HTTPException(409, f"la propuesta está {p.status}")
    return {"queued": True, "job": ingest.submit_ingest(pid, ctx.brain.id, secretguard.safe_name(p), ctx.user.id)}


@router.post("/{pid}/reject")
def reject(pid: int, body: ReviewIn, ctx: BrainCtx = Depends(curator)):
    return _review(ctx, pid, "rejected", body.note)
