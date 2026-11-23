"""Topics to review (#456): the brain's entities ranked by where a topic review would pay off, with no AI call.

For each entity with at least MIN_FACTS current facts:
- recalls: with the replay sample on (#291), how many sampled recalls brought one of its current facts; otherwise the sum of
  `fact_recalls.count` over them (#297), which keeps no query text;
- facts: its current facts, and the groups of repeats among them (the curator's near-duplicate test, `health.clusters`);
- flagged: its current facts past their shelf life or with a refuted probe (#293);
- retirement: a retirement review (#455) of it still waiting;
- its last review: when it finished and how many current facts arrived since.

score = (1 + log2(1 + recalls)) × (log2(1 + facts) + repeat groups + 3 × flagged share + 2 if a retirement review waits) × freshness.
Freshness is 0.1 when the last review is newer than every current fact (nothing new to review); with new facts since, it climbs from 0.5
right after the review to 1 after FRESH_DAYS; never reviewed, 1. Traffic multiplies, so a topic nobody asks about still shows if it is
large or noisy, below one people ask about.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from sqlalchemy import select

from . import health, replay
from .db import rows
from .deps import BrainCtx
from .models import FactProbe, FactRecall, RecallSample, TopicReview

log = logging.getLogger("mimirsynth.topic_queue")

MIN_FACTS = 2            # a topic of one fact has nothing to reconcile
FRESH_DAYS = 30          # after a review with new facts since, the days until it counts in full again
REVIEWED = 0.1           # the weight of a topic reviewed after its newest fact
CANDIDATES = 3           # repeats are measured on this many times `limit` entities, the best by the other inputs
REVIEWS_READ = 2000      # the brain's latest reviews read to know each entity's last one
FACTS = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.invalid_at IS NULL AND r.expired_at IS NULL "
         "RETURN r.uuid AS uuid, r.fact AS fact, r.created_at AS created_at, a.uuid AS source_uuid, a.name AS source, labels(a) AS source_labels, "
         "b.uuid AS target_uuid, b.name AS target, labels(b) AS target_labels ORDER BY coalesce(r.valid_at, r.created_at) DESC, r.uuid LIMIT $n")


def _when(v) -> datetime | None:
    """A date from the graph (ISO text or a datetime) or the database, always aware."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        d = v
    else:
        try:
            d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _type(labels) -> str | None:
    """The entity's type, as its labels in the graph say (Entity alone: none)."""
    return next((x for x in sorted(labels or []) if x != "Entity"), None)


def _pending(db, r: TopicReview) -> bool:
    """A review still waiting: queued or running with its job alive, or ready with actions to decide."""
    from .topic_review import _alive
    return _alive(db, r) or (r.status == "ready" and any(a.get("decision") in ("pending", "applying") for a in r.actions or []))


def _recalls(db, brain, owner: dict[str, set[str]]) -> tuple[str, dict[str, int]]:
    """Recalls per entity, and where they were counted: «replay» (the sample) or «counts» (`fact_recalls`)."""
    out: dict[str, int] = {}
    if replay.config(brain)["enabled"]:
        for items in db.scalars(select(RecallSample.items).where(RecallSample.brain_id == brain.id)):
            touched = set()
            for i in items or []:
                if i.get("kind") == "fact":
                    touched |= owner.get(str(i.get("id")), set())
            for e in touched:
                out[e] = out.get(e, 0) + 1
        return "replay", out
    for uuid, n in db.execute(select(FactRecall.fact_uuid, FactRecall.count).where(FactRecall.brain_id == brain.id)):
        for e in owner.get(uuid, ()):
            out[e] = out.get(e, 0) + (n or 0)
    return "counts", out


def _flagged(db, brain) -> set[str]:
    """Current facts that may no longer hold: past their shelf life, or refuted by their probe."""
    out = set(db.scalars(select(FactProbe.fact_uuid).where(FactProbe.brain_id == brain.id, FactProbe.state == "refuted")))
    try:
        from .shelflife import MAX_SCAN, scan
        out |= {f["uuid"] for f in scan(db, brain, MAX_SCAN)["items"]}
    except Exception as e:  # noqa: BLE001  (without the shelf life the ranking still stands, a little less informed)
        log.warning("topic queue: could not read the shelf life: %s", e.__class__.__name__)
    return out


def _repeats(facts: list[dict]) -> int:
    """The groups of repeats among these facts (all of them about one entity)."""
    return sum(len(health.clusters(grp)) for grp in health._groups(facts))


def score(recalls: int, facts: int, repeats: int, share: float, retirement: bool, freshness: float) -> float:
    return round((1 + math.log2(1 + recalls)) * (math.log2(1 + facts) + repeats + 3 * share + (2 if retirement else 0)) * freshness, 2)


def freshness(last: datetime | None, newest: datetime | None, now: datetime) -> float:
    if last is None:
        return 1.0
    if newest is None or newest <= last:
        return REVIEWED
    return min(1.0, 0.5 + 0.5 * (now - last).total_seconds() / (FRESH_DAYS * 86400))


def ranking(ctx: BrainCtx, limit: int = 20, now: datetime | None = None) -> dict:
    db, brain, g = ctx.db, ctx.brain, ctx.graph
    now = now or datetime.now(timezone.utc)
    facts = rows(g.query(FACTS, {"n": health.MAX_FACTS}))
    truncated = len(facts) >= health.MAX_FACTS
    ents: dict[str, dict] = {}
    owner: dict[str, set[str]] = {}
    for f in facts:
        for end in ("source", "target"):
            u = f[f"{end}_uuid"]
            e = ents.setdefault(u, {"uuid": u, "name": f[end] or "", "type": _type(f.get(f"{end}_labels")), "facts": [], "newest": None})
            e["facts"].append(f)
            when = _when(f.get("created_at"))
            if when and (e["newest"] is None or when > e["newest"]):
                e["newest"] = when
            owner.setdefault(f["uuid"], set()).add(u)
    ents = {u: e for u, e in ents.items() if len(e["facts"]) >= MIN_FACTS}
    source, recalls = _recalls(db, brain, owner)
    flagged = _flagged(db, brain)
    last: dict[str, TopicReview] = {}
    waiting: dict[str, TopicReview] = {}
    q = select(TopicReview).where(TopicReview.brain_id == brain.id).order_by(TopicReview.id.desc()).limit(REVIEWS_READ)
    for r in db.scalars(q):
        if r.entity_uuid not in ents:
            continue
        if r.status == "ready" and r.entity_uuid not in last:
            last[r.entity_uuid] = r
        if r.entity_uuid not in waiting and _pending(db, r):
            waiting[r.entity_uuid] = r
    out = []
    for u, e in ents.items():
        n = len(e["facts"])
        lr = last.get(u)
        lr_at = _when(lr.finished_at) if lr else None
        w = waiting.get(u)
        retire = bool(w and w.trigger == "retirement")
        nflag = sum(1 for f in e["facts"] if f["uuid"] in flagged)
        out.append({"uuid": u, "name": e["name"], "type": e["type"], "facts": n, "recalls": recalls.get(u, 0), "repeats": 0, "flagged": nflag,
                    "flagged_share": round(nflag / n, 3), "retirement": retire,
                    "last_review": {"id": lr.id, "finished_at": lr.finished_at,
                                    "new_facts": sum(1 for f in e["facts"] if (_when(f.get("created_at")) or now) > lr_at) if lr_at else n}
                    if lr else None,
                    "waiting": {"id": w.id, "status": w.status, "trigger": w.trigger or "manual"} if w else None,
                    "_fresh": freshness(lr_at, e["newest"], now), "_facts": e["facts"]})
    for x in out:
        x["score"] = score(x["recalls"], x["facts"], 0, x["flagged_share"], x["retirement"], x["_fresh"])
    out.sort(key=lambda x: (-x["score"], x["name"].lower(), x["uuid"]))
    # repeats cost embeddings: measured on the best candidates only, as many facts as the curator's redundancy samples
    candidates, budget = out[:limit * CANDIDATES], health.MAX_SAMPLE
    need = []
    for x in candidates:
        pairs = [f for grp in health._groups(x["_facts"]) for f in grp]
        if pairs and len(pairs) <= budget:
            need += [f["uuid"] for f in pairs]
            budget -= len(pairs)
    vectors: dict[str, list] = {}
    try:
        for i in range(0, len(need), 500):
            for r in rows(g.query(health._VECTORS, {"u": need[i:i + 500]})):
                vectors[r["uuid"]] = r["e"]
    except Exception as e:  # noqa: BLE001  (without embeddings, repeats are found by their text)
        log.warning("topic queue: could not read the embeddings: %s", e.__class__.__name__)
    for x in candidates:
        x["repeats"] = _repeats([{**f, "embedding": vectors.get(f["uuid"])} for f in x["_facts"]])
        x["score"] = score(x["recalls"], x["facts"], x["repeats"], x["flagged_share"], x["retirement"], x["_fresh"])
    candidates.sort(key=lambda x: (-x["score"], x["name"].lower(), x["uuid"]))
    items = [{k: v for k, v in x.items() if not k.startswith("_")} for x in candidates[:limit]]
    return {"recalls_from": source, "replay_days": replay.config(brain)["days"] if source == "replay" else None,
            "entities": len(ents), "facts_truncated": truncated, "items": items}

