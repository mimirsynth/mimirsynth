"""Shelf life per relation type (#114): facts that go stale without anyone contradicting them (an IP, a version, who runs a service).

A relation type of the ontology can have a shelf life in days (`shelf_life_days`); none has one by default. A current fact of that
relation whose last date (its last confirmation, or else its `valid_at`) is older than its shelf life is **to review**:
- in the recall it weighs less (`recall_stale_weight`) and says «not confirmed since …», also in the context the agent reads;
- it is listed in Content quality → **To review**, where a curator **confirms** it (stores the date in PostgreSQL, the graph is not
  touched) or **invalidates** it (as from Facts);
- a daily check counts them per brain (`facts.stale`, information, without text).

A fact without a `valid_at` (imported from another system, for example) never goes stale by date: there is nothing to measure from.
Lent facts are not marked: the shelf life is the lending brain's business.
"""
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from . import appsettings
from .conflicts import generic
from .db import graph, parse_ts, rows
from .deps import BrainCtx, audit, brain_access
from .models import Brain, BrainOntology, FactConfirmation
from .ontology import get_ontology
from .store import _factory
from .vocab import alias_map, canon_rel, resolve

MAX_SCAN = 20000  # facts read per scan, the oldest first: past it the queue says it is showing only part
CACHE_SECONDS = 30.0  # how long a brain's shelf lives are reused by the recall (saving the ontology clears them)
_CACHE: dict[int, tuple[float, dict[str, int]]] = {}
_CACHE_LOCK = threading.Lock()
router = APIRouter(prefix="/api/brains/{slug}/review")
curator = brain_access("curator")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def shelf_lives(onto: dict | None) -> dict[str, int]:
    """{relation (canonical): days} of the relation types with a shelf life."""
    out = {}
    for t in (onto or {}).get("edge_types", []):
        days = t.get("shelf_life_days")
        if isinstance(days, int) and days > 0 and not generic(t["name"]):
            out[canon_rel(t["name"])] = days
    return out


def confirmations(db, brain_id: int, uuids=None) -> dict[str, datetime]:
    q = select(FactConfirmation).where(FactConfirmation.brain_id == brain_id)
    if uuids is not None:
        q = q.where(FactConfirmation.fact_uuid.in_(list(uuids)))
    return {c.fact_uuid: (c.confirmed_at if c.confirmed_at.tzinfo else c.confirmed_at.replace(tzinfo=timezone.utc)) for c in db.scalars(q)}


def stale_since(valid_at, confirmed: datetime | None, days: int, now: datetime | None = None) -> datetime | None:
    """The date the fact has not been confirmed since, if its shelf life is over; None if it is not stale (or has no date)."""
    base = confirmed or parse_ts(valid_at)
    if base is None:
        return None
    return base if (now or _now()) - base > timedelta(days=days) else None


def cached_lives(brain_id: int) -> dict[str, int]:
    """The brain's shelf lives, read at most every CACHE_SECONDS: the recall asks for them on every query."""
    hit = _CACHE.get(brain_id)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    with _factory()() as db:
        lives = shelf_lives(get_ontology(db, brain_id))
    with _CACHE_LOCK:
        _CACHE[brain_id] = (time.monotonic(), lives)
    return lives


def forget(brain_id: int) -> None:
    """The brain's ontology changed: the next recall reads its shelf lives again."""
    with _CACHE_LOCK:
        _CACHE.pop(brain_id, None)


def mark(brain_id: int, facts: list[dict], amap: dict | None = None) -> list[dict]:
    """Marks the recall's own current facts that are to review (`stale_since`) and lowers their score. Returns them reordered. A brain
    without shelf lives costs nothing here once they are cached; with them, one query for the confirmations of the facts returned."""
    lives = cached_lives(brain_id)
    if not lives:
        return facts
    own = [f for f in facts if not f.get("origin") and f.get("status") == "current" and canon_rel(f.get("name") or "") in lives]
    if not own:
        return facts
    with _factory()() as db:
        conf = confirmations(db, brain_id, {f["uuid"] for f in own if f.get("uuid")})
    weight = float(appsettings.get("recall_stale_weight"))
    for f in own:
        since = stale_since(f.get("valid_at"), conf.get(f.get("uuid")), lives[canon_rel(f["name"])])
        if since:
            f["stale_since"] = since.isoformat()
            if isinstance(f.get("score"), (int, float)):
                f["score"] = round(f["score"] * weight, 4)
    if any(f.get("stale_since") for f in own):
        facts = sorted(facts, key=lambda f: -(f.get("score") or 0))
    return facts


def scan(db, brain: Brain, limit: int = 500) -> dict:
    """The brain's current facts that are to review, the oldest first. Only the relations with a shelf life are read: the names stored
    in the graph that resolve to them (format and aliases), found first with a DISTINCT. If there are more than MAX_SCAN such facts,
    the oldest MAX_SCAN are read and `truncated` says so."""
    lives = shelf_lives(get_ontology(db, brain.id))
    if not lives:
        return {"relations": {}, "total": 0, "items": [], "truncated": False}
    amap = alias_map(db, brain.id)
    g = graph(brain.graph_name)
    names = [r[0] for r in g.query("MATCH ()-[r:RELATES_TO]->() RETURN DISTINCT r.name").result_set
             if r[0] and canon_rel(resolve(r[0], amap)) in lives]
    if not names:
        return {"relations": lives, "total": 0, "items": [], "truncated": False}
    res = g.query(
        "MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.name IN $names AND r.invalid_at IS NULL AND r.expired_at IS NULL "
        "AND r.valid_at IS NOT NULL RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, r.valid_at AS valid_at, a.name AS source, "
        f"a.uuid AS source_uuid, b.name AS target, b.uuid AS target_uuid ORDER BY r.valid_at LIMIT {MAX_SCAN + 1}", {"names": names})
    facts = rows(res)
    truncated = len(facts) > MAX_SCAN
    facts = facts[:MAX_SCAN]
    conf = confirmations(db, brain.id, {f["uuid"] for f in facts})
    now, out = _now(), []
    for f in facts:
        rel = canon_rel(resolve(f["name"], amap))
        since = stale_since(f["valid_at"], conf.get(f["uuid"]), lives[rel], now)
        if since:
            out.append({**f, "relation": rel, "shelf_life_days": lives[rel], "stale_since": since.isoformat(),
                        "confirmed_at": conf[f["uuid"]].isoformat() if f["uuid"] in conf else None,
                        "days_over": (now - since).days - lives[rel]})
    out.sort(key=lambda x: x["stale_since"])
    return {"relations": lives, "total": len(out), "items": out[:limit], "truncated": truncated}


@router.get("/stale")
def list_stale(limit: int = Query(500, ge=1, le=5000), ctx: BrainCtx = Depends(curator)):
    return scan(ctx.db, ctx.brain, limit)


@router.post("/stale/{uuid}/confirm")
def confirm(uuid: str, ctx: BrainCtx = Depends(curator)):
    """The fact is still true: renews its date. Nothing changes in the graph; the confirmation is stored and audited."""
    hit = rows(ctx.graph.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() RETURN r.fact AS fact, r.name AS name, r.invalid_at AS invalid_at",
                               {"u": uuid}))
    if not hit:
        raise HTTPException(404, "hecho no encontrado")
    if hit[0]["invalid_at"]:
        raise HTTPException(409, "el hecho ya está invalidado: no se puede confirmar")
    if canon_rel(resolve(hit[0]["name"], alias_map(ctx.db, ctx.brain.id))) not in shelf_lives(get_ontology(ctx.db, ctx.brain.id)):
        raise HTTPException(409, "la relación de ese hecho no tiene vida útil: confirmarlo no cambiaría nada")
    c = ctx.db.scalar(select(FactConfirmation).where(FactConfirmation.brain_id == ctx.brain.id, FactConfirmation.fact_uuid == uuid))
    if not c:
        c = FactConfirmation(brain_id=ctx.brain.id, fact_uuid=uuid)
        ctx.db.add(c)
    c.confirmed_at, c.user_id = _now(), ctx.user.id
    ctx.db.commit()
    audit(ctx.db, ctx.user, "fact.confirm", ctx.brain, uuid=uuid)
    return {"ok": True, "confirmed_at": c.confirmed_at}


def check_all() -> int:
    """Counts the facts to review of each brain with some shelf life and says so in the bell (called daily). No text, only counts."""
    from . import notify
    n = 0
    with _factory()() as db:
        ids = [o.brain_id for o in db.scalars(select(BrainOntology)) if shelf_lives(o.data)]
        for b in db.scalars(select(Brain).where(Brain.id.in_(ids))) if ids else []:
            try:
                total = scan(db, b, limit=1)["total"]
            except Exception:  # noqa: BLE001  (a graph that does not answer is not a reason to skip the others)
                continue
            key = f"stale:{b.slug}"
            if total:
                notify.emit("facts.stale", f"«{b.name}» tiene {total} hechos sin confirmar desde hace más de su vida útil",
                            "Revísalos en Calidad del contenido → A revisar: confirma los que siguen siendo ciertos e invalida los demás.",
                            severity="info", brain_id=b.id, key=key)
                n += 1
            else:
                notify.resolve("facts.stale", key, "Ya no hay hechos a revisar.")
    return n
