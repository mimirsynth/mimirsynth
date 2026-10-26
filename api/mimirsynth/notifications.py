"""API de notificaciones: la campana (avisos visibles para cada persona) y, para administradores de la instancia, canales, historial de envíos y pruebas."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import notify
from . import notify_channels as ch
from .deps import audit, current_user, require_admin
from .models import Membership, Notification, NotifyChannel, NotifyDelivery, NotifyRead, User, now
from .roles import rank
from .secretbox import seal
from .store import get_db

router = APIRouter(prefix="/api/notifications")


def _visible(db: Session, user: User):
    """Condición de visibilidad: el administrador ve todo; un curador o administrador de brain, los avisos de sus brains (y ninguno de la instancia)."""
    if user.is_admin:
        return None
    ids = [m.brain_id for m in db.scalars(select(Membership).where(Membership.user_id == user.id)) if rank(m.role) >= rank("curator")]
    return Notification.brain_id.in_(ids) if ids else Notification.id < 0


def _out(n: Notification, last_read: int, brains: dict[int, str]) -> dict:
    return {"id": n.id, "ts": n.ts, "last_at": n.last_at, "event": n.event, "severity": n.severity, "title": n.title, "body": n.body, "count": n.count, "key": n.key,
            "brain": brains.get(n.brain_id), "resolved_at": n.resolved_at, "unread": n.id > last_read}


@router.get("")
def inbox(unread: bool = False, limit: int = 50, offset: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .models import Brain
    cond = _visible(db, user)
    last = db.scalar(select(NotifyRead.last_id).where(NotifyRead.user_id == user.id)) or 0
    q = select(Notification)
    if cond is not None:
        q = q.where(cond)
    if unread:
        q = q.where(Notification.id > last)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(db.scalars(q.order_by(Notification.last_at.desc(), Notification.id.desc()).limit(min(limit, 200)).offset(offset)))
    brains = {b.id: b.name for b in db.scalars(select(Brain))}
    return {"total": total, "items": [_out(n, last, brains) for n in rows]}


@router.get("/summary")
def summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Lo que pinta la campana: avisos sin leer y cuántos siguen abiertos (problemas sin resolver)."""
    cond = _visible(db, user)
    last = db.scalar(select(NotifyRead.last_id).where(NotifyRead.user_id == user.id)) or 0
    base = select(func.count()).select_from(Notification)
    if cond is not None:
        base = base.where(cond)
    unread = db.scalar(base.where(Notification.id > last)) or 0
    openq = db.scalar(base.where(Notification.resolved_at.is_(None))) or 0
    worst = None
    if openq:
        q = select(Notification.severity).where(Notification.resolved_at.is_(None))
        if cond is not None:
            q = q.where(cond)
        sevs = set(db.scalars(q))
        worst = "critical" if "critical" in sevs else "warning" if "warning" in sevs else "info"
    return {"unread": unread, "open": openq, "worst": worst}


@router.post("/read")
def mark_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    cond = _visible(db, user)
    q = select(func.max(Notification.id))
    if cond is not None:
        q = q.where(cond)
    top = db.scalar(q) or 0
    r = db.get(NotifyRead, user.id)
    if r:
        r.last_id = max(r.last_id, top)
    else:
        db.add(NotifyRead(user_id=user.id, last_id=top))
    db.commit()
    return {"ok": True}


# ---- administración ----
@router.get("/catalog")
def catalog(_: User = Depends(require_admin)):
    return {"events": [{"key": k, "severity": v[0], "label": v[1]} for k, v in notify.EVENTS.items()], "kinds": ch.FIELDS, "severities": list(ch.SEVERITIES)}


class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str
    config: dict = {}
    secret: str | None = None  # None o vacío al editar = conservar el guardado
    enabled: bool = True
    min_severity: str = "warning"
    events: list[str] = []


def _clean(body: ChannelIn) -> tuple[dict, list[str]]:
    if body.kind not in ch.KINDS:
        raise HTTPException(400, "tipo de canal no válido")
    if body.min_severity not in ch.SEVERITIES:
        raise HTTPException(400, "severidad no válida")
    allowed = ch.FIELDS[body.kind]["config"]
    cfg = {k: str(v).strip() for k, v in body.config.items() if k in allowed and str(v).strip()}
    if "url" in allowed and cfg.get("url"):
        if not cfg["url"].startswith(("http://", "https://")):
            raise HTTPException(400, "la URL debe empezar por http:// o https://")
    for k in ("thread_id",):
        if k in cfg and not cfg[k].lstrip("-").isdigit():
            raise HTTPException(400, "el tema (thread_id) debe ser un número")
    return cfg, [e for e in body.events if e in notify.EVENTS]


def _chan(c: NotifyChannel, last: dict | None = None) -> dict:
    return {"id": c.id, "name": c.name, "kind": c.kind, "config": c.config or {}, "has_secret": bool(c.secret), "enabled": c.enabled, "min_severity": c.min_severity,
            "events": c.events or [], "created_at": c.created_at, "last": last}


def _last_by_channel(db: Session) -> dict[int, dict]:
    out = {}
    for d in db.scalars(select(NotifyDelivery).order_by(NotifyDelivery.id)):
        out[d.channel_id] = {"status": d.status, "at": d.sent_at or d.next_try_at, "error": d.last_error}
    return out


@router.get("/channels")
def list_channels(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    last = _last_by_channel(db)
    return [_chan(c, last.get(c.id)) for c in db.scalars(select(NotifyChannel).order_by(NotifyChannel.name))]


@router.post("/channels", status_code=201)
def create_channel(body: ChannelIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    cfg, events = _clean(body)
    if db.scalar(select(NotifyChannel).where(NotifyChannel.name == body.name.strip())):
        raise HTTPException(409, "ya hay un canal con ese nombre")
    c = NotifyChannel(name=body.name.strip(), kind=body.kind, config=cfg, secret=seal(body.secret) if body.secret else "", enabled=body.enabled, min_severity=body.min_severity, events=events)
    db.add(c); db.commit()
    audit(db, admin, "notify.channel.create", None, name=c.name, kind=c.kind)
    return _chan(c)


@router.put("/channels/{cid}")
def update_channel(cid: int, body: ChannelIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.get(NotifyChannel, cid)
    if not c:
        raise HTTPException(404, "canal no encontrado")
    if body.kind != c.kind:
        raise HTTPException(400, "el tipo de un canal no se cambia: crea otro")
    cfg, events = _clean(body)
    other = db.scalar(select(NotifyChannel).where(NotifyChannel.name == body.name.strip(), NotifyChannel.id != cid))
    if other:
        raise HTTPException(409, "ya hay un canal con ese nombre")
    c.name, c.config, c.enabled, c.min_severity, c.events = body.name.strip(), cfg, body.enabled, body.min_severity, events
    if body.secret:
        c.secret = seal(body.secret)
    db.commit()
    audit(db, admin, "notify.channel.update", None, name=c.name, kind=c.kind)
    return _chan(c)


@router.delete("/channels/{cid}")
def delete_channel(cid: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from sqlalchemy import delete
    c = db.get(NotifyChannel, cid)
    if not c:
        raise HTTPException(404, "canal no encontrado")
    db.execute(delete(NotifyDelivery).where(NotifyDelivery.channel_id == cid))
    name, kind = c.name, c.kind
    db.delete(c); db.commit()
    audit(db, admin, "notify.channel.delete", None, name=name, kind=kind)
    return {"ok": True}


@router.post("/channels/{cid}/test")
def test_channel(cid: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Envía ahora un aviso de prueba por el canal (no cuenta como aviso del sistema) y devuelve el resultado."""
    c = db.get(NotifyChannel, cid)
    if not c:
        raise HTTPException(404, "canal no encontrado")
    m = ch.Message(event="test", severity="info", title="Prueba de notificaciones", body="Si ves esto, el canal funciona.", instance="MimirSynth")
    try:
        notify.deliver(db, c, m)
    except Exception as e:  # noqa: BLE001
        audit(db, admin, "notify.channel.test", None, name=c.name, ok=False)
        return {"ok": False, "error": (str(e) or e.__class__.__name__)[:300]}
    audit(db, admin, "notify.channel.test", None, name=c.name, ok=True)
    return {"ok": True}


@router.get("/deliveries")
def deliveries(status: str = "", limit: int = 50, offset: int = 0, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    q = select(NotifyDelivery)
    if status in ("pending", "sent", "failed"):
        q = q.where(NotifyDelivery.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(NotifyDelivery.id.desc()).limit(min(limit, 200)).offset(offset))
    return {"total": total, "items": [{"id": d.id, "channel": d.channel.name, "kind": d.kind, "status": d.status, "attempts": d.attempts, "error": d.last_error, "title": d.notification.title,
                                       "severity": d.notification.severity, "created_at": d.created_at, "sent_at": d.sent_at, "next_try_at": d.next_try_at} for d in rows]}


@router.post("/deliveries/{did}/retry")
def retry(did: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    d = db.get(NotifyDelivery, did)
    if not d or d.status != "failed":
        raise HTTPException(404, "envío no encontrado o no fallido")
    d.status, d.attempts, d.next_try_at = "pending", 0, now()
    db.commit()
    return {"ok": True}
