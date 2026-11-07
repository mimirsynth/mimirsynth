"""Replay sample (#291, first part): an opt-in sample of the recalls agents and people really send, to replay later against a candidate
configuration (a threshold, an embedding model, a release) in shadow mode and see what would change.

- **Off by default, per brain.** A brain administrator turns it on (`PUT /api/brains/{slug}/replay/settings`, or Ask → Recall quality).
  It is separate from «keep the text of the queries» (#110): the questions an agent's hook sends carry the person's prompt (up to 1,500
  characters), so keeping them for replay is its own explicit decision.
- **What is kept:** the question, with **every** secret the scanner finds masked whatever the brain's secret mode (a sample is never
  the place for a credential), the recall parameters it was asked with, what it returned (kind and id of each item, in order) and how
  it came (`http`, `mcp`, `answer`). Nothing of the memories' text.
- **Bounded:** at most `max` samples per brain (the oldest go first) and none older than `days`. Turning it off deletes them all.
- Written after the answer, with the recall log, and failing open: a recall never waits for its sample nor breaks because of it.

Replaying the sample and its report are the next part of #291.
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from .deps import BrainCtx, admin_of_brain, audit
from .models import Brain, RecallSample
from .store import _factory

log = logging.getLogger("mimirsynth.replay")
router = APIRouter(prefix="/api/brains/{slug}/replay")
DEFAULT = {"enabled": False, "max": 1000, "days": 30}
PARAMS = ("facts", "chunks", "max_chars", "docs", "federated", "min_similarity")   # what a recall request can set
LIST = 100


def config(brain: Brain) -> dict:
    return {**DEFAULT, **(brain.replay or {})}


def params_of(body) -> dict:
    """The recall parameters of a request, as it sent them (empty ones are the instance's)."""
    return {k: v for k in PARAMS if (v := getattr(body, k, None)) is not None}


def row(brain: Brain, query: str, params: dict, items: list[dict], via: str) -> dict | None:
    """The sample to store for a recall, or None if the brain does not keep them."""
    if not config(brain)["enabled"]:
        return None
    from .secretguard import mask_all
    text, n = mask_all(brain, query)
    return {"brain_id": brain.id, "via": via, "query": text, "params": params, "masked": bool(n),
            "items": [{"kind": i["kind"], "id": i["id"]} for i in items]}


def write(sample: dict) -> None:
    """Stores a sample and drops the oldest past the brain's `max`. Never raises."""
    try:
        with _factory()() as db:
            db.add(RecallSample(**sample))
            db.commit()
            b = db.get(Brain, sample["brain_id"])
            keep = config(b)["max"] if b else 0
            old = select(RecallSample.id).where(RecallSample.brain_id == sample["brain_id"]).order_by(RecallSample.id.desc()).offset(keep)
            ids = list(db.scalars(old))
            if ids:
                db.execute(delete(RecallSample).where(RecallSample.id.in_(ids)))
                db.commit()
    except Exception:  # noqa: BLE001
        log.warning("no se pudo guardar la muestra de un recall del brain %s", sample.get("brain_id"), exc_info=True)


def purge(now: datetime | None = None) -> int:
    """Samples older than their brain's `days` (called daily)."""
    now, n = now or datetime.now(timezone.utc), 0
    with _factory()() as db:
        for b in db.scalars(select(Brain).where(Brain.replay.is_not(None))):
            r = db.execute(delete(RecallSample).where(RecallSample.brain_id == b.id, RecallSample.created_at < now - timedelta(days=config(b)["days"])))
            n += r.rowcount or 0
        db.commit()
    return n


class SettingsIn(BaseModel):
    enabled: bool
    max: int = Field(DEFAULT["max"], ge=10, le=10000)
    days: int = Field(DEFAULT["days"], ge=1, le=365)


def _state(ctx: BrainCtx) -> dict:
    n = ctx.db.scalar(select(func.count()).select_from(RecallSample).where(RecallSample.brain_id == ctx.brain.id)) or 0
    return {**config(ctx.brain), "samples": n}


@router.get("/settings")
def get_settings(ctx: BrainCtx = Depends(admin_of_brain)):
    return _state(ctx)


@router.put("/settings")
def set_settings(body: SettingsIn, ctx: BrainCtx = Depends(admin_of_brain)):
    """Turns the sample on or off and sets its limits. Off deletes every sample at once; lower limits apply from the next recall."""
    ctx.brain.replay = body.model_dump()
    if not body.enabled:
        ctx.db.execute(delete(RecallSample).where(RecallSample.brain_id == ctx.brain.id))
    ctx.db.commit()
    audit(ctx.db, ctx.user, "replay.settings", ctx.brain, **body.model_dump())
    return _state(ctx)


@router.get("/samples")
def list_samples(ctx: BrainCtx = Depends(admin_of_brain)):
    """The last LIST samples, the newest first: what is being kept, to check it before replaying."""
    rows = ctx.db.scalars(select(RecallSample).where(RecallSample.brain_id == ctx.brain.id).order_by(RecallSample.id.desc()).limit(LIST))
    return {"items": [{"id": r.id, "created_at": r.created_at, "via": r.via, "query": r.query, "params": r.params or {},
                       "items": len(r.items or []), "masked": r.masked} for r in rows]}


@router.delete("/samples")
def clear_samples(ctx: BrainCtx = Depends(admin_of_brain)):
    n = ctx.db.execute(delete(RecallSample).where(RecallSample.brain_id == ctx.brain.id)).rowcount or 0
    ctx.db.commit()
    audit(ctx.db, ctx.user, "replay.clear", ctx.brain, deleted=n)
    return {"deleted": n}
