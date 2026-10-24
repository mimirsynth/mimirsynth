"""API de la cola de trabajos de un brain: listado, detalle, cancelar y reintentar."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from . import jobs
from .deps import BrainCtx, audit, curator_of_brain, reader
from .models import Job, User

router = APIRouter(prefix="/api/brains/{slug}/jobs")


def _get(ctx: BrainCtx, jid: int) -> Job:
    j = ctx.db.get(Job, jid)
    if not j or j.brain_id != ctx.brain.id:
        raise HTTPException(404, "trabajo no encontrado")
    return j


def _name(ctx: BrainCtx, uid: int | None) -> str:
    u = ctx.db.get(User, uid) if uid else None
    return (u.display_name or u.name) if u else ""


@router.get("")
def list_jobs(status: str = "", kind: str = "", q: str = Query("", max_length=200), order: str = "desc", limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), ctx: BrainCtx = Depends(reader)):
    base = select(Job).where(Job.brain_id == ctx.brain.id)
    counts = dict(ctx.db.execute(select(Job.status, func.count()).where(Job.brain_id == ctx.brain.id).group_by(Job.status)).all())
    kinds = sorted({k for (k,) in ctx.db.execute(select(Job.kind).where(Job.brain_id == ctx.brain.id).distinct())})
    if status:
        base = base.where(Job.status.in_([s for s in status.split(",") if s]))
    if kind:
        base = base.where(Job.kind == kind)
    if q.strip():
        base = base.where(Job.title.ilike("%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"))
    total = ctx.db.scalar(select(func.count()).select_from(base.subquery()))
    rows = ctx.db.scalars(base.order_by(Job.id.asc() if order == "asc" else Job.id.desc()).limit(limit).offset(offset)).all()
    names = {u.id: (u.display_name or u.name) for u in ctx.db.scalars(select(User).where(User.id.in_({r.created_by for r in rows if r.created_by})))} if rows else {}
    return {"total": total, "limit": limit, "offset": offset, "counts": counts, "kinds": [{"kind": k, "label": jobs.label_of(k)} for k in kinds], "items": [jobs.out(r, user_name=names.get(r.created_by, "")) for r in rows]}


@router.get("/summary")
def summary(ctx: BrainCtx = Depends(reader)):
    c = dict(ctx.db.execute(select(Job.status, func.count()).where(Job.brain_id == ctx.brain.id, Job.status.in_(("queued", "running"))).group_by(Job.status)).all())
    return {"active": sum(c.values()), "running": c.get("running", 0), "queued": c.get("queued", 0)}


@router.get("/{jid:int}")
def detail(jid: int, ctx: BrainCtx = Depends(reader)):
    j = _get(ctx, jid)
    return jobs.out(j, detail=True, user_name=_name(ctx, j.created_by))


@router.post("/{jid:int}/cancel")
def cancel(jid: int, ctx: BrainCtx = Depends(curator_of_brain)):
    _get(ctx, jid)
    res = jobs.cancel(jid)
    audit(ctx.db, ctx.user, "job.cancel", ctx.brain, id=jid, result=res)
    return {"result": res}


@router.post("/{jid:int}/retry", status_code=201)
def retry(jid: int, ctx: BrainCtx = Depends(curator_of_brain)):
    _get(ctx, jid)
    try:
        new = jobs.retry(jid, ctx.user.id)
    except ValueError as e:
        raise HTTPException(409, str(e))
    audit(ctx.db, ctx.user, "job.retry", ctx.brain, id=jid, new=new)
    return {"id": new}
