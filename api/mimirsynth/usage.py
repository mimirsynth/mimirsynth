"""AI consumption per brain (#132): calls, tokens, errors and pace of every call MimirSynth makes to an AI engine, with an estimated
cost and an optional monthly budget.

- **Where it is counted:** in the HTTP client of each call to an engine (extraction with Graphiti, decider, embeddings), with an
  httpx response hook. The `usage` field of the answer gives the tokens; when there is none, the input is estimated (4 characters
  per token) and the call is counted as estimated. A 429 and a 5xx are counted apart: they explain why an ingestion is slow or fails.
- **On behalf of whom:** `scope(brain_id, purpose)` around the work; a context variable, so it follows threads that copy the
  context and `asyncio.run`. A call outside any scope counts for brain 0 (engine tests, a model change).
- **What is kept:** counters per day, brain, engine kind, model and purpose (`ai_usage`), never the calls. A call only adds to
  counters in memory; they are written every FLUSH_EVERY seconds, on shutdown and before anything reads them, so an engine call (a
  recall's embedding) never waits for the database. The pace (requests per minute) is measured in memory: the live value per engine,
  and the day's peak in the counters.
- **Cost:** a price per million input and output tokens per model (`ai_prices`), editable; a local engine is left at zero.
- **Budget:** optional, per brain and month, in tokens or in cost. At 80 % it warns (`ai.budget`); at 100 % it warns again and, if
  so configured, pauses the brain's ingestion: approved proposals wait, marked, and go on by themselves when the month changes or
  the budget is raised.
"""
import json
import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import secretguard
from .deps import BrainCtx, admin_of_brain, audit, require_admin
from .models import AiPrice, AiUsage, Brain, Proposal, User
from .store import _factory, get_db

log = logging.getLogger("mimirsynth.usage")
KINDS = ("llm", "embedding", "decision")
CHARS_PER_TOKEN = 4
PAUSED = "en pausa: el brain ha agotado su presupuesto de IA de este mes"  # the marker of a proposal that waits for the budget
LEVELS = (80, 100)
_SCOPE: ContextVar[tuple[int, str]] = ContextVar("mimirsynth_ai_scope", default=(0, "other"))
_LOCK = threading.Lock()
_RECENT: dict[tuple[str, str], deque] = defaultdict(deque)   # (kind, model) -> times of the last minute's calls
_MINUTE: dict[tuple, int] = {}                                # (day, brain, kind, model, purpose, minute) -> calls in that minute
_STATUS: dict[int, tuple[float, dict]] = {}                   # brain -> (when, budget status): checked at most every CHECK_EVERY seconds
CHECK_EVERY = 30.0
FLUSH_EVERY = 5.0
_PENDING: dict[tuple, dict] = {}                              # counters not yet written: (day, brain, kind, model, purpose) -> increments
_FLUSH_LOCK = threading.Lock()                                # one writer at a time
_flusher: threading.Thread | None = None

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def scope(brain_id: int | None, purpose: str):
    """The calls inside count for this brain and this purpose."""
    token = _SCOPE.set((int(brain_id or 0), purpose))
    try:
        yield
    finally:
        _SCOPE.reset(token)


def current() -> tuple[int, str]:
    return _SCOPE.get()


# --- counting -------------------------------------------------------------------------------------

def _tokens(request_body: bytes, payload) -> tuple[int, int, bool]:
    """(input, output, estimated) from the answer's `usage`, or estimated from the request when it has none."""
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if isinstance(usage, dict):
        tin = usage.get("prompt_tokens", usage.get("input_tokens"))
        tout = usage.get("completion_tokens", usage.get("output_tokens", 0))
        if isinstance(tin, int):
            return tin, tout if isinstance(tout, int) else 0, False
    return len(request_body or b"") // CHARS_PER_TOKEN, 0, True


COUNTERS = ("calls", "errors_429", "errors_5xx", "errors_other", "prompt_tokens", "completion_tokens", "estimated_calls")


def record(kind: str, model: str, status: int, tin: int = 0, tout: int = 0, estimated: bool = False,
           brain_id: int | None = None, purpose: str | None = None) -> None:
    """Adds one call to the day's counters, in memory (see `flush`). Never raises: counting must not break the call it counts."""
    try:
        b, p = current()
        b, p = (b if brain_id is None else brain_id), (purpose or p)
        now = _now()
        day, minute = now.date(), int(now.timestamp() // 60)
        inc = {"calls": 1, "errors_429": int(status == 429), "errors_5xx": int(500 <= status < 600),
               "errors_other": int(status >= 400 and status != 429 and status < 500), "prompt_tokens": tin, "completion_tokens": tout,
               "estimated_calls": int(estimated)}
        key = (day, b, kind, model[:255], p[:32])
        with _LOCK:
            q = _RECENT[(kind, model)]
            q.append(now.timestamp())
            while q and q[0] < now.timestamp() - 60:
                q.popleft()
            mk = (*key, minute)
            _MINUTE[mk] = _MINUTE.get(mk, 0) + 1
            for k in [k for k in _MINUTE if k[5] < minute - 2]:
                del _MINUTE[k]
            acc = _PENDING.setdefault(key, {c: 0 for c in COUNTERS} | {"peak_rpm": 0})
            for c, v in inc.items():
                acc[c] += v
            acc["peak_rpm"] = max(acc["peak_rpm"], _MINUTE[mk])
        _start_flusher()
        if b and _over_budget_soon(b):
            _check_budget(b)
    except Exception:  # noqa: BLE001
        log.exception("no se pudo contar una llamada a un motor de IA")


def _over_budget_soon(brain_id: int) -> bool:
    """Whether the budget status is due for a check (cached for CHECK_EVERY seconds, so most calls skip it)."""
    hit = _STATUS.get(brain_id)
    return not hit or time.monotonic() - hit[0] >= CHECK_EVERY


def flush() -> int:
    """Writes the counters gathered in memory. Called every FLUSH_EVERY seconds, on shutdown and before the counters are read."""
    with _FLUSH_LOCK:
        with _LOCK:
            batch = dict(_PENDING)
            _PENDING.clear()
        if not batch:
            return 0
        try:
            with _factory()() as db:
                greatest = func.max if db.get_bind().dialect.name == "sqlite" else func.greatest
                for (day, b, kind, model, purpose), inc in batch.items():
                    key = dict(day=day, brain_id=b, kind=kind, model=model, purpose=purpose)
                    for _ in range(2):
                        r = db.execute(update(AiUsage).where(*[getattr(AiUsage, k) == v for k, v in key.items()])
                                       .values(**{c: getattr(AiUsage, c) + inc[c] for c in COUNTERS},
                                               peak_rpm=greatest(AiUsage.peak_rpm, inc["peak_rpm"])))
                        if r.rowcount:
                            db.commit()
                            break
                        try:
                            db.add(AiUsage(**key, **{c: inc[c] for c in COUNTERS}, peak_rpm=inc["peak_rpm"]))
                            db.commit()
                            break
                        except IntegrityError:  # another process inserted it meanwhile: add to theirs
                            db.rollback()
        except Exception:  # noqa: BLE001  (the database is down: keep the counts for the next flush)
            log.exception("no se pudieron guardar los contadores de consumo de IA")
            with _LOCK:
                for k, inc in batch.items():
                    acc = _PENDING.setdefault(k, {c: 0 for c in COUNTERS} | {"peak_rpm": 0})
                    for c in COUNTERS:
                        acc[c] += inc[c]
                    acc["peak_rpm"] = max(acc["peak_rpm"], inc["peak_rpm"])
            return 0
        return len(batch)


def _start_flusher() -> None:
    global _flusher
    if _flusher and _flusher.is_alive():
        return
    with _LOCK:
        if _flusher and _flusher.is_alive():
            return

        def loop():
            while True:
                time.sleep(FLUSH_EVERY)
                flush()
        _flusher = threading.Thread(target=loop, name="ai-usage-flush", daemon=True)
        _flusher.start()


def _on_response(kind: str, model: str, response, body: bytes) -> None:
    payload = None
    if response.status_code == 200:
        try:
            payload = json.loads(body or b"null")
        except ValueError:
            payload = None
    tin, tout, est = _tokens(response.request.content if response.request else b"", payload) if response.status_code == 200 else (0, 0, False)
    record(kind, model, response.status_code, tin, tout, est)


def observe(kind: str, model: str, response) -> None:
    """Counts a call already answered (for code that calls `httpx.post` directly). Never raises."""
    try:
        _on_response(kind, model, response, response.content)
    except Exception:  # noqa: BLE001
        log.debug("respuesta no contable de %s:%s", kind, model)


def hooks(kind: str, model: str) -> dict:
    """Event hooks for an `httpx.Client` that calls an engine. They read the whole body to find `usage`: do not use a hooked client for
    a streaming call, it would wait for the end of the stream."""
    def on_response(response):
        response.read()
        _on_response(kind, model, response, response.content)
    return {"response": [on_response]}


def async_hooks(kind: str, model: str) -> dict:
    """The same for an `httpx.AsyncClient` (Graphiti's OpenAI clients); the same warning about streaming."""
    import asyncio

    async def on_response(response):
        await response.aread()
        _on_response(kind, model, response, response.content)  # only memory: the budget check is cached
    return {"response": [on_response]}


def live_rpm() -> dict[str, int]:
    """Requests in the last minute per engine (`kind:model`), measured in this process."""
    now = time.time()
    with _LOCK:
        return {f"{k}:{m}": sum(1 for t in q if t >= now - 60) for (k, m), q in _RECENT.items() if q}


# --- cost and budget ------------------------------------------------------------------------------

def prices(db: Session) -> dict[tuple[str, str], tuple[float, float]]:
    return {(p.kind, p.model): (p.price_in, p.price_out) for p in db.scalars(select(AiPrice))}


def cost(row, table: dict) -> float | None:
    """Estimated cost of a row of counters, or None when its model has no price."""
    pr = table.get((row.kind, row.model))
    if pr is None:
        return None
    return round((row.prompt_tokens * pr[0] + row.completion_tokens * pr[1]) / 1_000_000, 6)


def _month_start(today: date) -> date:
    return today.replace(day=1)


def month_used(db: Session, brain_id: int, today: date | None = None) -> dict:
    flush()
    today = today or _now().date()
    rows = db.scalars(select(AiUsage).where(AiUsage.brain_id == brain_id, AiUsage.day >= _month_start(today))).all()
    table = prices(db)
    costs = [cost(r, table) for r in rows]
    return {"tokens": sum(r.prompt_tokens + r.completion_tokens for r in rows), "cost": round(sum(c for c in costs if c), 6),
            "unpriced": sorted({f"{r.kind}:{r.model}" for r, c in zip(rows, costs) if c is None and (r.prompt_tokens or r.completion_tokens)})}


def budget_status(db: Session, brain: Brain, today: date | None = None) -> dict:
    b = brain.ai_budget or {}
    used = month_used(db, brain.id, today)
    limit, unit = b.get("limit"), b.get("unit", "tokens")
    pct = round(100 * used[unit] / limit, 1) if limit else None
    return {"limit": limit, "unit": unit, "pause": bool(b.get("pause")), "used": used[unit], "pct": pct,
            "paused": bool(limit and b.get("pause") and used[unit] >= limit), "unpriced": used["unpriced"] if unit == "cost" else []}


def _check_budget(brain_id: int, force: bool = False) -> dict:
    """The brain's budget status, recomputed at most every CHECK_EVERY seconds; warns once per month at 80 % and at 100 %."""
    hit = _STATUS.get(brain_id)
    if hit and not force and time.monotonic() - hit[0] < CHECK_EVERY:
        return hit[1]
    from . import notify
    with _factory()() as db:
        brain = db.get(Brain, brain_id)
        if not brain or not (brain.ai_budget or {}).get("limit"):
            st = {"paused": False, "pct": None}
        else:
            st = budget_status(db, brain)
            month = _now().strftime("%Y-%m")
            for level in LEVELS:
                if st["pct"] is not None and st["pct"] >= level:
                    what = "tokens" if st["unit"] == "tokens" else "coste estimado"
                    notify.emit("ai.budget", f"«{brain.name}» ha gastado el {level} % de su presupuesto de IA de este mes",
                                f"Consumo del mes ({what}): {st['used']} de {st['limit']}."
                                + (" La ingesta de propuestas queda en pausa hasta el mes que viene o hasta que se suba el presupuesto."
                                   if level == 100 and st["pause"] else ""),
                                severity="critical" if level == 100 else "warning", brain_id=brain.id, key=f"budget:{brain.id}:{month}:{level}")
    _STATUS[brain_id] = (time.monotonic(), st)
    return st


def paused(brain_id: int) -> bool:
    """Whether the brain's ingestion waits for its budget."""
    return bool(_check_budget(brain_id, force=True).get("paused"))


def resume() -> int:
    """Puts back in the queue the proposals that waited for a budget that no longer stops them (new month, or a higher budget). Called
    by the notifications loop."""
    from . import ingest
    n = 0
    with _factory()() as db:
        waiting = db.scalars(select(Proposal).where(Proposal.status == "approved", Proposal.ingest_error == PAUSED)).all()
        for p in waiting:
            if paused(p.brain_id):
                continue
            p.ingest_error = ""
            db.commit()
            ingest.submit_ingest(p.id, p.brain_id, secretguard.safe_name(p))  # what the detector flagged in the title stays covered
            n += 1
    return n


# --- API --------------------------------------------------------------------------------------------

def _rows_out(rows, table) -> list[dict]:
    agg: dict[tuple, dict] = {}
    for r in rows:
        k = (r.kind, r.model, r.purpose)
        a = agg.setdefault(k, {"kind": r.kind, "model": r.model, "purpose": r.purpose, "calls": 0, "errors_429": 0, "errors_5xx": 0,
                               "errors_other": 0, "prompt_tokens": 0, "completion_tokens": 0, "estimated_calls": 0, "peak_rpm": 0, "cost": 0.0,
                               "priced": True})
        for c in ("calls", "errors_429", "errors_5xx", "errors_other", "prompt_tokens", "completion_tokens", "estimated_calls"):
            a[c] += getattr(r, c)
        a["peak_rpm"] = max(a["peak_rpm"], r.peak_rpm)
        c = cost(r, table)
        if c is None:
            a["priced"] = False
        else:
            a["cost"] = round(a["cost"] + c, 6)
    return sorted(agg.values(), key=lambda x: -(x["prompt_tokens"] + x["completion_tokens"]))


def _series(rows, since: date, days: int) -> list[dict]:
    per = defaultdict(lambda: {"calls": 0, "tokens": 0, "errors": 0})
    for r in rows:
        d = per[r.day.isoformat()]
        d["calls"] += r.calls
        d["tokens"] += r.prompt_tokens + r.completion_tokens
        d["errors"] += r.errors_429 + r.errors_5xx + r.errors_other
    return [{"day": (since + timedelta(days=i)).isoformat(), **per[(since + timedelta(days=i)).isoformat()]} for i in range(days)]


@router.get("/api/brains/{slug}/ai-usage")
def brain_usage(days: int = Query(30, ge=1, le=366), ctx: BrainCtx = Depends(admin_of_brain)):
    flush()
    since = _now().date() - timedelta(days=days - 1)
    rows = ctx.db.scalars(select(AiUsage).where(AiUsage.brain_id == ctx.brain.id, AiUsage.day >= since)).all()
    table = prices(ctx.db)
    return {"days": days, "series": _series(rows, since, days), "rows": _rows_out(rows, table), "budget": budget_status(ctx.db, ctx.brain)}


class BudgetIn(BaseModel):
    limit: float | None = Field(None, gt=0, description="monthly limit; empty: no budget")
    unit: str = Field("tokens", pattern="^(tokens|cost)$")
    pause: bool = Field(False, description="pause the brain's ingestion when the budget is spent")


@router.put("/api/brains/{slug}/ai-budget")
def set_budget(body: BudgetIn, ctx: BrainCtx = Depends(admin_of_brain)):
    before = ctx.brain.ai_budget
    after = {"limit": body.limit, "unit": body.unit, "pause": body.pause} if body.limit else None
    if before != after:
        ctx.brain.ai_budget = after
        ctx.db.commit()
        audit(ctx.db, ctx.user, "brain.ai_budget", ctx.brain, **{"from": before, "to": after})
        _STATUS.pop(ctx.brain.id, None)
    return budget_status(ctx.db, ctx.brain)


@router.get("/api/ai-usage")
def instance_usage(days: int = Query(30, ge=1, le=366), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Every brain's consumption and the engines' pace: requests per minute now, the day's peak and the 429/5xx errors."""
    flush()
    since = _now().date() - timedelta(days=days - 1)
    rows = db.scalars(select(AiUsage).where(AiUsage.day >= since)).all()
    table = prices(db)
    names = {b.id: (b.slug, b.name) for b in db.scalars(select(Brain))}
    by_brain = defaultdict(list)
    for r in rows:
        by_brain[r.brain_id].append(r)
    brains = []
    for bid, rs in by_brain.items():
        out = _rows_out(rs, table)
        slug, name = names.get(bid, ("", "")) if bid else ("", "")
        brains.append({"brain_id": bid, "slug": slug, "name": name, "calls": sum(x["calls"] for x in out),
                       "tokens": sum(x["prompt_tokens"] + x["completion_tokens"] for x in out),
                       "errors_429": sum(x["errors_429"] for x in out), "errors_5xx": sum(x["errors_5xx"] for x in out),
                       "cost": round(sum(x["cost"] for x in out), 6), "priced": all(x["priced"] for x in out)})
    engines = _rows_out([type("R", (), {**{c: getattr(r, c) for c in ("kind", "model", "calls", "errors_429", "errors_5xx", "errors_other",
                                                                      "prompt_tokens", "completion_tokens", "estimated_calls", "peak_rpm")},
                                        "purpose": ""})() for r in rows], table)
    live = live_rpm()
    for e in engines:
        e["rpm_now"] = live.get(f"{e['kind']}:{e['model']}", 0)
        e["price"] = table.get((e["kind"], e["model"]))
    return {"days": days, "series": _series(rows, since, days), "brains": sorted(brains, key=lambda x: -x["tokens"]), "engines": engines}


class PriceIn(BaseModel):
    kind: str = Field(pattern="^(llm|embedding|decision)$")
    model: str = Field(min_length=1, max_length=255)
    price_in: float = Field(ge=0, le=100000)
    price_out: float = Field(0, ge=0, le=100000)


@router.put("/api/ai-usage/prices")
def set_price(body: PriceIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.scalar(select(AiPrice).where(AiPrice.kind == body.kind, AiPrice.model == body.model))
    if not p:
        p = AiPrice(kind=body.kind, model=body.model)
        db.add(p)
    p.price_in, p.price_out = body.price_in, body.price_out
    db.commit()
    audit(db, user, "ai.price", None, kind=body.kind, model=body.model, price_in=body.price_in, price_out=body.price_out)
    _STATUS.clear()
    return {"kind": p.kind, "model": p.model, "price_in": p.price_in, "price_out": p.price_out}


@router.delete("/api/ai-usage/prices")
def delete_price(kind: str, model: str, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.scalar(select(AiPrice).where(AiPrice.kind == kind, AiPrice.model == model))
    if not p:
        raise HTTPException(404, "ese modelo no tiene precio")
    db.delete(p)
    db.commit()
    audit(db, user, "ai.price", None, kind=kind, model=model, removed=True)
    _STATUS.clear()
    return {"ok": True}
