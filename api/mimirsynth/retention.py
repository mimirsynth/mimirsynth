"""Retention periods per brain (#137): what is no longer useful after a while is purged by a daily job, with a summary.

- **Rejected proposals:** their text goes (name, body, source, review note, the decider's reasoning, the secret findings and the
  correction's detail); the row stays, with its status, authors and dates, and `purged_at`.
- **Finished jobs** of the brain (done, failed or cancelled) and their detail.

Each brain can set its own period for each, or use the instance's (`retention_rejected_days`, `retention_jobs_days`); 0 means no
period. By default there is none, so nothing changes until someone sets one. Only the brain's owner (or the instance administrator)
changes them, and every change is audited. The audit log is never purged from here, and neither are the episodes (#134).
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update

from . import appsettings, jobs
from .deps import BrainCtx, audit, owner_of_brain
from .models import Brain, Job, Proposal
from .store import _factory

KIND = "retention.purge"
KEYS = {"rejected_days": "retention_rejected_days", "jobs_days": "retention_jobs_days"}  # brain's key -> instance setting
MAX_DAYS = 3650

router = APIRouter(prefix="/api/brains/{slug}/retention")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def defaults() -> dict:
    return {k: int(appsettings.get(s)) for k, s in KEYS.items()}


def effective(brain: Brain) -> dict:
    """The period that applies to each kind of data: the brain's own, or the instance's when the brain has none (0: no period)."""
    own, inst = brain.retention or {}, defaults()
    return {k: own[k] if isinstance(own.get(k), int) else inst[k] for k in KEYS}


def purge(brain_id: int, now: datetime | None = None) -> dict:
    """Applies the brain's periods and returns what was purged."""
    now = now or _now()
    with _factory()() as db:
        b = db.get(Brain, brain_id)
        if not b:
            return {}
        days = effective(b)
        out = {"proposals": 0, "jobs": 0, **days}
        if days["rejected_days"]:
            cut = now - timedelta(days=days["rejected_days"])
            r = db.execute(update(Proposal).where(Proposal.brain_id == b.id, Proposal.status == "rejected", Proposal.purged_at.is_(None),
                                                  Proposal.reviewed_at.is_not(None), Proposal.reviewed_at < cut)
                           .values(name="", body="", source_description="", review_note="", decision=None, secret_findings=None,
                                   correction=None, purged_at=now))
            out["proposals"] = r.rowcount or 0
        if days["jobs_days"]:
            cut = now - timedelta(days=days["jobs_days"])
            r = db.execute(delete(Job).where(Job.brain_id == b.id, Job.status.in_(("done", "failed", "cancelled")),
                                             Job.finished_at.is_not(None), Job.finished_at < cut))
            out["jobs"] = r.rowcount or 0
        db.commit()
    return out


@jobs.register(KIND, "Retención: purgar lo que ha caducado", limit=1)
def _run(job: jobs.JobCtx, params: dict) -> dict:
    out = purge(job.brain_id)
    job.progress(1, 1, f"propuestas: {out.get('proposals', 0)}, trabajos: {out.get('jobs', 0)}")
    return out


def run_all() -> list[int]:
    """A purge job for each brain with some period (called daily by the notifications loop)."""
    with _factory()() as db:
        brains = [b.id for b in db.scalars(select(Brain)) if any(effective(b).values())]
    return [jobs.submit(KIND, b, {}, "Retención: purgar lo que ha caducado", dedupe_key=f"{KIND}:{b}") for b in brains]


class RetentionIn(BaseModel):
    rejected_days: int | None = Field(None, ge=0, le=MAX_DAYS, description="days a rejected proposal keeps its text; empty: the instance's; 0: forever")
    jobs_days: int | None = Field(None, ge=0, le=MAX_DAYS, description="days a finished job is kept; empty: the instance's; 0: forever")


def _out(ctx: BrainCtx) -> dict:
    last = ctx.db.scalar(select(Job).where(Job.brain_id == ctx.brain.id, Job.kind == KIND).order_by(Job.id.desc()).limit(1))
    own = ctx.brain.retention or {}
    return {**{k: own.get(k) for k in KEYS}, "defaults": defaults(), "effective": effective(ctx.brain),
            "last_run": {"status": last.status, "finished_at": last.finished_at, "result": last.result, "error": last.error} if last else None}


@router.get("")
def get_retention(ctx: BrainCtx = Depends(owner_of_brain)):
    return _out(ctx)


@router.put("")
def set_retention(body: RetentionIn, ctx: BrainCtx = Depends(owner_of_brain)):
    before = {k: (ctx.brain.retention or {}).get(k) for k in KEYS}
    after = {k: getattr(body, k) for k in KEYS}
    if before != after:
        ctx.brain.retention = {k: v for k, v in after.items() if v is not None} or None
        ctx.db.commit()
        audit(ctx.db, ctx.user, "brain.retention", ctx.brain, **{k: {"from": before[k], "to": after[k]} for k in KEYS if before[k] != after[k]})
    return _out(ctx)


@router.post("/run", status_code=202)
def run_now(ctx: BrainCtx = Depends(owner_of_brain)):
    """Applies the periods now instead of waiting for the daily run."""
    if not any(effective(ctx.brain).values()):
        raise HTTPException(409, "este brain no tiene ningún plazo de retención: no hay nada que purgar")
    return {"id": jobs.submit(KIND, ctx.brain.id, {}, "Retención: purgar lo que ha caducado", ctx.user.id, dedupe_key=f"{KIND}:{ctx.brain.id}")}
