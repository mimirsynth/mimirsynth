"""Shadow replay (#291, second part): the brain's sample of real recalls (replay.py) asked again with a **candidate configuration** (a
threshold, the trust weighting, the decay, the current-state card…) without changing anything for callers, and a report of what
would differ: per question, the items it would gain and lose, whether the order changes and whether it would come back empty; in all,
how many questions change, the share that would be empty and the share that would bring something marked as possibly outdated.

- **Bounded:** at most `sample` questions per run (the newest first, 100 by default, 500 at most) and RUNS_PER_HOUR runs per brain.
  Each question is one recall, one embedding. The runs are jobs (progress, cancellation), the last KEEP_RUNS are kept.
- **What it compares:** the kind and id of each item, as the sample stored them; never the memories' text.
- **Promote a question** (`POST /replay/samples/{id}/promote`): a curator who confirms what a real question should return turns it
  into a reference query with those expected texts, so it is checked again after every change.
- Brain administrators run and read it, as they are the ones who see the sample.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import jobs, ratelimit
from .deps import BrainCtx, admin_of_brain, audit
from .models import Brain, RecallSample, RefQuery, ReplayRun
from .store import _factory

log = logging.getLogger("mimirsynth.replayrun")
router = APIRouter(prefix="/api/brains/{slug}/replay")
KIND = "replay.run"
RUNS_PER_HOUR = 10
KEEP_RUNS = 20
CANDIDATE = ("min_similarity", "min_sim", "docs", "facts", "chunks", "trust", "decay", "state_card")


class CandidateIn(BaseModel):
    min_similarity: float | None = Field(None, ge=0, le=1)
    min_sim: float | None = Field(None, ge=0, le=1)
    docs: int | None = Field(None, ge=0, le=6)
    facts: int | None = Field(None, ge=0, le=30)
    chunks: int | None = Field(None, ge=0, le=15)
    trust: bool | None = None
    decay: bool | None = None
    state_card: bool | None = None


class RunIn(BaseModel):
    candidate: CandidateIn = Field(default_factory=CandidateIn)
    sample: int = Field(100, ge=1, le=500)


def _key(i: dict) -> tuple:
    return (i.get("kind"), str(i.get("id")))


def diff(before: list[dict], after: list[dict]) -> dict:
    """What changes between the items a recall returned and those the candidate returns, by kind and id."""
    b, a = [_key(i) for i in before or []], [_key(i) for i in after or []]
    gained, lost = [k for k in a if k not in b], [k for k in b if k not in a]
    common_b, common_a = [k for k in b if k in a], [k for k in a if k in b]
    return {"gained": [{"kind": k, "id": i} for k, i in gained], "lost": [{"kind": k, "id": i} for k, i in lost],
            "reordered": common_b != common_a, "empty_before": not b, "empty_after": not a,
            "changed": bool(gained or lost or common_b != common_a)}


def summarize(results: list[dict]) -> dict:
    ok = [r for r in results if not r.get("error")]
    n = len(ok)
    return {"questions": len(results), "errors": len(results) - n, "changed": sum(r["changed"] for r in ok),
            "gained": sum(len(r["gained"]) for r in ok), "lost": sum(len(r["lost"]) for r in ok),
            "empty_after": round(sum(r["empty_after"] for r in ok) / n, 4) if n else None,
            "empty_before": round(sum(r["empty_before"] for r in ok) / n, 4) if n else None,
            "outdated_after": round(sum(r["outdated"] > 0 for r in ok) / n, 4) if n else None}


@jobs.register(KIND, "Repetir recalls reales con otra configuración", limit=1)
def _job(ctx: "jobs.JobCtx", p: dict) -> dict:
    from .federation import sources_for
    from .health import outdated
    from .ratings import items_of
    from .recall import recall
    with _factory()() as db:
        run = db.get(ReplayRun, p["run_id"])
        if not run:
            return {}
        b = db.get(Brain, run.brain_id)
        bid, gname, cand, size = b.id, b.graph_name, dict(run.params or {}), run.size
        samples = [(s.id, s.query, dict(s.params or {}), list(s.items or [])) for s in
                   db.scalars(select(RecallSample).where(RecallSample.brain_id == bid).order_by(RecallSample.id.desc()).limit(size))]
        src = sources_for(db, b)
        run.status = "running"
        db.commit()
    results = []
    try:
        for n, (sid, query, params, before) in enumerate(samples):
            ctx.check()
            ctx.progress(n, len(samples))
            merged = {**params, **{k: v for k, v in cand.items() if v is not None}}
            try:
                out = recall(bid, gname, query, merged.get("facts", 8), merged.get("chunks", 4), merged.get("max_chars", 6000),
                             n_docs=merged.get("docs"), min_sim=merged.get("min_sim"), min_similarity=merged.get("min_similarity"),
                             trust=merged.get("trust"), decay=merged.get("decay"), state_card=merged.get("state_card"),
                             **({"sources": src} if src and merged.get("federated", True) else {}))
                results.append({"sample_id": sid, "query": query[:300], **diff(before, items_of(out)), "outdated": outdated(out)})
            except Exception as e:  # noqa: BLE001  (one question that fails does not stop the run)
                results.append({"sample_id": sid, "query": query[:300], "error": str(e)[:300]})
    except BaseException as e:
        with _factory()() as db:
            r = db.get(ReplayRun, p["run_id"])
            r.status, r.finished_at = "error", datetime.now(timezone.utc)
            r.error = "cancelada" if isinstance(e, jobs.Cancelled) else str(e)[:500]
            db.commit()
        raise
    summary = summarize(results)
    with _factory()() as db:
        r = db.get(ReplayRun, p["run_id"])
        r.status, r.summary, r.results, r.finished_at = "done", summary, results, datetime.now(timezone.utc)
        old = [x.id for x in db.scalars(select(ReplayRun).where(ReplayRun.brain_id == bid).order_by(ReplayRun.id.desc()).offset(KEEP_RUNS))]
        for oid in old:
            db.delete(db.get(ReplayRun, oid))
        db.commit()
    return summary


def _out(r: ReplayRun, full: bool = False) -> dict:
    out = {"id": r.id, "status": r.status, "params": r.params or {}, "size": r.size, "summary": r.summary, "error": r.error,
           "created_at": r.created_at, "finished_at": r.finished_at}
    if full:
        out["results"] = r.results or []
    return out


@router.post("/runs", status_code=202)
def start_run(body: RunIn, ctx: BrainCtx = Depends(admin_of_brain)):
    """Replays the newest `sample` questions of the brain's sample with the candidate settings, in a background job."""
    from sqlalchemy import func
    if not ctx.db.scalar(select(func.count()).select_from(RecallSample).where(RecallSample.brain_id == ctx.brain.id)):
        raise HTTPException(409, "el brain no tiene ninguna consulta guardada en su muestra")
    if not ratelimit.allow(f"replay:{ctx.brain.id}", RUNS_PER_HOUR, 3600):
        raise HTTPException(429, f"como mucho {RUNS_PER_HOUR} repeticiones por hora en cada brain")
    params = body.candidate.model_dump(exclude_none=True)
    r = ReplayRun(brain_id=ctx.brain.id, params=params, size=body.sample, created_by=ctx.user.id)
    ctx.db.add(r)
    ctx.db.commit()
    jobs.submit(KIND, ctx.brain.id, {"run_id": r.id}, "Repetir recalls reales con otra configuración", ctx.user.id, dedupe_key=f"{KIND}:{r.id}")
    audit(ctx.db, ctx.user, "replay.run", ctx.brain, run=r.id, params=params, sample=body.sample)
    return {"run": r.id}


@router.get("/runs")
def list_runs(ctx: BrainCtx = Depends(admin_of_brain)):
    rows = ctx.db.scalars(select(ReplayRun).where(ReplayRun.brain_id == ctx.brain.id).order_by(ReplayRun.id.desc()).limit(KEEP_RUNS))
    return {"items": [_out(r) for r in rows]}


@router.get("/runs/{rid}")
def get_run(rid: int, ctx: BrainCtx = Depends(admin_of_brain)):
    r = ctx.db.get(ReplayRun, rid)
    if not r or r.brain_id != ctx.brain.id:
        raise HTTPException(404, "ejecución no encontrada")
    return _out(r, full=True)


class PromoteIn(BaseModel):
    expect: list[str] = Field(min_length=1, max_length=50, description="what this question must bring, as a reference query's texts")
    note: str = Field("", max_length=2000)


@router.post("/samples/{sid}/promote", status_code=201)
def promote(sid: int, body: PromoteIn, ctx: BrainCtx = Depends(admin_of_brain)):
    """Turns a real question of the sample into a reference query with the expected texts a curator confirms."""
    from .refqueries import _clean
    s = ctx.db.get(RecallSample, sid)
    if not s or s.brain_id != ctx.brain.id:
        raise HTTPException(404, "consulta no encontrada en la muestra")
    q = RefQuery(brain_id=ctx.brain.id, query=s.query[:4000], expect=[{"text": _clean(ctx, t)[:500], "kind": "any"} for t in body.expect if t.strip()],
                 avoid=[], note=(body.note or f"de la muestra de recalls #{sid}")[:2000])
    ctx.db.add(q)
    ctx.db.commit()
    audit(ctx.db, ctx.user, "replay.promote", ctx.brain, sample=sid, refquery=q.id)
    return {"refquery": q.id}
