"""Periodic summary of what changed in a person's brains (#128), by email to whoever subscribes in My account.

- **Subscription:** per person and brain, daily or weekly (no row: never). The hour, the day of the week and the time zone are the
  person's, the same for all their brains, so one email covers every brain that is due at that moment.
- **Counts and links, never the text of the memories.** For everyone: new and invalidated facts and documents added in the period.
  For curators and above, also what waits for them: proposals and corrections (and how old the oldest is), documents with errors,
  possible contradictions (#113) and facts to review (#114). Each line links to its page when the instance has a public URL.
- **Nothing to say, nothing sent.** A brain with nothing new in the period and the same waiting counters as in its last summary is
  left out (the person already knows), and an email with no brain left is not sent.
- **When:** `run_due`, every few minutes from the notifications loop. A subscription is due once its last scheduled moment (the
  person's hour, that day or that weekday) is later than its last summary, so an instance that was stopped sends one summary when it
  comes back, not one per missed day. The period starts at the last summary, at most one day or one week back. A new subscription
  starts counting when it is made.
- Only brains the person can still read: a subscription to a brain they lost is removed. Without email (SMTP) nothing is sent and the
  subscriptions wait; a failed email is tried again on the next round.
"""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import appsettings, brand, mail
from .db import graph
from .deps import BrainCtx, current_user, effective_role
from .i18n import tr
from .models import Brain, DigestSubscription, Document, Proposal, User, now
from .roles import allows
from .store import _factory, get_db
from .userlib import mail_language

log = logging.getLogger("mimirsynth.digest")
router = APIRouter(prefix="/api/me/digest")
FREQUENCIES = ("daily", "weekly")
PERIOD = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}
WAITING = ("proposals", "corrections", "doc_errors", "conflicts", "stale")   # what a curator is waiting on: compared with the last summary
ISO = "%Y-%m-%dT%H:%M:%S.%f"   # Graphiti keeps its dates as ISO 8601 text in UTC: comparing as text is enough


def zone(name: str) -> timezone | ZoneInfo:
    try:
        return ZoneInfo(name) if name else timezone.utc
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def last_slot(at: datetime, user: User, frequency: str) -> datetime:
    """The last scheduled moment at or before `at`: the person's hour that day (daily) or on their weekday (weekly), in their zone."""
    local = at.astimezone(zone(user.timezone))
    slot = local.replace(hour=user.digest_hour, minute=0, second=0, microsecond=0)
    if frequency == "weekly":
        slot -= timedelta(days=(slot.weekday() - user.digest_weekday) % 7)
    if slot > local:
        slot -= PERIOD[frequency]
    return slot.astimezone(timezone.utc)


def _aware(d: datetime | None) -> datetime | None:
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


class _Run:
    """What one round has already counted: the waiting counters of a brain do not depend on who asks, and people with the same
    period share the counts of the graph."""

    def __init__(self):
        self.waiting: dict[int, dict] = {}
        self.graph: dict[tuple[int, datetime], dict] = {}


def _graph_counts(brain: Brain, since: datetime) -> dict:
    g = graph(brain.graph_name)
    s = since.astimezone(timezone.utc).strftime(ISO)
    one = lambda q: g.query(q, {"s": s}).result_set[0][0]  # noqa: E731
    return {"facts_new": one("MATCH (:Entity)-[r:RELATES_TO]->(:Entity) WHERE r.created_at >= $s RETURN count(r)"),
            "facts_gone": one("MATCH (:Entity)-[r:RELATES_TO]->(:Entity) WHERE r.invalid_at IS NOT NULL "
                              "AND coalesce(r.expired_at, r.invalid_at) >= $s RETURN count(r)")}


def _waiting(db: Session, brain: Brain, user: User, role: str) -> dict:
    from .attention import _conflicts, _stale
    rows = db.execute(select(Proposal.kind, func.count(), func.min(Proposal.created_at))
                      .where(Proposal.brain_id == brain.id, Proposal.status == "pending").group_by(Proposal.kind)).all()
    memory = [(n, t) for k, n, t in rows if (k or "memory") != "correction"]
    oldest = min((_aware(t) for _, t in memory if t), default=None)
    out = {"proposals": sum(n for n, _ in memory), "corrections": sum(n for k, n, _ in rows if k == "correction"),
           "oldest_days": (now() - oldest).days if oldest else None,
           "doc_errors": db.scalar(select(func.count()).select_from(Document).where(Document.brain_id == brain.id, Document.status == "error"))}
    ctx = BrainCtx(brain=brain, user=user, role=role, db=db)
    for name, fn in (("conflicts", _conflicts), ("stale", _stale)):
        try:
            out[name] = fn(ctx)
        except Exception:  # noqa: BLE001  (one counter that fails leaves the others)
            log.warning("resumen: no se pudo calcular %s del brain %s", name, brain.id, exc_info=True)
            out[name] = None
    return out


def section(db: Session, brain: Brain, user: User, role: str, since: datetime, run: _Run | None = None) -> dict:
    """The counts of one brain for one person: `new` (in the period) and, for curators and above, `waiting`."""
    run = run or _Run()
    new = {"facts_new": None, "facts_gone": None}
    try:
        if (brain.id, since) not in run.graph:
            run.graph[(brain.id, since)] = _graph_counts(brain, since)
        new = dict(run.graph[(brain.id, since)])
    except Exception:  # noqa: BLE001  (the graph is down: the rest of the summary still goes)
        log.warning("resumen: no se pudo contar el grafo del brain %s", brain.id, exc_info=True)
    new["docs_new"] = db.scalar(select(func.count()).select_from(Document).where(
        Document.brain_id == brain.id, Document.status != "deleted", Document.first_seen_at >= since))
    out = {"slug": brain.slug, "name": brain.name, "new": new, "waiting": None}
    if allows(role, "curator"):
        if brain.id not in run.waiting:
            run.waiting[brain.id] = _waiting(db, brain, user, role)
        out["waiting"] = run.waiting[brain.id]
    return out


def changed(sec: dict, last: dict | None) -> bool:
    """Whether the section has something to say: anything new in the period, or waiting counters other than in the last summary."""
    if any(sec["new"].values()):
        return True
    w = sec["waiting"] or {}
    return any(w.get(k) and w.get(k) != (last or {}).get(k) for k in WAITING)


def _link(path: str, slug: str = "") -> str:
    """` → <url>` of a page of the interface, opened on the brain `slug`; nothing without a public URL to build it."""
    base = (appsettings.get("public_url") or "").rstrip("/")
    if not base:
        return ""
    return f" → {base}{path}" + (f"{'&' if '?' in path else '?'}brain={slug}" if slug else "")


def render(user: User, sections: list[dict], since: datetime, frequency: str, lang: str) -> tuple[str, str]:
    """(subject, body) of the email: counts per brain and the links to see them, in the person's language."""
    local = since.astimezone(zone(user.timezone)).strftime("%Y-%m-%d %H:%M")
    subject = tr("{{app}}: lo que ha cambiado en tus brains", lang, app=brand.NAME)
    lines = [tr("Hola {{name}},", lang, name=user.display_name or user.name or user.email or ""), "",
             tr("Esto es lo que ha cambiado desde el {{since}}:", lang, since=local) if frequency == "weekly"
             else tr("Esto es lo que ha cambiado desde ayer, {{since}}:", lang, since=local), ""]
    for s in sections:
        lines.append(f"## {s['name']}")
        n, w, slug = s["new"], s["waiting"] or {}, s["slug"]
        if n.get("facts_new") or n.get("facts_gone"):
            lines.append("- " + tr("Hechos nuevos: {{new}} · invalidados: {{gone}}", lang, new=n.get("facts_new") or 0, gone=n.get("facts_gone") or 0)
                         + _link("/hechos", slug))
        if n.get("docs_new"):
            lines.append("- " + tr("Documentos nuevos: {{n}}", lang, n=n["docs_new"]) + _link("/conocimiento", slug))
        if w.get("proposals"):
            old = w.get("oldest_days")
            lines.append("- " + (tr("Propuestas por revisar: {{n}} (la más antigua, de hace {{days}} días)", lang, n=w["proposals"], days=old)
                                 if old else tr("Propuestas por revisar: {{n}}", lang, n=w["proposals"])) + _link("/propuestas", slug))
        if w.get("corrections"):
            lines.append("- " + tr("Correcciones por revisar: {{n}}", lang, n=w["corrections"]) + _link("/propuestas", slug))
        if w.get("doc_errors"):
            lines.append("- " + tr("Documentos con errores: {{n}}", lang, n=w["doc_errors"]) + _link("/conocimiento", slug))
        if w.get("conflicts"):
            lines.append("- " + tr("Posibles contradicciones: {{n}}", lang, n=w["conflicts"]) + _link("/calidad?tab=conflicts", slug))
        if w.get("stale"):
            lines.append("- " + tr("Hechos a revisar: {{n}}", lang, n=w["stale"]) + _link("/calidad?tab=stale", slug))
        if lines[-1] == f"## {s['name']}":   # only in a preview: a summary leaves such a brain out
            lines.append("- " + tr("Sin novedades.", lang))
        lines.append("")
    base = (appsettings.get("public_url") or "").rstrip("/")
    lines += [tr("Solo lleva recuentos: el contenido está en la aplicación.", lang),
              tr("Para cambiar o dejar de recibir este resumen: {{url}}", lang, url=f"{base}/cuenta?seccion=resumen") if base
              else tr("Para cambiar o dejar de recibir este resumen: Mi cuenta → Resumen por correo.", lang)]
    return subject, "\n".join(lines) + "\n"


def _readable(db: Session, user: User, brain: Brain) -> str | None:
    role = effective_role(db, user, brain)
    return role if allows(role, "reader") else None


def run_due(at: datetime | None = None) -> int:
    """Sends the summaries that are due. Returns how many emails went out. Never raises."""
    if not mail.configured():
        return 0
    at, sent, run = at or now(), 0, _Run()
    try:
        with _factory()() as db:
            users = db.scalars(select(User).where(User.id.in_(select(DigestSubscription.user_id)), User.status == "active")).all()
            for user in users:
                try:
                    sent += _for_user(db, user, at, run)
                except Exception:  # noqa: BLE001  (one person's summary does not stop the others)
                    db.rollback()
                    log.exception("resumen: falló el de la persona %s", user.id)
    except Exception:  # noqa: BLE001
        log.exception("resumen: no se pudieron preparar los resúmenes")
    return sent


def _for_user(db: Session, user: User, at: datetime, run: _Run) -> int:
    if not user.email:
        return 0
    subs = db.scalars(select(DigestSubscription).where(DigestSubscription.user_id == user.id)).all()
    due, sections, starts = [], [], []
    for sub in subs:
        slot = last_slot(at, user, sub.frequency)
        last = _aware(sub.last_sent_at)
        if last and last >= slot:
            continue
        brain = db.get(Brain, sub.brain_id)
        role = _readable(db, user, brain) if brain else None
        if not role:
            db.delete(sub)
            continue
        since = max(last or slot - PERIOD[sub.frequency], slot - PERIOD[sub.frequency])
        sec = section(db, brain, user, role, since, run)
        due.append((sub, sec))
        if changed(sec, sub.last_counts):
            sections.append(sec)
            starts.append((since, sub.frequency))
    if sections:
        since = min(s for s, _ in starts)
        frequency = "weekly" if any(f == "weekly" for _, f in starts) else "daily"
        subject, body = render(user, sections, since, frequency, mail_language(user))
        mail.send(user.email, subject, body)   # raises: nothing is marked and the next round tries again
    for sub, sec in due:
        sub.last_sent_at = at
        sub.last_counts = {k: (sec["waiting"] or {}).get(k) for k in WAITING}
    db.commit()
    return 1 if sections else 0


# ---- My account ----
class DigestIn(BaseModel):
    hour: int = Field(8, ge=0, le=23)
    weekday: int = Field(0, ge=0, le=6)   # 0 = Monday
    timezone: str = Field("", max_length=64)
    brains: dict[str, str] = Field(default_factory=dict)   # slug -> daily | weekly | never


def _my_brains(db: Session, user: User) -> list[tuple[Brain, str]]:
    out = []
    for b in db.scalars(select(Brain).order_by(Brain.name)):
        role = _readable(db, user, b)
        if role:
            out.append((b, role))
    return out


def _out(db: Session, user: User) -> dict:
    subs = {s.brain_id: s.frequency for s in db.scalars(select(DigestSubscription).where(DigestSubscription.user_id == user.id))}
    return {"mail": mail.configured(), "email": user.email, "hour": user.digest_hour, "weekday": user.digest_weekday, "timezone": user.timezone,
            "brains": [{"slug": b.slug, "name": b.name, "role": r, "frequency": subs.get(b.id, "never")} for b, r in _my_brains(db, user)]}


@router.get("")
def get_digest(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(db, user)


@router.put("")
def set_digest(body: DigestIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.timezone:
        try:
            ZoneInfo(body.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, "zona horaria desconocida") from None
    if any(f not in (*FREQUENCIES, "never") for f in body.brains.values()):
        raise HTTPException(422, "frecuencia no válida: daily, weekly o never")
    user.digest_hour, user.digest_weekday, user.timezone = body.hour, body.weekday, body.timezone
    mine = {b.slug: b for b, _ in _my_brains(db, user)}
    subs = {s.brain_id: s for s in db.scalars(select(DigestSubscription).where(DigestSubscription.user_id == user.id))}
    for slug, freq in body.brains.items():
        b = mine.get(slug)
        if not b:
            raise HTTPException(404, "brain no encontrado")
        s = subs.get(b.id)
        if freq == "never":
            if s:
                db.delete(s)
        elif s:
            s.frequency = freq
        else:
            db.add(DigestSubscription(user_id=user.id, brain_id=b.id, frequency=freq, last_sent_at=now()))  # counts from now
    db.commit()
    return _out(db, user)


@router.get("/preview")
def preview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """What a summary of the subscribed brains would say now, over their period, even with nothing new: to see what it looks like."""
    subs = db.scalars(select(DigestSubscription).where(DigestSubscription.user_id == user.id)).all()
    at, run, sections, frequency = now(), _Run(), [], "daily"
    since = at - PERIOD["daily"]
    for sub in subs:
        brain = db.get(Brain, sub.brain_id)
        role = _readable(db, user, brain) if brain else None
        if not role:
            continue
        s = at - PERIOD[sub.frequency]
        since, frequency = min(since, s), ("weekly" if sub.frequency == "weekly" else frequency)
        sections.append(section(db, brain, user, role, s, run))
    if not sections:
        raise HTTPException(409, "no estás suscrito al resumen de ningún brain")
    subject, body = render(user, sections, since, frequency, mail_language(user))
    return {"subject": subject, "body": body}
