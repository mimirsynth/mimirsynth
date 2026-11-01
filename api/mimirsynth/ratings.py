"""Ratings of the recall (#110): whoever uses the recall says whether each item it returned was useful, irrelevant or incorrect.

- **`recall_id`:** every recall over HTTP or MCP is logged (`recall_logs`) with what it returned (kind, id, similarity and the
  start of its text) and gives back a short `recall_id`. It can be rated for RATE_HOURS; after that, a log nobody rated is purged.
  The log is written after the answer is sent and fails open: the recall never waits for it nor breaks because of it; if it could
  not be written, that `recall_id` simply cannot be rated.
- **The query:** only its hash and length, unless the brain chooses to keep its text (`recall_query_text`), and then only for
  QUERY_TEXT_DAYS: real queries carry people's prompts.
- **Who rates:** anyone who can read the brain, with a request limit. «Incorrect» on a fact of the brain, from a contributor or
  above, opens a correction proposal (#109) that a curator decides; it never invalidates anything by itself. From a reader it is
  only recorded, and the quality view lists it.
- **Quality view:** per kind of item and per similarity range, how much was useful, irrelevant or incorrect, next to the total
  number of recalls (a few clicks are not a trend). This is what tells whether to raise or lower a threshold.
- **Retention:** ratings and their logs follow the brain's `ratings_days` period (#137).
"""
import hashlib
import logging
import secrets
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update

from . import ratelimit
from .deps import BrainCtx, admin_of_brain, audit, brain_access
from .models import RecallLog, RecallRating
from .roles import allows
from .store import _factory

RATE_HOURS = 48
QUERY_TEXT_DAYS = 30
RATINGS = ("useful", "irrelevant", "incorrect")
KINDS = ("fact", "chunk", "doc")
TEXT = 200  # start of each item's text kept in the log, to find it again when an agent rates it by its text
MIN_TEXT = 12  # shortest text an item can be rated by
log_ = logging.getLogger("mimirsynth.ratings")
LIMIT = (60, 60.0)  # ratings per user and minute

router = APIRouter(prefix="/api/brains/{slug}/recall")
reader = brain_access("reader")
curator = brain_access("curator")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def items_of(out: dict) -> list[dict]:
    """What a recall returned, as rateable items."""
    items = []
    for f in out.get("facts") or []:
        items.append({"kind": "fact", "id": str(f.get("uuid") or ""), "sim": f.get("score"), "origin": f.get("origin"), "text": (f.get("fact") or "")[:TEXT]})
    for c in out.get("chunks") or []:
        items.append({"kind": "chunk", "id": f"{c.get('origin') or ''}:{c.get('id')}", "sim": c.get("score"), "origin": c.get("origin"),
                      "text": (c.get("text") or "")[:TEXT]})
    for p in out.get("documents") or []:
        items.append({"kind": "doc", "id": f"{p.get('origin') or ''}:{p.get('document_id')}:{p.get('chunk_idx')}", "sim": p.get("similarity"),
                      "origin": p.get("origin"), "text": (p.get("text") or "")[:TEXT]})
    return items


def log(ctx: BrainCtx, query: str, out: dict, bg=None) -> str:
    """Gives the recall its `recall_id` and logs it, after the answer when `bg` (BackgroundTasks) is given. Never raises."""
    rid = secrets.token_urlsafe(9)
    row = dict(brain_id=ctx.brain.id, rid=rid, user_id=ctx.user.id, query_hash=hashlib.sha256(query.encode()).hexdigest(),
               query_len=len(query), query_text=query if ctx.brain.recall_query_text else None, items=items_of(out))
    if bg is not None:
        bg.add_task(_write, row)
    else:
        _write(row)
    return rid


def _write(row: dict) -> None:
    try:
        with _factory()() as db:
            db.add(RecallLog(**row))
            db.commit()
    except Exception:  # noqa: BLE001  (a full table, a lock, a duplicate rid: that recall cannot be rated, nothing else)
        log_.warning("no se pudo registrar el recall %s para poder valorarlo", row.get("rid"), exc_info=True)


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def find_item(entry: RecallLog, kind: str, item_id: str = "", text: str = "") -> dict | None:
    """The logged item by its id or, for an agent that only saw the context, by its text: the logged text must start with what was
    given (at least MIN_TEXT characters), and if several items do, it answers 409 with them instead of choosing one."""
    for it in entry.items or []:
        if it["kind"] == kind and item_id and it["id"] == item_id:
            return it
    want = _norm(text)[:TEXT]
    if len(want) < MIN_TEXT:
        if text:
            raise HTTPException(400, f"el texto es demasiado corto para saber qué elemento es: da al menos {MIN_TEXT} caracteres")
        return None
    hits = [it for it in entry.items or [] if it["kind"] == kind and _norm(it["text"]).startswith(want)]
    if len(hits) > 1:
        cands = "; ".join(f"«{h['text'][:80]}»" for h in hits[:5])
        raise HTTPException(409, f"varios elementos empiezan así: {cands}. Repite con más texto")
    return hits[0] if hits else None


class RateIn(BaseModel):
    kind: str = Field(pattern="^(fact|chunk|doc)$")
    id: str = Field("", max_length=80)
    text: str = Field("", max_length=2000, description="the item's text as shown, when its id is not known (an agent that read the context)")
    rating: str = Field(pattern="^(useful|irrelevant|incorrect)$")
    note: str = Field("", max_length=500)


def rate(ctx: BrainCtx, request: Request, rid: str, body: RateIn) -> dict:
    if not ratelimit.allow(f"rate:{ctx.user.id}", *LIMIT):
        raise HTTPException(429, "demasiadas valoraciones seguidas: espera un minuto")
    entry = ctx.db.scalar(select(RecallLog).where(RecallLog.rid == rid, RecallLog.brain_id == ctx.brain.id))
    if not entry or _now() - _aware(entry.created_at) > timedelta(hours=RATE_HOURS):
        raise HTTPException(404, "recall no encontrado o ya no se puede valorar")
    it = find_item(entry, body.kind, body.id, body.text)
    if not it:
        raise HTTPException(404, "ese elemento no está en lo que devolvió el recall")
    r = ctx.db.scalar(select(RecallRating).where(RecallRating.log_id == entry.id, RecallRating.kind == it["kind"], RecallRating.item_id == it["id"],
                                                 RecallRating.user_id == ctx.user.id))
    if not r:
        r = RecallRating(brain_id=ctx.brain.id, log_id=entry.id, kind=it["kind"], item_id=it["id"], similarity=it.get("sim"), user_id=ctx.user.id)
        ctx.db.add(r)
    r.rating, r.created_at = body.rating, _now()
    ctx.db.commit()
    out = {"ok": True, "rating": r.rating, "proposal_id": r.proposal_id, "recorded_only": False}
    if body.rating == "incorrect" and it["kind"] == "fact" and not it.get("origin") and not r.proposal_id:
        if allows(ctx.role, "contributor"):  # a curator decides; nothing is invalidated from here
            from .corrections import CorrectionIn, create
            reason = "Valorado como incorrecto al consultar la memoria" + (f": {body.note.strip()}" if body.note.strip() else "")
            try:
                p = create(ctx, request, CorrectionIn(fact_uuid=it["id"], reason=reason), direct=False)
                r.proposal_id = p.id
                ctx.db.commit()
                out["proposal_id"] = p.id
            except HTTPException as e:  # already invalidated, lent… the rating stays
                out["correction_error"] = e.detail
        else:
            out["recorded_only"] = True
    return out


@router.post("/{rid}/ratings")
def rate_endpoint(rid: str, body: RateIn, request: Request, ctx: BrainCtx = Depends(reader)):
    return rate(ctx, request, rid, body)


def _bucket(sim) -> str | None:
    if not isinstance(sim, (int, float)):
        return None
    lo = min(int(max(sim, 0) * 10), 9) / 10
    return f"{lo:.1f}–{lo + 0.1:.1f}"


@router.get("/quality")
def quality(days: int = Query(30, ge=1, le=366), ctx: BrainCtx = Depends(curator)):
    """Ratings per kind of item and per similarity range, with the number of recalls they come from."""
    since = _now() - timedelta(days=days)
    recalls = ctx.db.scalar(select(func.count(RecallLog.id)).where(RecallLog.brain_id == ctx.brain.id, RecallLog.created_at >= since)) or 0
    rows = ctx.db.scalars(select(RecallRating).where(RecallRating.brain_id == ctx.brain.id, RecallRating.created_at >= since)).all()
    by_kind = {k: Counter() for k in KINDS}
    buckets: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for r in rows:
        by_kind[r.kind][r.rating] += 1
        b = _bucket(r.similarity)
        if b:
            buckets[r.kind][b][r.rating] += 1
    incorrect = [r for r in sorted(rows, key=lambda x: x.created_at, reverse=True) if r.rating == "incorrect"][:20]
    logs = {lg.id: lg for lg in ctx.db.scalars(select(RecallLog).where(RecallLog.id.in_({r.log_id for r in incorrect})))} if incorrect else {}
    recent = []
    for r in incorrect:
        it = next((i for i in (logs[r.log_id].items or []) if i["kind"] == r.kind and i["id"] == r.item_id), {}) if r.log_id in logs else {}
        recent.append({"kind": r.kind, "text": it.get("text", ""), "similarity": r.similarity, "created_at": r.created_at, "proposal_id": r.proposal_id})
    return {"days": days, "recalls": recalls, "rated_recalls": len({r.log_id for r in rows}), "ratings": len(rows),
            "by_kind": {k: {x: c[x] for x in RATINGS} for k, c in by_kind.items()},
            "buckets": {k: [{"range": b, **{x: c[x] for x in RATINGS}} for b, c in sorted(v.items())] for k, v in buckets.items()},
            "incorrect": recent, "keep_query_text": ctx.brain.recall_query_text, "query_text_days": QUERY_TEXT_DAYS, "rate_hours": RATE_HOURS}


class SettingsIn(BaseModel):
    keep_query_text: bool


@router.put("/settings")
def set_settings(body: SettingsIn, ctx: BrainCtx = Depends(admin_of_brain)):
    if ctx.brain.recall_query_text != body.keep_query_text:
        ctx.brain.recall_query_text = body.keep_query_text
        if not body.keep_query_text:  # turning it off also drops what was kept
            ctx.db.execute(update(RecallLog).where(RecallLog.brain_id == ctx.brain.id).values(query_text=None))
        ctx.db.commit()
        audit(ctx.db, ctx.user, "recall.query_text", ctx.brain, keep=body.keep_query_text)
    return {"keep_query_text": ctx.brain.recall_query_text}


def purge(now: datetime | None = None) -> dict:
    """Logs nobody rated once they can no longer be rated, and query texts past QUERY_TEXT_DAYS (called daily)."""
    now = now or _now()
    with _factory()() as db:
        rated = select(RecallRating.log_id)
        a = db.execute(delete(RecallLog).where(RecallLog.created_at < now - timedelta(hours=RATE_HOURS), RecallLog.id.not_in(rated)))
        b = db.execute(update(RecallLog).where(RecallLog.created_at < now - timedelta(days=QUERY_TEXT_DAYS), RecallLog.query_text.is_not(None))
                       .values(query_text=None))
        db.commit()
        return {"logs": a.rowcount or 0, "texts": b.rowcount or 0}
