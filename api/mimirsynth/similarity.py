"""How similar two facts of this brain usually are (#468). With today's embedding models the cosine of two unrelated facts sits high
(0.6-0.8) and in a narrow band, so a fixed threshold cannot tell «close» from «about anything else in this brain». This measures, per
brain and embedding model:

- the **baseline**: the true cosine of random pairs of current facts (each pair from two different entity pairs), with its percentiles;
- the **same-thing pairs**: facts a curator decided say the same thing (approved redundancy proposals and topic-review merges), whose
  embeddings stay after they are invalidated, and how many of them fall under the baseline's p99 (the overlap).

A fact is «close» to a proposal only above the baseline's p99 and above the fixed floor. The measurement is kept with the brain's
daily health run (a «similarity» part of `health.measure`), and in memory between runs; a change of embedding model, or a stored
measurement older than STORED_DAYS, makes it stale. Recall's `min_similarity` and the curator's
near-duplicate threshold are only shown against it, never changed here: they are measured with the reference queries first."""
from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select

from .db import rows
from .health import _VECTORS, _cosine

log = logging.getLogger("mimirsynth.similarity")

PAIRS = 400            # random pairs measured for the baseline
MIN_FACTS = 30         # fewer current facts than this: nothing to measure, the fixed thresholds stay
MIN_PAIRS = 30         # fewer measured pairs than this (all facts on one pair of entities, vectors missing): not measured either
MAX_SCAN = 20000       # current facts listed to draw the sample from, the newest first
SAME_MAX = 300         # same-thing pairs measured at most
CLOSE_FLOOR = 0.70     # «close» is never below this cosine, whatever the brain (today's fixed CLOSE_SCORE 0.85 on the (1+cos)/2 scale)
CACHE_SECONDS = 6 * 3600
STORED_DAYS = 2        # a measurement kept with a health run older than this is taken again: the brain has changed since
DOWN_SECONDS = 120     # after a failed measurement, the graph is not asked again for this long: every panel would wait on it

_CURRENT = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.invalid_at IS NULL AND r.expired_at IS NULL AND r.fact_embedding IS NOT NULL "
            "RETURN r.uuid AS uuid, a.uuid AS s, b.uuid AS t ORDER BY coalesce(r.valid_at, r.created_at) DESC, r.uuid LIMIT $n")
_cache: dict[int, tuple[float, dict]] = {}
_down: dict[int, float] = {}
_lock = threading.Lock()
_measuring: dict[int, threading.Lock] = {}   # one measurement per brain at a time: the others wait for it and read its result


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo), 4)


def _vectors(g, uuids: list[str]) -> dict[str, list]:
    out: dict[str, list] = {}
    for i in range(0, len(uuids), 500):
        for r in rows(g.query(_VECTORS, {"u": uuids[i:i + 500]})):
            if r.get("e"):
                out[r["uuid"]] = r["e"]
    return out


def same_pairs(db, brain_id: int) -> list[tuple[str, str]]:
    """Fact pairs a curator decided say the same thing: an approved redundancy proposal (kept, dropped: each claim's `supersedes` is one
    fact's uuid) and an approved merge action of a topic review (kept, each merged)."""
    from .models import Proposal, TopicReview
    pairs: list[tuple[str, str]] = []
    for p in db.scalars(select(Proposal).where(Proposal.brain_id == brain_id, Proposal.category == "curator.redundancy",
                                               Proposal.status.in_(("approved", "ingested")))):
        keep = (((p.decision or {}).get("curator") or {}).get("keep") or {}).get("uuid")
        for c in p.claims or []:
            sup = c.get("supersedes") if isinstance(c, dict) else None
            for u in ([sup] if isinstance(sup, str) else sup if isinstance(sup, list) else []):
                if keep and isinstance(u, str) and u != keep:
                    pairs.append((keep, u))
    for r in db.scalars(select(TopicReview).where(TopicReview.brain_id == brain_id, TopicReview.status == "ready")):
        items = r.items or {}
        for a in r.actions or []:
            if a.get("type") != "merge" or a.get("decision") != "approved":
                continue
            ids = [(items.get(x) or {}).get("uuid") for x in a.get("facts") or []]
            keep = (items.get(a.get("keep") or "") or {}).get("uuid") or (ids[0] if ids else None)
            pairs += [(keep, u) for u in ids if keep and u and u != keep]
    return list(dict.fromkeys(pairs))[:SAME_MAX]


def measure(g, db, brain_id: int, model: dict | None = None, seed: int | None = None) -> dict:
    """The brain's similarity distribution now. Never raises for a small brain: it says so with `too_few`."""
    model = model or _model()
    current = rows(g.query(_CURRENT, {"n": MAX_SCAN}))
    out: dict = {"model": model.get("model"), "dim": model.get("dim"), "facts": len(current),
                 "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if len(current) < MIN_FACTS:
        return {**out, "too_few": True, "reason": "facts", "baseline": None, "same": None}
    rnd = random.Random(seed if seed is not None else brain_id)
    pairs: list[tuple[str, str]] = []
    for _ in range(PAIRS * 4):   # two facts about different entity pairs, so a pair of near-repeats is not taken for the baseline
        if len(pairs) >= PAIRS:
            break
        a, b = rnd.sample(current, 2)
        if {a["s"], a["t"]} != {b["s"], b["t"]}:
            pairs.append((a["uuid"], b["uuid"]))
    same = same_pairs(db, brain_id)
    vec = _vectors(g, list(dict.fromkeys([u for p in pairs + same for u in p])))
    base = [_cosine(vec[a], vec[b]) for a, b in pairs if a in vec and b in vec and len(vec[a]) == len(vec[b])]
    if len(base) < MIN_PAIRS:   # nothing to stand on: every fact between the same entities, or the embeddings missing
        return {**out, "too_few": True, "reason": "pairs", "baseline": None, "same": None}
    baseline = {"pairs": len(base), "p50": _pct(base, 0.5), "p90": _pct(base, 0.9), "p95": _pct(base, 0.95), "p99": _pct(base, 0.99)}
    sims = [_cosine(vec[a], vec[b]) for a, b in same if a in vec and b in vec and len(vec[a]) == len(vec[b])]
    p99 = baseline["p99"]
    same_out = {"pairs": len(sims), "p10": _pct(sims, 0.1), "p50": _pct(sims, 0.5),
                "under_p99": round(sum(1 for s in sims if s < p99) / len(sims), 3) if sims else None}
    return {**out, "too_few": False, "baseline": baseline, "same": same_out}


def _model() -> dict:
    """The embedding model in use: a measurement taken with another one is stale."""
    try:
        from .embed import resolve_embedding
        e = resolve_embedding()
        return {"model": e.get("model"), "dim": e.get("dim")}
    except Exception:  # noqa: BLE001
        return {"model": None, "dim": None}


def _recent(m: dict) -> bool:
    try:
        at = datetime.fromisoformat(str(m.get("measured_at")))
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - (at if at.tzinfo else at.replace(tzinfo=timezone.utc))).days < STORED_DAYS


def current(db, brain, g=None, refresh: bool = False) -> dict | None:
    """The brain's measurement with the embedding model in use: from memory, else from its latest health run (if recent), else
    measured now and kept in memory. None when it cannot be measured (the graph is down): after a failure the graph is not asked
    again for DOWN_SECONDS, unless an administrator asks. One measurement per brain at a time; the others wait for its result."""
    model = _model()
    fresh = lambda m: bool(m) and m.get("model") == model.get("model") and m.get("dim") == model.get("dim")  # noqa: E731

    def known():
        with _lock:
            hit = _cache.get(brain.id)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS and fresh(hit[1]):
            return hit[1]
        from .models import HealthRun
        run = db.scalar(select(HealthRun).where(HealthRun.brain_id == brain.id, HealthRun.status == "done").order_by(HealthRun.day.desc()).limit(1))
        stored = ((run.metrics or {}).get("similarity") if run else None)
        if fresh(stored) and _recent(stored):
            remember(brain.id, stored)
            return stored
        return None
    if not refresh and (m := known()):
        return m
    with _lock:
        gate = _measuring.setdefault(brain.id, threading.Lock())
    with gate:
        if not refresh and (m := known()):   # another request measured it while this one waited
            return m
        if not refresh and time.monotonic() - _down.get(brain.id, -DOWN_SECONDS) < DOWN_SECONDS:
            return None
        try:   # the graph is opened here, inside the guard: a graph that is down is «not measured», never an error
            from .db import graph
            m = measure((g() if callable(g) else g) or graph(brain.graph_name), db, brain.id, model)
        except Exception as e:  # noqa: BLE001  (the panels fall back to the fixed thresholds)
            log.warning("similarity of brain %s: %s", brain.id, e.__class__.__name__)
            _down[brain.id] = time.monotonic()
            return None
        _down.pop(brain.id, None)
        remember(brain.id, m, db)
        return m


def remember(brain_id: int, m: dict, db=None) -> None:
    """Keeps a measurement. When «close» moves, the verdicts of the pending proposals were taken with another threshold: they are
    cleared, and checked again as the queue is opened (`proposals.check_unchecked`)."""
    with _lock:
        before = _cache.get(brain_id)
        _cache[brain_id] = (time.monotonic(), m)
    if db is None:
        return
    if before is not None:
        prev = before[1]
    else:   # a restart: the threshold the verdicts were taken with is the one kept with the last health run (or the fixed one)
        from .models import HealthRun
        run = db.scalar(select(HealthRun).where(HealthRun.brain_id == brain_id, HealthRun.status == "done").order_by(HealthRun.day.desc()).limit(1))
        prev = (run.metrics or {}).get("similarity") if run else None
    if abs(close_cosine(prev) - close_cosine(m)) >= 0.005:
        try:
            from .proposals import reset_verdicts
            reset_verdicts(db, brain_id)
        except Exception as e:  # noqa: BLE001  (the verdicts are refreshed as each proposal is opened anyway)
            log.warning("similarity of brain %s: verdicts not reset: %s", brain_id, e.__class__.__name__)


def forget(brain_id: int) -> None:
    with _lock:
        _cache.pop(brain_id, None)
    _down.pop(brain_id, None)


def close_cosine(m: dict | None) -> float:
    """The cosine above which a fact is close to a proposal in this brain: the baseline's p99, never under the fixed floor."""
    p99 = ((m or {}).get("baseline") or {}).get("p99")
    return max(CLOSE_FLOOR, p99) if p99 is not None and not (m or {}).get("too_few") else CLOSE_FLOOR


def standing(cos: float | None, m: dict | None) -> str | None:
    """Where a cosine sits in this brain: «well_above» (at «close» or over), «above» (over p95), «usual» (as any two facts), or None
    unmeasured. «well_above» is the same line as «close», so a card never says one and its relevance the other."""
    b = (m or {}).get("baseline") or {}
    if cos is None or not b or (m or {}).get("too_few") or b.get("p95") is None:
        return None
    return "well_above" if cos >= close_cosine(m) else "above" if cos >= b["p95"] else "usual"


# --- API ---------------------------------------------------------------------------------------------
from fastapi import APIRouter, Depends  # noqa: E402

from .deps import BrainCtx, audit, brain_access  # noqa: E402

router = APIRouter(prefix="/api/brains/{slug}/similarity")
curator = brain_access("curator")
admin = brain_access("admin")


def _thresholds(ctx: BrainCtx, m: dict | None) -> list[dict]:
    """The similarity thresholds the brain uses now, each as a cosine, to be read against its distribution."""
    # only thresholds that compare two facts: the curator's grouping of episodes compares episode texts, another distribution
    from . import appsettings, health
    from .distil import COVER_SIMILARITY
    return [{"key": "close", "cosine": round(close_cosine(m), 4)},
            {"key": "near_duplicate", "cosine": health.REDUNDANT_COSINE},
            {"key": "recall_min", "cosine": float(appsettings.get("recall_min_similarity"))},
            {"key": "distil_cover", "cosine": COVER_SIMILARITY}]


def _out(ctx: BrainCtx, m: dict | None) -> dict:
    b = (m or {}).get("baseline") or {}
    # a value for recall's threshold to try with the reference queries: just over what any two facts of this brain score
    suggest = round(b["p95"], 2) if b.get("p95") is not None and not (m or {}).get("too_few") else None
    return {"measurement": m, "thresholds": _thresholds(ctx, m), "suggested_recall_min": suggest, "min_facts": MIN_FACTS}


@router.get("")
def read(ctx: BrainCtx = Depends(curator)):
    """The brain's similarity distribution and where each threshold sits on it (#468)."""
    return _out(ctx, current(ctx.db, ctx.brain, lambda: ctx.graph))


@router.post("/measure")
def measure_now(ctx: BrainCtx = Depends(admin)):
    """Measures it again now, with the embedding model in use."""
    m = current(ctx.db, ctx.brain, lambda: ctx.graph, refresh=True)
    audit(ctx.db, ctx.user, "similarity.measure", ctx.brain, facts=(m or {}).get("facts"))
    return _out(ctx, m)
