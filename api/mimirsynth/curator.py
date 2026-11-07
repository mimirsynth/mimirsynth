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
import re
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
PASSES = ("contradictions", "redundancy", "obsolescence", "noise")
DEFAULT = {"enabled": False, "passes": {"contradictions": True, "redundancy": False, "obsolescence": False, "noise": False}, "batch": 5}
MAX_REDUNDANT = 3000   # candidate facts whose embeddings the redundancy pass reads per run (the most recent first)
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


_RICH = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.invalid_at IS NULL AND r.expired_at IS NULL "
         "RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, r.valid_at AS valid_at, r.created_at AS created_at, a.name AS source, "
         "a.uuid AS source_uuid, b.name AS target, b.uuid AS target_uuid ORDER BY coalesce(r.valid_at, r.created_at) DESC, r.uuid LIMIT $n")


def redundancy(brain_id: int) -> list[dict]:
    """Findings of the redundancy pass (#297's merge): current facts between the same two entities that say the same thing (the same
    text, or close embeddings with the same numbers and identifiers, as the memory health counts them). The newest one is kept and the
    others are proposed for invalidation, pointing to it."""
    from . import health
    from .db import graph, rows
    with _factory()() as db:
        b = db.get(Brain, brain_id)
        gname, busy = b.graph_name, _pending_targets(db, brain_id)
    g = graph(gname)
    groups, n, out = [], 0, []
    for grp in health._groups(rows(g.query(_RICH, {"n": health.MAX_FACTS}))):
        if n + len(grp) > MAX_REDUNDANT and groups:
            break
        groups.append(grp)
        n += len(grp)
    uuids = [f["uuid"] for grp in groups for f in grp]
    vectors = {}
    for i in range(0, len(uuids), 500):
        for r in rows(g.query(health._VECTORS, {"u": uuids[i:i + 500]})):
            vectors[r["uuid"]] = r["e"]
    for grp in groups:
        for c in health.clusters([{**f, "embedding": vectors.get(f["uuid"])} for f in grp]):
            c = sorted(c, key=lambda f: (str(f.get("valid_at") or f.get("created_at") or ""), f["uuid"]), reverse=True)
            keep, drop = c[0], [f for f in c[1:] if f["uuid"] not in busy]
            if not drop:
                continue
            short = lambda f: {k: f.get(k) for k in ("uuid", "fact", "target", "valid_at")}  # noqa: E731
            out.append({"pass": "redundancy", "subject": keep["source"], "relation": keep["name"], "keep": short(keep),
                        "replace": [short(f) for f in drop], "why": "says the same as a newer current fact between the same entities"})
            if len(out) >= MAX_FINDINGS:
                return out
    return out


def obsolescence(brain_id: int) -> list[dict]:
    """Findings of the obsolescence pass: current facts past their relation's shelf life (as Content quality → To review lists them, the
    longest overdue first), proposed for invalidation one by one. Confirming one in To review, or rejecting its proposal, keeps it."""
    from . import shelflife
    with _factory()() as db:
        b = db.get(Brain, brain_id)
        busy = _pending_targets(db, brain_id)
        items = shelflife.scan(db, b, limit=MAX_FINDINGS * 2)["items"]
    items = sorted(items, key=lambda i: -(i.get("days_over") or 0))
    return [{"pass": "obsolescence", "subject": i["source"], "relation": i["relation"], "keep": None,
             "replace": [{k: i.get(k) for k in ("uuid", "fact", "target", "valid_at")}],
             "why": f"not confirmed since {str(i['stale_since'])[:10]}, {i['days_over']} days past its {i['shelf_life_days']}-day shelf life"}
            for i in items if i["uuid"] not in busy][:MAX_FINDINGS]


# The noise pass: deterministic and conservative on purpose (a keyword list alone gave false positives on a real brain, #300).
# A placeholder that is not a thing of the world: a fact with one at either end says nothing that can be used.
PLACEHOLDERS = frozenset("""it this that these those them they something someone thing things stuff user the-user
esto eso ello él ella ellos ellas algo alguien cosa cosas usuario el-usuario lo la le""".split())
# The memory talking about itself: an entity named like this is the graph, not the world it describes.
# Only names that cannot be a thing of the world: «node» is also Node.js, «memory» also RAM and «edge» also a browser.
META = frozenset("""knowledge-graph the-graph this-graph the-memory this-memory episode episodes fact facts entity entities
grafo-de-conocimiento el-grafo este-grafo la-memoria esta-memoria episodio episodios hecho hechos entidad entidades""".split())
# A change told as an event («X was moved to Y»): history, redundant when a current fact between the same entities states the result.
_CHANGE = re.compile(r"\b(was|were|has been|have been|got) (changed|moved|migrated|updated|renamed|replaced|switched|upgraded)\b|"
                     r"\bse (cambi[oó]|movi[oó]|migr[oó]|actualiz[oó]|renombr[oó]|sustituy[oó])\b|\bha sido (cambiad|movid|migrad|actualizad|renombrad)", re.I)
_WORD = re.compile(r"\w(?:[\w.-]*\w)?")


def _name(s) -> str:
    return "-".join(str(s or "").lower().split())


def _content(text: str, minus: set[str]) -> set[str]:
    """The words of four letters or more (or with a digit) of a fact that are not the names of its two entities."""
    return {w for w in (x.lower() for x in _WORD.findall(text or "")) if (len(w) >= 4 or any(c.isdigit() for c in w)) and w not in minus}


def noise_reason(f: dict, others: list[dict]) -> str | None:
    """Why a current fact is noise, or None. `others`: the other current facts between the same two entities."""
    from .conflicts import generic
    s, t = _name(f.get("source")), _name(f.get("target"))
    if s in PLACEHOLDERS or t in PLACEHOLDERS or len(s) < 2 or len(t) < 2:
        return "one end is a placeholder, not a thing of the world"
    if s in META or t in META:
        return "it is about the memory itself, not the world it describes"
    names = set(_WORD.findall(f"{f.get('source') or ''} {f.get('target') or ''}".lower()))
    if generic(f.get("name")) and len(_content(f.get("fact") or "", names)) < 2:
        return "a generic relation that says nothing beyond its two entities"
    if _CHANGE.search(f.get("fact") or "") and any(not _CHANGE.search(o.get("fact") or "") for o in others):
        return "a change told as an event, while a current fact between the same entities states the result"
    return None


def noise(brain_id: int) -> list[dict]:
    """Findings of the noise pass, one fact each, proposed for invalidation."""
    from .db import graph, rows
    with _factory()() as db:
        b = db.get(Brain, brain_id)
        gname, busy = b.graph_name, _pending_targets(db, brain_id)
    facts = rows(graph(gname).query(_RICH, {"n": 50000}))
    pairs: dict[tuple, list[dict]] = {}
    for f in facts:
        pairs.setdefault(tuple(sorted((str(f["source_uuid"]), str(f["target_uuid"])))), []).append(f)
    out = []
    for f in facts:
        if f["uuid"] in busy:
            continue
        others = [o for o in pairs[tuple(sorted((str(f["source_uuid"]), str(f["target_uuid"]))))] if o["uuid"] != f["uuid"]]
        why = noise_reason(f, others)
        if why:
            out.append({"pass": "noise", "subject": f["source"], "relation": f["name"], "keep": None,
                        "replace": [{k: f.get(k) for k in ("uuid", "fact", "target", "valid_at")}], "why": why})
            if len(out) >= MAX_FINDINGS:
                break
    return out


def coverage_stop(brain_id: int) -> str | None:
    """Why the curator must not run today: the memory health's coverage fell (as `health.degraded` measures it) after curators
    approved some of the curator's proposals. None if it may run."""
    from . import appsettings, health
    from .models import HealthRun
    drop = float(appsettings.get("health_coverage_drop"))
    if not drop:
        return None
    with _factory()() as db:
        last = list(db.scalars(select(HealthRun).where(HealthRun.brain_id == brain_id, HealthRun.status == "done")
                                .order_by(HealthRun.day.desc()).limit(2)))
        if len(last) < 2:
            return None
        d = health.coverage_drop(last[0].metrics or {}, last[1].metrics or {})
        if not d or d[0] - d[1] < drop - 1e-9:
            return None
        since = last[1].finished_at or last[1].created_at
        approved = db.scalar(select(func.count()).select_from(Proposal).where(
            Proposal.brain_id == brain_id, Proposal.category.like("curator.%"), Proposal.status.in_(("approved", "ingested")),
            Proposal.reviewed_at >= since))
    if not approved:
        return None
    return (f"la cobertura bajó del {round(d[0] * 100, 1):g} % al {round(d[1] * 100, 1):g} % tras aprobar {approved} propuestas del curador: "
            "no propone nada hasta que la cobertura se recupere o se revise")


FINDERS = {"contradictions": contradictions, "redundancy": redundancy, "obsolescence": obsolescence, "noise": noise}


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
            keep = f.get("keep") or {}   # the obsolescence pass keeps nothing: the fact just stops being current
            raw = [{"subject": f["subject"], "relation": f["relation"], "value": keep.get("target") or x["target"], "valid_from": keep.get("valid_at"),
                    "supersedes": x["uuid"]} for x in f["replace"]]
            try:
                checked = claims_mod.check(g, raw, amap, functional)
            except claims_mod.ClaimError:   # a fact stopped being current since the pass read it
                continue
            name = (f"Curador: ruido «{(f['replace'][0].get('fact') or '')[:200]}»" if f["pass"] == "noise"
                    else f"Curador: repite «{(keep.get('fact') or '')[:200]}»" if f["pass"] == "redundancy"
                    else f"Curador: sin confirmar «{(f['replace'][0].get('fact') or '')[:200]}»" if f["pass"] == "obsolescence"
                    else f"Curador: «{f['subject']}» {f['relation']} → {keep.get('target')}")[:255]
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
    stop = coverage_stop(bid)
    if stop:   # the reference queries say the curated memory answers worse: stop and say so (#300)
        from . import notify
        with _factory()() as db:
            r = db.get(CuratorRun, p["run_id"])
            r.status, r.error, r.finished_at = "stopped", stop, datetime.now(timezone.utc)
            db.commit()
            name = db.get(Brain, bid).name
            slug = db.get(Brain, bid).slug
        notify.emit("curator.stopped", f"El curador de «{name}» se ha detenido", stop[:1].upper() + stop[1:] + ".", brain_id=bid, key=f"curator:{slug}")
        return {"stopped": stop}
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
