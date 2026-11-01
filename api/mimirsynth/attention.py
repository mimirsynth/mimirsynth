"""What in a brain is waiting for a person's decision (#164): the counters behind the «Needs your attention» block of the home screen
and the summary of Content quality.

Each counter is the one its own page already computes (proposals, corrections, duplicate groups, possible contradictions, facts to
review, type corrections and the last run of the reference queries). They are kept CACHE_SECONDS per brain, so opening the home
screen does not scan the graph each time; a counter that fails comes back as `null` instead of breaking the rest. Only curators and
above can ask, and the type corrections are only given to administrators, the only ones who can apply them.

The cache is dropped by any successful write on the brain (`invalidate_after_writes`: deciding a proposal, merging, resolving or
dismissing a contradiction, confirming or invalidating a fact, a type correction…), so the next read already shows the change. What
changes on its own (a fact that goes past its shelf life, a job that ingests, an agent proposing over MCP) shows within the minute.
With the cache empty the scans run in the request, one computation per brain at a time: on a large brain that first read is slower.
"""
import logging
import threading
import time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from .deps import BrainCtx, brain_access
from .models import Proposal, RefRun
from .roles import allows

log = logging.getLogger("mimirsynth.attention")
router = APIRouter(prefix="/api/brains/{slug}/attention")
curator = brain_access("curator")
CACHE_SECONDS = 60.0
_CACHE: dict[int, tuple[float, dict]] = {}
_GEN: dict[int, int] = {}                 # bumped by forget(): a computation that started before it is not kept
_LOCKS: dict[int, threading.Lock] = {}    # one computation per brain at a time
_LOCK = threading.Lock()
WRITES = {"POST", "PUT", "PATCH", "DELETE"}
READS = ("/recall", "/query", "/attention", "/duplicates/preview")  # POSTs that only read: they keep the cache


def _proposals(ctx: BrainCtx) -> dict:
    rows = ctx.db.execute(select(Proposal.kind, func.count()).where(Proposal.brain_id == ctx.brain.id, Proposal.status == "pending")
                          .group_by(Proposal.kind)).all()
    return {"proposals": sum(n for k, n in rows if (k or "memory") != "correction"), "corrections": sum(n for k, n in rows if k == "correction")}


def _duplicates(ctx: BrainCtx) -> int:
    from .graphapi import duplicates
    return len(duplicates(ctx.graph, ctx.db, ctx.brain.id)[1])


def _conflicts(ctx: BrainCtx) -> int:
    from .conflicts import _brain_functional, _dismissals, scan
    from .vocab import alias_map
    functional = _brain_functional(ctx.db, ctx.brain.id)
    if not functional:
        return 0
    return scan(ctx.graph, alias_map(ctx.db, ctx.brain.id), functional, dismissed=_dismissals(ctx.db, ctx.brain.id))["total"]


def _stale(ctx: BrainCtx) -> int:
    from .shelflife import scan
    return scan(ctx.db, ctx.brain, limit=1)["total"]


def _retype(ctx: BrainCtx) -> int:
    from .retype import pending_count
    return pending_count(ctx.db, ctx.brain.id)


def _refqueries(ctx: BrainCtx) -> int:
    """Reference queries that got worse in the last run with the settings in force (a simulation with other parameters does not count)."""
    last = next((r for r in ctx.db.scalars(select(RefRun).where(RefRun.brain_id == ctx.brain.id, RefRun.status == "done")
                                           .order_by(RefRun.id.desc()).limit(50)) if not r.params), None)
    d = (last.summary or {}).get("delta") if last else None
    if not d or not d.get("regressed"):
        return 0
    return len({x["id"] for x in [*d.get("lost", []), *d.get("new_false_positives", [])]}) or 1


COUNTERS = {"duplicates": _duplicates, "conflicts": _conflicts, "stale": _stale, "retype": _retype, "refqueries": _refqueries}


def _brain_lock(brain_id: int) -> threading.Lock:
    with _LOCK:
        return _LOCKS.setdefault(brain_id, threading.Lock())


def counts(ctx: BrainCtx, fresh: bool = False) -> dict:
    """Every counter of the brain, read at most every CACHE_SECONDS unless `fresh`. Concurrent requests with the cache empty wait for one
    computation and take its result; with `fresh`, a result computed after the request arrived is good enough."""
    bid, asked = ctx.brain.id, time.monotonic()
    hit = _CACHE.get(bid)
    if hit and not fresh and asked - hit[0] < CACHE_SECONDS:
        return hit[1]
    with _brain_lock(bid):
        hit = _CACHE.get(bid)
        if hit and (hit[0] >= asked or (not fresh and time.monotonic() - hit[0] < CACHE_SECONDS)):
            return hit[1]
        gen = _GEN.get(bid, 0)
        out = _compute(ctx)
        with _LOCK:
            if _GEN.get(bid, 0) == gen:  # a write during the computation may be missing from it: it is not kept
                _CACHE[bid] = (time.monotonic(), out)
        return out


def _compute(ctx: BrainCtx) -> dict:
    out: dict = {}
    try:
        out.update(_proposals(ctx))
    except Exception:  # noqa: BLE001  (one counter that fails leaves the others)
        log.warning("no se pudieron contar las propuestas del brain %s", ctx.brain.id, exc_info=True)
        out.update(proposals=None, corrections=None)
    for name, fn in COUNTERS.items():
        try:
            out[name] = fn(ctx)
        except Exception:  # noqa: BLE001
            log.warning("no se pudo calcular el contador %s del brain %s", name, ctx.brain.id, exc_info=True)
            out[name] = None
    return out


def forget(brain_id: int, gone: bool = False) -> None:
    """Something in the brain changed: the next read computes the counters again. `gone`: the brain was deleted."""
    with _LOCK:
        _CACHE.pop(brain_id, None)
        _GEN[brain_id] = _GEN.get(brain_id, 0) + 1
        if gone:
            _GEN.pop(brain_id, None)
            _LOCKS.pop(brain_id, None)


async def invalidate_after_writes(request, call_next):
    """HTTP middleware: a successful write on a brain (its routes leave `request.state.brain_id`) drops the counters of that brain."""
    state = request.state  # created before the call, so the route writes into this same state
    response = await call_next(request)
    bid = getattr(state, "brain_id", None)
    path = request.url.path
    if bid and request.method in WRITES and response.status_code < 400 and not path.endswith(READS) and "/mcp" not in path:
        forget(bid)
    return response


@router.get("")
def attention(fresh: bool = False, ctx: BrainCtx = Depends(curator)):
    """What is waiting for a decision in the brain, counter by counter (`null` if it could not be computed). `retype` only for
    administrators. `fresh` computes them again: Content quality asks so after each change, the home screen does not."""
    out = dict(counts(ctx, fresh))
    if not allows(ctx.role, "admin"):
        out.pop("retype", None)
    return out
