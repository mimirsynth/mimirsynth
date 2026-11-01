"""What in a brain is waiting for a person's decision (#164): the counters behind the «Needs your attention» block of the home screen
and the summary of Content quality.

Each counter is the one its own page already computes (proposals, corrections, duplicate groups, possible contradictions, facts to
review, type corrections and the last run of the reference queries). They are kept CACHE_SECONDS per brain, so opening the home
screen does not scan the graph each time; a counter that fails comes back as `null` instead of breaking the rest. Only curators and
above can ask, and the type corrections are only given to administrators, the only ones who can apply them.
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
_LOCK = threading.Lock()


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


def counts(ctx: BrainCtx, fresh: bool = False) -> dict:
    """Every counter of the brain, read at most every CACHE_SECONDS unless `fresh`."""
    hit = _CACHE.get(ctx.brain.id)
    if hit and not fresh and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
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
    with _LOCK:
        _CACHE[ctx.brain.id] = (time.monotonic(), out)
    return out


def forget(brain_id: int) -> None:
    with _LOCK:
        _CACHE.pop(brain_id, None)


@router.get("")
def attention(fresh: bool = False, ctx: BrainCtx = Depends(curator)):
    """What is waiting for a decision in the brain, counter by counter (`null` if it could not be computed). `retype` only for
    administrators. `fresh` computes them again: Content quality asks so after each change, the home screen does not."""
    out = dict(counts(ctx, fresh))
    if not allows(ctx.role, "admin"):
        out.pop("retype", None)
    return out
