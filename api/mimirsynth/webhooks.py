"""Incoming webhooks (#122): what happens in the infrastructure (an alert, a deployment, a pipeline, a backup) becomes episodic memory.

- **Address and secret.** Each webhook of a brain has a public key in its address, `POST /api/brains/{slug}/hooks/{key}`, and a secret
  shown once. The request proves it with an HMAC-SHA256 signature of the body (`X-Hub-Signature-256` or `X-MimirSynth-Signature`,
  `sha256=<hex>`) or with the secret itself in `Authorization: Bearer`, `X-Gitlab-Token` or `X-Webhook-Token`, compared in constant
  time. Anything wrong (unknown key, disabled, wrong secret) answers the same 401 and creates nothing. The body is limited to MAX_BODY.
- **Templates** (`hooktemplates`) turn the body into events: alerts that fire and resolve, or one-off events.
- **Proposals, not facts.** Each event becomes a proposal of the brain, written as «what happened and when», with its origin in the
  source description, through the secret detector (#116) and then the decider and the curators. A webhook marked as trusted approves
  its proposals directly, still within its daily cap and never with a flagged secret.
- **Grouping.** An alert that keeps firing (same fingerprint) does not make a proposal per request: the repetitions are counted. If it
  resolves within `webhook_group_minutes` it becomes one proposal with its start, its end and the number of notices; if it outlives
  that window, one proposal says it is still firing and another says when it resolved. Nothing is invalidated: the decider and the
  curators decide what the episodes mean.
- **Limits** (#132): requests per minute per webhook (429) and proposals per day (the rest is logged as `capped` and warned once).
- **Log.** What was received is kept without its body (`webhook_events`): title, counts, dates and the proposals it became.
"""
import hashlib
import hmac
import json
import logging
import secrets as pysecrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from . import appsettings, hooktemplates, notify, ratelimit, secretguard
from .deps import BrainCtx, audit, brain_access
from .hooktemplates import Event
from .i18n import tr
from .models import Brain, User, Webhook, WebhookEvent
from .secretbox import seal, unseal
from .store import _factory

log = logging.getLogger("mimirsynth.webhooks")
router = APIRouter(prefix="/api/brains/{slug}")
admin = brain_access("admin")
MAX_BODY = 256 * 1024
KEEP_DAYS = 90       # closed groups and events older than this are forgotten
TOKEN_HEADERS = ("x-webhook-token", "x-gitlab-token")
SIGNATURE_HEADERS = ("x-hub-signature-256", "x-mimirsynth-signature")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: datetime | None) -> datetime | None:
    return d.replace(tzinfo=timezone.utc) if d and d.tzinfo is None else d


def _lang() -> str:
    return appsettings.get("default_language") or "es"


def _when(d: datetime | None) -> str:
    return _aware(d).strftime("%Y-%m-%d %H:%M UTC") if d else "?"


# --- verifying a request ---------------------------------------------------------------------------

def verify(secret: str, body: bytes, headers: dict) -> bool:
    """The request carries the secret: an HMAC-SHA256 of the body, or the secret itself in a header. Constant-time comparisons."""
    h = {k.lower(): v for k, v in headers.items()}
    for name in SIGNATURE_HEADERS:
        sig = h.get(name, "")
        if sig:
            want = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            return hmac.compare_digest(sig.strip().lower(), want)
    given = h.get("authorization", "")
    given = given[7:].strip() if given.lower().startswith("bearer ") else ""
    for name in TOKEN_HEADERS:
        given = given or h.get(name, "").strip()
    return bool(given) and hmac.compare_digest(given.encode(), secret.encode())


# --- events into proposals -------------------------------------------------------------------------

def _texts(e: Event, kind: str, g: WebhookEvent | None, lang: str, hook: Webhook) -> tuple[str, str]:
    """The proposal for an event (`kind`: event | grouped | firing | resolved), as «what happened and when»."""
    src = hooktemplates.LABELS.get(hook.template, hook.template)
    if kind == "event":
        head = tr("Evento de {{source}}: {{title}} ({{when}}).", lang, source=src, title=e.title, when=_when(e.at or _now()))
    elif kind == "grouped":
        head = tr("Incidente de {{source}}: {{title}}. Activo desde {{start}} hasta {{end}}; {{n}} avisos.", lang, source=src, title=g.title,
                  start=_when(g.first_at), end=_when(g.resolved_at), n=g.count)
    elif kind == "firing":
        head = tr("Incidente de {{source}}: {{title}}. Activo desde {{start}}; {{n}} avisos hasta {{now}} y sin resolver todavía.", lang,
                  source=src, title=g.title, start=_when(g.first_at), now=_when(g.last_at), n=g.count)
    else:
        head = tr("Incidente resuelto de {{source}}: {{title}}. Resuelto el {{end}}, tras {{n}} avisos desde {{start}}.", lang, source=src,
                  title=g.title if g else e.title, start=_when(g.first_at if g else None), end=_when(e.at or _now()), n=g.count if g else 1)
    return e.title if kind == "event" else (g.title if g else e.title), (head + ("\n" + e.text if e.text else ""))[:50000]


def _propose(db, hook: Webhook, brain: Brain, name: str, text: str, at: datetime | None, later) -> tuple[int | None, str]:
    """A proposal from the webhook, within its daily cap. Returns (proposal id, outcome): proposed | capped | blocked."""
    from .proposals import ProposalIn, store
    today = _now().date()
    if hook.day != today:
        hook.day, hook.day_count = today, 0
    if hook.day_count >= hook.daily_cap:
        notify.emit("webhook.capped", f"El webhook «{hook.name}» ha llegado a su tope diario de {hook.daily_cap} propuestas",
                    "Lo que siga llegando hoy queda en su registro, pero no se propone. Revisa el emisor o sube el tope.",
                    brain_id=brain.id, key=f"webhook:{hook.id}:{today}")
        return None, "capped"
    author = db.get(User, hook.created_by) if hook.created_by else None
    if not author:
        return None, "blocked"
    try:
        safe_name, in_name = secretguard.guard(brain, name[:255])
        safe_text, in_body = secretguard.guard(brain, text)
    except secretguard.Blocked:
        audit(db, author, "proposal.blocked", brain, reason="secrets", webhook=hook.name)
        return None, "blocked"
    body = ProposalIn(name=safe_name or name[:255], body=safe_text or text, source="json",
                      source_description=f"webhook «{hook.name}» ({hooktemplates.LABELS.get(hook.template, hook.template)})"[:255],
                      reference_time=at)
    p = store(db, brain, author, body, safe_name, safe_text, in_name, in_body, hook.auto_approve, later, how="webhook")
    hook.day_count += 1
    return p.id, "proposed"


def handle(db, hook: Webhook, brain: Brain, events: list[Event], later) -> list[dict]:
    """Applies the events of one request: one-off events are proposed now; alerts are grouped by fingerprint (see the module)."""
    lang, out = _lang(), []
    for e in events:
        now = _now()
        if e.state == "event":
            name, text = _texts(e, "event", None, lang, hook)
            pid, outcome = _propose(db, hook, brain, name, text, e.at, later)
            db.add(WebhookEvent(webhook_id=hook.id, brain_id=brain.id, kind="event", outcome=outcome, title=e.title[:300], first_at=e.at or now,
                                last_at=e.at or now, proposal_id=pid))
            out.append({"title": e.title, "outcome": outcome})
            continue
        g = db.scalar(select(WebhookEvent).where(WebhookEvent.webhook_id == hook.id, WebhookEvent.fingerprint == e.fingerprint,
                                                 WebhookEvent.kind == "alert", WebhookEvent.resolved_at.is_(None)).order_by(WebhookEvent.id.desc()))
        if e.state == "firing":
            if g:
                g.count += 1
                g.last_at = now
                out.append({"title": e.title, "outcome": "grouped", "count": g.count})
            else:
                db.add(WebhookEvent(webhook_id=hook.id, brain_id=brain.id, fingerprint=e.fingerprint, kind="alert", outcome="open",
                                    title=e.title[:300], first_at=e.at or now, last_at=now))
                out.append({"title": e.title, "outcome": "open"})
            continue
        # resolved
        if g and g.proposal_id is None:   # within the window: one proposal with its start and its end
            g.resolved_at = e.at or now
            name, text = _texts(e, "grouped", g, lang, hook)
            g.proposal_id, g.outcome = _propose(db, hook, brain, name, text, g.first_at, later)
            g.outcome = g.outcome if g.outcome != "proposed" else "closed"
        elif g:                           # it outlived the window: a second proposal for the resolution
            g.resolved_at = e.at or now
            name, text = _texts(e, "resolved", g, lang, hook)
            g.resolution_id, outcome = _propose(db, hook, brain, name, text, g.resolved_at, later)
            g.outcome = "closed" if outcome == "proposed" else outcome
        else:                             # a resolution whose alert was never seen
            name, text = _texts(e, "resolved", None, lang, hook)
            pid, outcome = _propose(db, hook, brain, name, text, e.at, later)
            db.add(WebhookEvent(webhook_id=hook.id, brain_id=brain.id, fingerprint=e.fingerprint, kind="alert",
                                outcome="closed" if outcome == "proposed" else outcome, title=e.title[:300], first_at=e.at or now,
                                last_at=now, resolved_at=e.at or now, proposal_id=pid))
        out.append({"title": e.title, "outcome": "resolved"})
    db.commit()
    return out


def flush_due() -> int:
    """Alerts still firing past the grouping window become a proposal («still firing»); old records are forgotten. Called every minute."""
    n = 0
    window = timedelta(minutes=int(appsettings.get("webhook_group_minutes")))
    with _factory()() as db:
        due = db.scalars(select(WebhookEvent).where(WebhookEvent.kind == "alert", WebhookEvent.resolved_at.is_(None),
                                                    WebhookEvent.proposal_id.is_(None), WebhookEvent.outcome == "open")).all()
        for g in due:
            if _now() - _aware(g.created_at) < window:   # from the first notice received, not the start the emitter reports
                continue
            hook, brain = db.get(Webhook, g.webhook_id), db.get(Brain, g.brain_id)
            if not hook or not brain:
                continue
            e = Event("firing", g.title, "", g.last_at, g.fingerprint)
            name, text = _texts(e, "firing", g, _lang(), hook)
            g.proposal_id, outcome = _propose(db, hook, brain, name, text, g.first_at, lambda fn, *a: fn(*a))  # already in the background
            g.outcome = "proposed" if outcome == "proposed" else outcome
            n += 1
        db.query(WebhookEvent).filter(WebhookEvent.created_at < _now() - timedelta(days=KEEP_DAYS),
                                      (WebhookEvent.kind == "event") | WebhookEvent.resolved_at.is_not(None)).delete(synchronize_session=False)
        db.commit()
    return n


# --- the incoming endpoint -------------------------------------------------------------------------

def _deny() -> HTTPException:
    return HTTPException(401, "webhook o secreto incorrecto")


@router.post("/hooks/{key}", status_code=202)
async def receive(slug: str, key: str, request: Request, bg: BackgroundTasks):
    """An external emitter sends an event. No session: the secret of the webhook is the credential (see the module)."""
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        raise HTTPException(413, "el cuerpo del webhook es demasiado grande")
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, "el cuerpo del webhook es demasiado grande")
    return await run_in_threadpool(_receive, slug, key, body, dict(request.headers), bg)


def _receive(slug: str, key: str, body: bytes, headers: dict, bg: BackgroundTasks) -> dict:
    with _factory()() as db:
        hook = db.scalar(select(Webhook).where(Webhook.key == key))
        brain = db.get(Brain, hook.brain_id) if hook else None
        if not hook or not brain or brain.slug != slug or not hook.enabled:
            raise _deny()
        if not verify(unseal(hook.secret_enc), body, headers):
            hook.rejected += 1
            hook.last_error = "bad_secret"
            db.commit()
            raise _deny()
        if not ratelimit.allow(f"webhook:{hook.id}", hook.per_minute, 60):
            hook.last_error = "rate_limited"
            db.commit()
            raise HTTPException(429, "demasiadas peticiones a este webhook; espera un minuto")
        hook.received += 1
        hook.last_at = _now()
        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            hook.last_error = "not_json"
            db.commit()
            raise HTTPException(400, "el cuerpo no es JSON válido") from None
        events = hooktemplates.parse(hook.template, payload, headers, hook.config)
        hook.last_error = "" if events else "no_events"
        out = handle(db, hook, brain, events, bg.add_task)
        return {"events": len(events), "outcomes": out}


# --- managing the webhooks of a brain --------------------------------------------------------------

class HookIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    template: str = Field(pattern="^(" + "|".join(hooktemplates.TEMPLATES) + ")$")
    config: dict = Field(default_factory=dict)
    auto_approve: bool = False
    daily_cap: int = Field(200, ge=1, le=10000)
    per_minute: int = Field(60, ge=1, le=6000)
    enabled: bool = True


class PreviewIn(BaseModel):
    template: str = Field(pattern="^(" + "|".join(hooktemplates.TEMPLATES) + ")$")
    config: dict = Field(default_factory=dict)
    body: str = Field(min_length=2, max_length=MAX_BODY)
    event: str = Field("", max_length=64, description="X-GitHub-Event, for the GitHub template")


def _config(template: str, cfg: dict) -> dict:
    """Only the generic template takes a mapping, and only these keys, as short strings."""
    if template != "generic":
        return {}
    out = {k: str(cfg[k])[:500] for k in ("title", "text", "at", "fingerprint", "state") if cfg.get(k)}
    if isinstance(cfg.get("resolved"), list):
        out["resolved"] = [str(x)[:50] for x in cfg["resolved"][:10]]
    return out


def _out(h: Webhook, slug: str) -> dict:
    return {"id": h.id, "name": h.name, "template": h.template, "config": h.config or {}, "enabled": h.enabled, "auto_approve": h.auto_approve,
            "daily_cap": h.daily_cap, "per_minute": h.per_minute, "path": f"/api/brains/{slug}/hooks/{h.key}", "received": h.received,
            "rejected": h.rejected, "today": h.day_count if h.day == _now().date() else 0, "last_at": h.last_at, "last_error": h.last_error,
            "created_at": h.created_at}


def _get(ctx: BrainCtx, hid: int) -> Webhook:
    h = ctx.db.get(Webhook, hid)
    if not h or h.brain_id != ctx.brain.id:
        raise HTTPException(404, "webhook no encontrado")
    return h


@router.get("/webhooks")
def list_hooks(ctx: BrainCtx = Depends(admin)):
    rows = ctx.db.scalars(select(Webhook).where(Webhook.brain_id == ctx.brain.id).order_by(Webhook.id)).all()
    return {"items": [_out(h, ctx.brain.slug) for h in rows], "templates": hooktemplates.LABELS,
            "group_minutes": appsettings.get("webhook_group_minutes")}


@router.post("/webhooks", status_code=201)
def create_hook(body: HookIn, ctx: BrainCtx = Depends(admin)):
    """The secret is only shown here (and when rotated)."""
    secret = pysecrets.token_urlsafe(32)
    h = Webhook(brain_id=ctx.brain.id, key=pysecrets.token_urlsafe(12), name=body.name, template=body.template,
                config=_config(body.template, body.config), secret_enc=seal(secret), enabled=body.enabled, auto_approve=body.auto_approve,
                daily_cap=body.daily_cap, per_minute=body.per_minute, created_by=ctx.user.id)
    ctx.db.add(h); ctx.db.commit()
    audit(ctx.db, ctx.user, "webhook.create", ctx.brain, name=h.name, template=h.template, auto_approve=h.auto_approve)
    return {**_out(h, ctx.brain.slug), "secret": secret}


@router.put("/webhooks/{hid}")
def update_hook(hid: int, body: HookIn, ctx: BrainCtx = Depends(admin)):
    h = _get(ctx, hid)
    h.name, h.template, h.config = body.name, body.template, _config(body.template, body.config)
    h.enabled, h.auto_approve, h.daily_cap, h.per_minute = body.enabled, body.auto_approve, body.daily_cap, body.per_minute
    ctx.db.commit()
    audit(ctx.db, ctx.user, "webhook.update", ctx.brain, name=h.name, template=h.template, enabled=h.enabled, auto_approve=h.auto_approve)
    return _out(h, ctx.brain.slug)


@router.post("/webhooks/{hid}/rotate")
def rotate_hook(hid: int, ctx: BrainCtx = Depends(admin)):
    """A new secret, at once: the old one stops working."""
    h = _get(ctx, hid)
    secret = pysecrets.token_urlsafe(32)
    h.secret_enc = seal(secret)
    ctx.db.commit()
    audit(ctx.db, ctx.user, "webhook.rotate", ctx.brain, name=h.name)
    return {**_out(h, ctx.brain.slug), "secret": secret}


@router.delete("/webhooks/{hid}", status_code=204)
def delete_hook(hid: int, ctx: BrainCtx = Depends(admin)):
    h = _get(ctx, hid)
    name = h.name
    ctx.db.delete(h); ctx.db.commit()
    audit(ctx.db, ctx.user, "webhook.delete", ctx.brain, name=name)


@router.get("/webhooks/{hid}/events")
def hook_events(hid: int, ctx: BrainCtx = Depends(admin)):
    h = _get(ctx, hid)
    rows = ctx.db.scalars(select(WebhookEvent).where(WebhookEvent.webhook_id == h.id).order_by(WebhookEvent.id.desc()).limit(100)).all()
    return [{"id": r.id, "kind": r.kind, "outcome": r.outcome, "title": r.title, "count": r.count, "first_at": r.first_at, "last_at": r.last_at,
             "resolved_at": r.resolved_at, "proposal_id": r.proposal_id, "resolution_id": r.resolution_id} for r in rows]


@router.post("/webhooks/preview")
def preview(body: PreviewIn, ctx: BrainCtx = Depends(admin)):
    """What a template makes of a sample body, without creating anything."""
    try:
        payload = json.loads(body.body)
    except ValueError:
        raise HTTPException(400, "el cuerpo no es JSON válido") from None
    events = hooktemplates.parse(body.template, payload, {"X-GitHub-Event": body.event} if body.event else {}, _config(body.template, body.config))
    return {"events": [e.out() for e in events]}
