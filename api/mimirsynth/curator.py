"""Scheduled curator (#300, first part): passes over a brain's graph that turn what they find into **proposals in quarantine**, each with
its evidence, so curation stops depending on someone opening each screen. The curator never writes to the graph: a person approves
each proposal (as a correction, one at a time), and only then the change is applied, undoable from the vocabulary history.

- **Passes.** This part brings the **contradiction** pass: in the relations marked functional, the possible contradictions whose
  suggestion is clear (`conflicts.find`: a strictly newer validity date, all dated, a relation that does not look multi-valued) become
  a proposal that keeps the newest value and invalidates the others, with the group as evidence. Groups a curator marked «not a
  contradiction», unclear ones and ones that already have a pending proposal are left out. Noise, redundancy and obsolescence come
  next (#300, #297, #293).
- **Off by default, per brain and per pass** (`PUT /curator/settings`, brain administrators). Once a day, from the notification loop,
  for each enabled brain; the day is the run's key, as for the memory health.
- **A sample before a batch.** A pass that would propose more than `batch` changes (5 by default) does not propose them: the run
  waits with a sample of what it would change **and what it keeps**, and a curator confirms it (`POST /curator/runs/{id}/confirm`)
  or discards it. When a service is decommissioned dozens of facts can go at once, and only a person tells «still useful» from «now
  stale» (reviewer, #300).
- **Preview.** `POST /curator/preview` runs a pass read-only and says what it would propose, with the pass's **precision** so far:
  the share of its proposals that curators approved (`category`: `curator.contradictions`).
- **Cost.** These passes read the graph, with no AI calls.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from . import jobs
from .deps import BrainCtx, admin_of_brain, audit, brain_access
from .models import Brain, CuratorRun, Job, Proposal, User
from .store import _factory

log = logging.getLogger("mimirsynth.curator")
router = APIRouter(prefix="/api/brains/{slug}/curator")
curator = brain_access("curator")
KIND = "curator.run"
PASSES = ("contradictions",)
DEFAULT = {"enabled": False, "passes": {"contradictions": True}, "batch": 5}
MAX_FINDINGS = 200   # per run: what is past it waits for the next one
SAMPLE = 10


def _today() -> date:
    return datetime.now(timezone.utc).date()


def config(brain: Brain) -> dict:
    c = {**DEFAULT, **(brain.curator or {})}
    return {**c, "passes": {**DEFAULT["passes"], **(c.get("passes") or {})}}


def category(pass_: str) -> str:
    return f"curator.{pass_}"


# --- passes -----------------------------------------------------------------------------------

def _pending_targets(db, brain_id: int) -> set[str]:
    """Facts a pending proposal already asks to replace: not proposed twice."""
    out = set()
    for claims in db.scalars(select(Proposal.claims).where(Proposal.brain_id == brain_id, Proposal.status == "pending", Proposal.claims.is_not(None))):
        out |= {c.get("supersedes") for c in claims or [] if c.get("supersedes")}
    return out


def contradictions(brain_id: int) -> list[dict]:
    """Findings of the contradiction pass: per clear group, the fact kept and the ones it replaces."""
    from .conflicts import _brain_functional, _dismissals, scan
    from .db import graph
    from .vocab import alias_map
    with _factory()() as db:
        b = db.get(Brain, brain_id)
        functional, amap, dismissed, gname = _brain_functional(db, brain_id), alias_map(db, brain_id), _dismissals(db, brain_id), b.graph_name
        busy = _pending_targets(db, brain_id)
    if not functional:
        return []
    out = []
    for g in scan(graph(gname), amap, functional, dismissed=dismissed)["groups"]:
        s = g["suggestion"]
        if not s["clear"] or busy & set(s["invalidate"]):
            continue
        keep = next(f for f in g["facts"] if f["uuid"] == s["keep"])
        drop = [f for f in g["facts"] if f["uuid"] in s["invalidate"]]
        out.append({"pass": "contradictions", "subject": g["source"], "relation": g["relation"], "keep": keep, "replace": drop,
                    "why": "newer validity date in a functional relation"})
    return out[:MAX_FINDINGS]


FINDERS = {"contradictions": contradictions}


def precision(db, brain_id: int, pass_: str) -> dict:
    """How curators decided this pass's proposals so far: approved / (approved + rejected)."""
    rows = dict(db.execute(select(Proposal.status, func.count()).where(Proposal.brain_id == brain_id, Proposal.category == category(pass_))
                           .group_by(Proposal.status)).all())
    approved = sum(rows.get(s, 0) for s in ("approved", "ingested", "failed"))
    rejected = rows.get("rejected", 0)
    return {"approved": approved, "rejected": rejected, "pending": rows.get("pending", 0),
            "precision": round(approved / (approved + rejected), 3) if approved + rejected else None}


# --- proposing ------------------------------------------------------------------------------

def _author(db, brain: Brain) -> User | None:
    """Who the curator's proposals are written for: the administrator who turned it on, else the brain's creator."""
    uid = (brain.curator or {}).get("by") or brain.created_by
    return db.get(User, uid) if uid else None


def propose(brain_id: int, findings: list[dict]) -> list[int]:
    """One proposal per finding, in quarantine, with its claims checked again against the graph (what changed since is skipped)."""
    from . import claims as claims_mod
    from .conflicts import _brain_functional
    from .db import graph
    from .vocab import alias_map
    ids = []
    with _factory()() as db:
        b = db.get(Brain, brain_id)
        author, g = _author(db, b), graph(b.graph_name)
        amap, functional = alias_map(db, brain_id), _brain_functional(db, brain_id)
        busy = _pending_targets(db, brain_id)
        if not author:
            raise RuntimeError("the brain has nobody to write the curator's proposals for")
        for f in findings:
            if busy & {x["uuid"] for x in f["replace"]}:
                continue
            raw = [{"subject": f["subject"], "relation": f["relation"], "value": f["keep"]["target"], "valid_from": f["keep"].get("valid_at"),
                    "supersedes": x["uuid"]} for x in f["replace"]]
            try:
                checked = claims_mod.check(g, raw, amap, functional)
            except claims_mod.ClaimError:   # a fact stopped being current since the pass read it
                continue
            name = f"Curador: «{f['subject']}» {f['relation']} → {f['keep']['target']}"[:255]
            p = Proposal(brain_id=brain_id, author_id=author.id, name=name, body="", source="text", status="pending", kind="memory",
                         source_description=f"curator: {f['pass']}", category=category(f["pass"]), claims=checked,
                         related_verdict="new", decision={"curator": {"pass": f["pass"], "why": f["why"], "keep": f["keep"]}})
            db.add(p)
            db.commit()
            busy |= {x["uuid"] for x in f["replace"]}
            ids.append(p.id)
            audit(db, None, "proposal.submit", b, id=p.id, status="pending", by="curator", category=p.category)
    return ids


# --- runs -------------------------------------------------------------------------------------

def _alive(db, job_id: int | None) -> bool:
    j = db.get(Job, job_id) if job_id else None
    return bool(j) and j.status in ("queued", "running")


def start(brain_id: int, day: date, reason: str = "daily", user_id: int | None = None) -> int | None:
    with _factory()() as db:
        r = db.scalar(select(CuratorRun).where(CuratorRun.brain_id == brain_id, CuratorRun.day == day))
        if r and (r.status in ("waiting",) or (r.status in ("queued", "running") and _alive(db, r.job_id))):
            return None
        if r is None:
            r = CuratorRun(brain_id=brain_id, day=day)
            db.add(r)
        r.status, r.reason, r.error, r.findings, r.proposals = "queued", reason, "", None, None
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return None
        rid = r.id
    jid = jobs.submit(KIND, brain_id, {"run_id": rid}, "Curador programado", user_id, dedupe_key=f"{KIND}:{brain_id}")
    with _factory()() as db:
        db.get(CuratorRun, rid).job_id = jid
        db.commit()
    return rid


def due(today: date | None = None) -> list[int]:
    """The brains with the curator on and no run today. Called every few minutes."""
    today = today or _today()
    with _factory()() as db:
        on = [b.id for b in db.scalars(select(Brain).where(Brain.curator.is_not(None))) if config(b)["enabled"]]
        runs = {r.brain_id: r for r in db.scalars(select(CuratorRun).where(CuratorRun.day == today))}
        todo = [b for b in on if b not in runs or (runs[b].status in ("queued", "running") and not _alive(db, runs[b].job_id))]
    return [rid for b in todo if (rid := start(b, today)) is not None]


@jobs.register(KIND, "Curador programado", limit=1)
def _job(ctx: "jobs.JobCtx", p: dict) -> dict:
    with _factory()() as db:
        r = db.get(CuratorRun, p["run_id"])
        if not r:
            return {}
        b = db.get(Brain, r.brain_id)
        cfg, bid = config(b), b.id
        r.status = "running"
        db.commit()
    try:
        found, made, waiting = {}, [], False
        for name in PASSES:
            if not cfg["passes"].get(name):
                continue
            ctx.check()
            ctx.progress(0, 0, name)
            fs = FINDERS[name](bid)
            found[name] = fs
            if len(fs) > cfg["batch"]:
                waiting = True   # many changes at once: a person looks at a sample first
            else:
                made += propose(bid, fs)
    except BaseException as e:
        with _factory()() as db:
            r = db.get(CuratorRun, p["run_id"])
            r.status, r.finished_at = "error", datetime.now(timezone.utc)
            r.error = "cancelada" if isinstance(e, jobs.Cancelled) else str(e)[:500]
            db.commit()
        raise
    with _factory()() as db:
        r = db.get(CuratorRun, p["run_id"])
        r.findings, r.proposals, r.finished_at = found, made, datetime.now(timezone.utc)
        r.status = "waiting" if waiting else "done"
        db.commit()
    return {"findings": {k: len(v) for k, v in found.items()}, "proposals": len(made), "waiting": waiting}


# --- API --------------------------------------------------------------------------------------

class SettingsIn(BaseModel):
    enabled: bool
    passes: dict[str, bool] = Field(default_factory=dict)
    batch: int = Field(DEFAULT["batch"], ge=1, le=100)


def _run_out(db, r: CuratorRun, full: bool = False) -> dict:
    found = r.findings or {}
    out = {"id": r.id, "day": r.day.isoformat(), "status": r.status, "reason": r.reason, "error": r.error, "created_at": r.created_at,
           "finished_at": r.finished_at, "findings": {k: len(v) for k, v in found.items()}, "proposals": r.proposals or []}
    if full or r.status == "waiting":
        out["sample"] = {k: v[:SAMPLE] for k, v in found.items()}
    return out


@router.get("/settings")
def get_settings(ctx: BrainCtx = Depends(curator)):
    return {**config(ctx.brain), "precision": {p: precision(ctx.db, ctx.brain.id, p) for p in PASSES}}


@router.put("/settings")
def set_settings(body: SettingsIn, ctx: BrainCtx = Depends(admin_of_brain)):
    unknown = set(body.passes) - set(PASSES)
    if unknown:
        raise HTTPException(422, f"pasadas desconocidas: {', '.join(sorted(unknown))}")
    ctx.brain.curator = {"enabled": body.enabled, "passes": {**DEFAULT["passes"], **body.passes}, "batch": body.batch, "by": ctx.user.id}
    ctx.db.commit()
    audit(ctx.db, ctx.user, "curator.settings", ctx.brain, enabled=body.enabled, passes=body.passes, batch=body.batch)
    return get_settings(ctx)


@router.post("/preview")
def preview(pass_: str = Query("contradictions", alias="pass"), ctx: BrainCtx = Depends(curator)):
    """What a pass would propose now, read-only, with its precision so far."""
    if pass_ not in PASSES:
        raise HTTPException(422, "pasada desconocida")
    fs = FINDERS[pass_](ctx.brain.id)
    return {"pass": pass_, "count": len(fs), "findings": fs[:SAMPLE * 5], "batch": config(ctx.brain)["batch"],
            "precision": precision(ctx.db, ctx.brain.id, pass_)}


@router.get("/runs")
def list_runs(days: int = Query(30, ge=1, le=365), ctx: BrainCtx = Depends(curator)):
    rows = ctx.db.scalars(select(CuratorRun).where(CuratorRun.brain_id == ctx.brain.id, CuratorRun.day >= _today() - timedelta(days=days))
                          .order_by(CuratorRun.day.desc()))
    return {"items": [_run_out(ctx.db, r) for r in rows]}


@router.post("/run", status_code=202)
def run_now(ctx: BrainCtx = Depends(curator)):
    rid = start(ctx.brain.id, _today(), "manual", ctx.user.id)
    if rid is None:
        raise HTTPException(409, "el curador ya está en marcha o espera una confirmación")
    audit(ctx.db, ctx.user, "curator.run", ctx.brain, run=rid)
    return {"run": rid}


def _waiting(ctx: BrainCtx, rid: int) -> CuratorRun:
    r = ctx.db.get(CuratorRun, rid)
    if not r or r.brain_id != ctx.brain.id:
        raise HTTPException(404, "ejecución no encontrada")
    if r.status != "waiting":
        raise HTTPException(409, "esa ejecución no espera ninguna confirmación")
    return r


@router.post("/runs/{rid}/confirm")
def confirm(rid: int, ctx: BrainCtx = Depends(curator)):
    """A curator looked at the sample: every finding of the run becomes a proposal (each one is still decided on its own)."""
    r = _waiting(ctx, rid)
    made = []
    for fs in (r.findings or {}).values():
        made += propose(ctx.brain.id, fs)
    ctx.db.refresh(r)
    r.status, r.proposals = "done", [*(r.proposals or []), *made]
    ctx.db.commit()
    audit(ctx.db, ctx.user, "curator.confirm", ctx.brain, run=rid, proposals=len(made))
    return _run_out(ctx.db, r)


@router.post("/runs/{rid}/discard")
def discard(rid: int, ctx: BrainCtx = Depends(curator)):
    r = _waiting(ctx, rid)
    r.status = "discarded"
    ctx.db.commit()
    audit(ctx.db, ctx.user, "curator.discard", ctx.brain, run=rid)
    return _run_out(ctx.db, r)
