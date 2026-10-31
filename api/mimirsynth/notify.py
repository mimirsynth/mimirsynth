"""Notificaciones: un único punto de emisión (`emit`/`resolve`), avisos agrupados, cola de envíos con reintentos y comprobaciones de estado.

Un aviso se guarda siempre (es lo que muestra la campana de la interfaz) y, además, se encola un envío por cada canal que lo admite (severidad y eventos).
Un problema que se repite (mismo evento y clave) no genera avisos nuevos: se cuenta, y solo se vuelve a enviar pasado el «aviso repetido».
`resolve` cierra el problema y avisa de la recuperación por los canales que recibieron el aviso. `emit` y `resolve` nunca lanzan: un fallo al avisar no debe romper lo que se estaba haciendo."""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from . import appsettings, brand, notify_channels as ch
from .models import Brain, Notification, NotifyChannel, NotifyDelivery, now
from .store import _factory

log = logging.getLogger("mimirsynth.notify")

# evento -> (severidad por defecto, descripción). La clave es lo que se elige en cada canal.
EVENTS = {
    "model.unavailable": ("critical", "Un modelo de IA (LLM, embeddings o decisor) no responde"),
    "ingest.failed": ("warning", "Una propuesta aprobada no se pudo ingerir tras los reintentos"),
    "job.failed": ("warning", "Un trabajo en segundo plano ha fallado"),
    "docsource.error": ("warning", "Una fuente de documentos no se pudo sincronizar"),
    "graph.down": ("critical", "El grafo (FalkorDB) no responde"),
    "update.available": ("info", "Hay una versión nueva de MimirSynth"),
    "security.lockout": ("warning", "Una cuenta se ha bloqueado por intentos fallidos"),
    "reindex.orphan": ("warning", "Un cambio de modelo de embeddings lleva tiempo sin terminar y sus vectores sombra ocupan memoria"),
    "refquery.regressed": ("warning", "Las consultas de referencia de un brain empeoran tras un cambio de modelo de embeddings"),
    "conflicts.found": ("info", "Hay hechos vigentes que se contradicen en una relación de un solo valor"),
    "token.expiring": ("info", "Un token de API caduca en pocos días"),
}
BACKOFF = [60, 300, 1800, 7200, 43200]  # segundos entre reintentos de un envío; tras el último se da por fallido
MAX_ATTEMPTS = len(BACKOFF) + 1
_RANK = {s: i for i, s in enumerate(ch.SEVERITIES)}


def _aware(d: datetime | None) -> datetime | None:
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def _hhmm(v: str) -> tuple[int, int] | None:
    try:
        h, m = str(v).strip().split(":")
        return (int(h), int(m)) if 0 <= int(h) < 24 and 0 <= int(m) < 60 else None
    except ValueError:
        return None


def quiet_until(at: datetime) -> datetime | None:
    """Si `at` cae en las horas de silencio, cuándo terminan (hora del servidor); si no, None."""
    a, b = _hhmm(appsettings.get("notify_quiet_start")), _hhmm(appsettings.get("notify_quiet_end"))
    if not a or not b or a == b:
        return None
    local = at.astimezone()
    cur = (local.hour, local.minute)
    inside = (a <= cur < b) if a < b else (cur >= a or cur < b)
    if not inside:
        return None
    end = local.replace(hour=b[0], minute=b[1], second=0, microsecond=0)
    if end <= local:
        end += timedelta(days=1)
    return end.astimezone(timezone.utc)


def _matches(c: NotifyChannel, event: str, severity: str) -> bool:
    return c.enabled and _RANK.get(severity, 1) >= _RANK.get(c.min_severity, 1) and (not c.events or event in c.events)


def _queue(db, n: Notification, kind: str, only: set[int] | None = None) -> int:
    t = now()
    until = quiet_until(t) if n.severity != "critical" else None
    k = 0
    for c in db.scalars(select(NotifyChannel).where(NotifyChannel.enabled.is_(True))):
        if (only is not None and c.id not in only) or (only is None and not _matches(c, n.event, n.severity)):
            continue
        db.add(NotifyDelivery(notification_id=n.id, channel_id=c.id, kind=kind, next_try_at=until or t)); k += 1
    return k


def emit(event: str, title: str, body: str = "", *, severity: str | None = None, brain_id: int | None = None, key: str = "") -> int | None:
    """Registra un problema (o un aviso) y lo encola para los canales. Devuelve el id del aviso, o None si falló. No lanza."""
    try:
        sev = severity or EVENTS.get(event, ("warning", ""))[0]
        t = now()
        with _factory()() as db:
            n = db.scalar(select(Notification).where(Notification.event == event, Notification.key == key, Notification.resolved_at.is_(None)).order_by(Notification.id.desc()))
            if n:
                n.count += 1
                last = _aware(n.last_at)
                again = last is not None and t - last >= timedelta(minutes=int(appsettings.get("notify_cooldown_minutes")))
                n.body, n.severity = body[:2000] or n.body, sev
                if again:  # el problema sigue abierto: recordatorio por los canales
                    n.last_at = t
                    _queue(db, n, "alert")
                db.commit()
                return n.id
            n = Notification(event=event, severity=sev, title=title[:200], body=body[:2000], brain_id=brain_id, key=key[:120], ts=t, last_at=t)
            db.add(n); db.flush()
            _queue(db, n, "alert")
            db.commit()
            return n.id
    except Exception:  # noqa: BLE001
        log.exception("no se pudo registrar el aviso %s", event)
        return None


def resolve(event: str, key: str = "", body: str = "") -> bool:
    """Cierra el problema abierto (si lo hay) y avisa de la recuperación a quien recibió el aviso. No lanza."""
    try:
        with _factory()() as db:
            n = db.scalar(select(Notification).where(Notification.event == event, Notification.key == key, Notification.resolved_at.is_(None)).order_by(Notification.id.desc()))
            if not n:
                return False
            n.resolved_at = now()
            if body:
                n.body = body[:2000]
            sent = {d.channel_id for d in db.scalars(select(NotifyDelivery).where(NotifyDelivery.notification_id == n.id, NotifyDelivery.kind == "alert"))}
            if sent and n.severity != "info":
                _queue(db, n, "recovery", only=sent)
            db.commit()
            return True
    except Exception:  # noqa: BLE001
        log.exception("no se pudo resolver el aviso %s", event)
        return False


def build_message(db, n: Notification, kind: str) -> ch.Message:
    brain = db.get(Brain, n.brain_id) if n.brain_id else None
    title = f"Recuperado: {n.title}" if kind == "recovery" else n.title
    return ch.Message(event=n.event, severity=n.severity, title=title, body="" if kind == "recovery" else n.body, kind=kind, brain=brain.name if brain else "",
                      count=n.count, instance=f"{brand.NAME} · {appsettings.get('public_url').rstrip('/')}".rstrip(" ·"), ts=(_aware(n.last_at) or now()).isoformat())


def deliver(db, c: NotifyChannel, m: ch.Message) -> None:
    from .secretbox import unseal
    ch.SENDERS[c.kind](dict(c.config or {}), unseal(c.secret) if c.secret else "", m)


def process_due(limit: int = 25) -> int:
    """Envía los envíos pendientes cuya hora ha llegado. Un fallo reprograma con espera creciente; agotados los intentos queda como fallido."""
    done = 0
    with _factory()() as db:
        due = list(db.scalars(select(NotifyDelivery).where(NotifyDelivery.status == "pending", NotifyDelivery.next_try_at <= now()).order_by(NotifyDelivery.id).limit(limit)))
        for d in due:
            d.attempts += 1
            try:
                deliver(db, d.channel, build_message(db, d.notification, d.kind))
                d.status, d.sent_at, d.last_error = "sent", now(), ""
            except Exception as e:  # noqa: BLE001
                d.last_error = (str(e) or e.__class__.__name__)[:500]
                if d.attempts >= MAX_ATTEMPTS:
                    d.status = "failed"
                else:
                    d.next_try_at = now() + timedelta(seconds=BACKOFF[d.attempts - 1])
                log.warning("envío %s por «%s» falló (intento %s): %s", d.id, d.channel.name, d.attempts, d.last_error)
            done += 1
        db.commit()
    return done


def prune() -> int:
    with _factory()() as db:
        cut = now() - timedelta(days=int(appsettings.get("notify_keep_days")))
        r = db.execute(delete(Notification).where(Notification.ts < cut, Notification.resolved_at.is_not(None)))
        r2 = db.execute(delete(Notification).where(Notification.ts < cut - timedelta(days=30)))  # los abiertos eternos también acaban
        db.commit()
        return (r.rowcount or 0) + (r2.rowcount or 0)


# ---- comprobaciones de estado ----
_FAILS: dict[str, int] = {}   # fallos seguidos de cada comprobación (en memoria: un reinicio empieza de cero)


def _fail(event: str, title: str, body: str, key: str) -> None:
    """Un fallo aislado no avisa: hacen falta `notify_health_failures` seguidos. Así un 500 o un timeout puntual de un proveedor no genera un aviso (y su correo de recuperación)."""
    k = f"{event}:{key}"
    _FAILS[k] = _FAILS.get(k, 0) + 1
    if _FAILS[k] >= int(appsettings.get("notify_health_failures")):
        emit(event, title, body, key=key)


def _ok(event: str, key: str) -> None:
    _FAILS.pop(f"{event}:{key}", None)
    resolve(event, key)


def check_health() -> None:
    """Grafo y modelos de IA: emite el problema si no responden `notify_health_failures` veces seguidas y lo resuelve cuando vuelven. Los fallos de PostgreSQL no se pueden avisar desde dentro (no habría dónde guardarlos): vigílalo con un monitor externo."""
    from .db import list_graphs
    try:
        list_graphs()
        _ok("graph.down", "falkordb")
    except Exception as e:  # noqa: BLE001
        _fail("graph.down", "El grafo (FalkorDB) no responde", str(e)[:300], "falkordb")
    try:
        from . import decider as _decider
        from .aistatus import _llm_ping
        from .deciders_admin import default_decider
        from .embeddings_admin import _probe, default_embedding
        from .llm import default_engine
        from .secretbox import unseal
        with _factory()() as db:
            probes = []
            if (e := default_engine(db)):
                probes.append(("llm", e.name, lambda e=e: _llm_ping(e.base_url, e.model, unseal(e.api_key_enc))))
            if (e := default_embedding(db)):
                probes.append(("embedding", e.name, lambda e=e: _probe(e.base_url, e.model, unseal(e.api_key_enc))))
            if (e := default_decider(db)):
                probes.append(("decider", e.name, lambda e=e: _decider.decide(e.base_url, e.model, unseal(e.api_key_enc), "x", "¿ok?", ["Sí", "No"], timeout=30)))
    except Exception:  # noqa: BLE001
        log.exception("no se pudieron preparar las comprobaciones de los modelos")
        return
    names = {"llm": "LLM", "embedding": "embeddings", "decider": "decisor"}
    for kind, name, fn in probes:
        try:
            fn()
            _ok("model.unavailable", kind)
        except Exception as e:  # noqa: BLE001
            _fail("model.unavailable", f"El modelo de {names[kind]} no responde", f"Motor «{name}»: {str(e)[:250]}", kind)


def _newer(latest: str, current: str) -> bool:
    def v(s):
        return tuple(int(x) for x in s.lstrip("v").split("-")[0].split(".")[:3] if x.isdigit())
    try:
        return v(latest) > v(current) and "-" not in latest.lstrip("v")
    except ValueError:
        return False


def check_update(current: str) -> None:
    if appsettings.get("notify_update_check") != "yes":
        return
    try:
        import httpx
        r = httpx.get("https://api.github.com/repos/mimirsynth/mimirsynth/releases/latest", timeout=15, headers={"Accept": "application/vnd.github+json"})
        r.raise_for_status()
        tag = str(r.json().get("tag_name", ""))
        if tag and _newer(tag, current):
            emit("update.available", f"Versión {tag.lstrip('v')} disponible", f"Estás en la {current}. Notas: https://github.com/mimirsynth/mimirsynth/releases/tag/{tag}", key=tag)
    except Exception as e:  # noqa: BLE001
        log.info("no se pudo comprobar si hay versión nueva: %s", e)


async def worker(version: str = "0.0.0") -> None:
    """Hilo de fondo: envía lo pendiente cada pocos segundos, comprueba el estado y la versión, y poda lo antiguo."""
    from . import jobs
    if jobs.INLINE:  # pruebas: nada en segundo plano
        return
    await asyncio.sleep(15)
    last_health = last_update = last_prune = last_reindex = last_conflicts = 0.0
    while True:
        try:
            await asyncio.to_thread(process_due)
            t = time.monotonic()
            mins = int(appsettings.get("notify_health_minutes"))
            if mins > 0 and t - last_health >= mins * 60:
                last_health = t
                await asyncio.to_thread(check_health)
            if t - last_update >= 86400:
                last_update = t
                await asyncio.to_thread(check_update, version)
            if t - last_prune >= 3600:
                last_prune = t
                await asyncio.to_thread(prune)
            if t - last_reindex >= 600:
                last_reindex = t
                from . import reembed
                await asyncio.to_thread(reembed.check_orphan)
            if t - last_conflicts >= 86400:
                last_conflicts = t
                from . import conflicts, memory
                await asyncio.to_thread(conflicts.check_all)
                await asyncio.to_thread(memory.check_expiring)
                from . import retention
                await asyncio.to_thread(retention.run_all)
        except Exception:  # noqa: BLE001
            log.exception("fallo en el ciclo de notificaciones")
        await asyncio.sleep(10)
