"""Archiving what is never recalled (#297): a fact nobody's recall has brought for a long time, and that nobody confirmed, takes the recall's
budget from those that are used. The curator proposes archiving it; a person decides; an archived fact stays in the graph, untouched,
and is left out of the recall unless asked for (`archived: true`). Archiving is reversible at any time.

- **Last recalled:** every logged recall (HTTP, MCP, Answer) updates, after answering, the last date each of its own facts came back
  (`fact_recalls`). This is what «never recalled» is measured against, so the curator's archive pass only proposes once the brain has
  been tracked for the whole period (`archive_days`, 180 by default): before that, every old fact would look unused.
- **Archived** is a sidecar table (`fact_archive`), as decided on #297: the graph and graphiti-core's data are never changed, and
  `DELETE /api/brains/{slug}/archive/{uuid}` brings a fact back.
- **Candidates** (the curator's `archive` pass, off by default): current facts learned before the period, not recalled in it, never
  confirmed by a person or a probe, and without a pending proposal.
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from .deps import BrainCtx, audit, brain_access
from .models import FactArchive, FactRecall
from .store import _factory

log = logging.getLogger("mimirsynth.archive")
router = APIRouter(prefix="/api/brains/{slug}/archive")
curator = brain_access("curator")
CACHE_SECONDS = 30.0
_CACHE: dict[int, tuple[float, frozenset[str]]] = {}
_LOCK = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def touch(brain_id: int, uuids: list[str]) -> None:
    """The recall brought these facts of the brain now. Never raises."""
    uuids = list(dict.fromkeys(u for u in uuids if u))
    if not uuids:
        return
    try:
        now = _now()
        with _factory()() as db:
            known = {r.fact_uuid: r for r in db.scalars(select(FactRecall).where(FactRecall.brain_id == brain_id, FactRecall.fact_uuid.in_(uuids)))}
            for u in uuids:
                r = known.get(u)
                if r:
                    r.last_recalled_at, r.count = now, (r.count or 0) + 1
                else:
                    db.add(FactRecall(brain_id=brain_id, fact_uuid=u, first_recalled_at=now, last_recalled_at=now, count=1))
            db.commit()
    except Exception:  # noqa: BLE001  (a lost update only makes a fact look a little older)
        log.warning("no se pudo anotar qué hechos trajo un recall del brain %s", brain_id, exc_info=True)


def tracked_since(db, brain_id: int) -> datetime | None:
    first = db.scalar(select(func.min(FactRecall.first_recalled_at)).where(FactRecall.brain_id == brain_id))
    return first if first is None or first.tzinfo else first.replace(tzinfo=timezone.utc)


def archived(brain_id: int) -> frozenset[str]:
    """The brain's archived facts, read at most every CACHE_SECONDS (the recall asks on every query)."""
    hit = _CACHE.get(brain_id)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    with _factory()() as db:
        out = frozenset(db.scalars(select(FactArchive.fact_uuid).where(FactArchive.brain_id == brain_id)))
    with _LOCK:
        _CACHE[brain_id] = (time.monotonic(), out)
    return out


def forget(brain_id: int) -> None:
    with _LOCK:
        _CACHE.pop(brain_id, None)


def leave_out(brain_id: int, facts: list[dict]) -> list[dict]:
    """The recall's facts without the brain's archived ones (lent facts are the lending brain's business)."""
    gone = archived(brain_id)
    return [f for f in facts if f.get("origin") or f.get("uuid") not in gone] if gone else facts


def put(db, brain_id: int, uuid: str, user_id: int | None, proposal_id: int | None = None, reason: str = "") -> bool:
    if db.scalar(select(FactArchive).where(FactArchive.brain_id == brain_id, FactArchive.fact_uuid == uuid)):
        return False
    db.add(FactArchive(brain_id=brain_id, fact_uuid=uuid, user_id=user_id, proposal_id=proposal_id, reason=reason[:300]))
    forget(brain_id)
    return True


def candidates(db, brain, days: int, busy: set[str], limit: int) -> list[dict]:
    """Current facts learned before `days` ago, not recalled since, never confirmed, not archived: none if tracking is younger."""
    from .db import graph, rows
    from .models import FactConfirmation, FactProbe
    since, cutoff = tracked_since(db, brain.id), _now() - timedelta(days=days)
    if since is None or since > cutoff:
        return []
    recent = set(db.scalars(select(FactRecall.fact_uuid).where(FactRecall.brain_id == brain.id, FactRecall.last_recalled_at >= cutoff)))
    confirmed = set(db.scalars(select(FactConfirmation.fact_uuid).where(FactConfirmation.brain_id == brain.id)))
    verified = set(db.scalars(select(FactProbe.fact_uuid).where(FactProbe.brain_id == brain.id, FactProbe.state == "verified")))
    skip = recent | confirmed | verified | busy | set(archived(brain.id))
    out = []
    for f in rows(graph(brain.graph_name).query(
            "MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.invalid_at IS NULL AND r.expired_at IS NULL AND r.created_at < $c "
            "RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, r.valid_at AS valid_at, r.created_at AS created_at, a.name AS source, "
            "b.name AS target ORDER BY r.created_at, r.uuid LIMIT 20000", {"c": cutoff.isoformat()})):
        if f["uuid"] not in skip:
            out.append(f)
            if len(out) >= limit:
                break
    return out


# --- API --------------------------------------------------------------------------------------

@router.get("")
def list_archived(ctx: BrainCtx = Depends(curator)):
    """The brain's archived facts, the newest first, with their text when the graph still has them."""
    from .db import rows
    items = list(ctx.db.scalars(select(FactArchive).where(FactArchive.brain_id == ctx.brain.id).order_by(FactArchive.id.desc()).limit(500)))
    text = {}
    if items:
        text = {r["uuid"]: r for r in rows(ctx.graph.query("MATCH (a:Entity)-[r:RELATES_TO]->(:Entity) WHERE r.uuid IN $u RETURN r.uuid AS uuid, "
                                                           "r.fact AS fact, a.name AS source, a.uuid AS source_uuid", {"u": [i.fact_uuid for i in items]}))}
    return {"items": [{"fact_uuid": i.fact_uuid, "archived_at": i.archived_at, "reason": i.reason, "proposal_id": i.proposal_id,
                       **{k: (text.get(i.fact_uuid) or {}).get(k) for k in ("fact", "source", "source_uuid")}} for i in items]}


@router.delete("/{uuid}")
def restore(uuid: str, ctx: BrainCtx = Depends(curator)):
    """Brings an archived fact back into the recall."""
    row = ctx.db.scalar(select(FactArchive).where(FactArchive.brain_id == ctx.brain.id, FactArchive.fact_uuid == uuid))
    if not row:
        raise HTTPException(404, "el hecho no está archivado")
    ctx.db.delete(row)
    ctx.db.commit()
    forget(ctx.brain.id)
    audit(ctx.db, ctx.user, "fact.unarchive", ctx.brain, uuid=uuid)
    return {"ok": True}
