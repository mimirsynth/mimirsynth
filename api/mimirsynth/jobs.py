"""Cola general de trabajos en segundo plano. Cada trabajo queda registrado (estado, progreso, salida, reintentos) y se ejecuta en un
pool acotado por tipo. Los manejadores se registran por tipo y reciben un JobCtx con el que informan del progreso."""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import delete, select

from . import appsettings
from .config import settings
from .models import Job
from .store import _factory

log = logging.getLogger("mimirsynth.jobs")
LOG_LINES = 60
KEEP_PER_BRAIN = 2000


class Cancelled(Exception):
    """El manejador la lanza (vía JobCtx.check) cuando alguien ha cancelado el trabajo."""


@dataclass
class Kind:
    fn: Callable
    label: str
    limit: int = 2
    resume: bool = False  # se relanza solo si el servicio se reinicia con el trabajo a medias (debe ser idempotente)


_KINDS: dict[str, Kind] = {}
_POOLS: dict[str, ThreadPoolExecutor] = {}
_CANCEL: set[int] = set()
_LOCK = threading.Lock()
INLINE = False  # pruebas: ejecuta cada trabajo en el hilo que lo encola, sin pool


def register(kind: str, label: str, limit: int = 2, resume: bool = False):
    def deco(fn):
        _KINDS[kind] = Kind(fn, label, limit, resume)
        return fn
    return deco


def label_of(kind: str) -> str:
    return _KINDS[kind].label if kind in _KINDS else kind


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JobCtx:
    """Lo que ve un manejador: parámetros, progreso, notas y cancelación."""

    def __init__(self, job_id: int, brain_id: int | None, params: dict):
        self.id, self.brain_id, self.params = job_id, brain_id, params
        self._last = 0.0
        self._pending: dict = {}

    def check(self) -> None:
        if self.id in _CANCEL:
            raise Cancelled()

    def progress(self, done: int, total: int | None = None, message: str | None = None) -> None:
        self._pending["progress_done"] = int(done)
        if total is not None:
            self._pending["progress_total"] = int(total)
        if message is not None:
            self._pending["message"] = message[:300]
        if time.monotonic() - self._last >= 1.0:
            self.flush()

    def note(self, msg: str) -> None:
        """Línea de registro visible en el detalle del trabajo."""
        self.flush(note=msg)

    def retrying(self, msg: str) -> None:
        """Anota un reintento interno (límite de tasa, error transitorio…) y sube el contador de intentos."""
        self.flush(note=msg, bump_attempt=True)

    def flush(self, note: str | None = None, bump_attempt: bool = False) -> None:
        self._last = time.monotonic()
        with _factory()() as db:
            j = db.get(Job, self.id)
            if not j:
                return
            for k, v in self._pending.items():
                setattr(j, k, v)
            self._pending = {}
            if note:
                j.log = (list(j.log or []) + [{"t": _now().isoformat(timespec="seconds"), "msg": note[:400]}])[-LOG_LINES:]
            if bump_attempt:
                j.attempts = (j.attempts or 1) + 1
            db.commit()


def _pool(kind: str) -> ThreadPoolExecutor:
    with _LOCK:
        if kind not in _POOLS:
            _POOLS[kind] = ThreadPoolExecutor(max_workers=_KINDS[kind].limit, thread_name_prefix=f"job-{kind}")
        return _POOLS[kind]


def submit(kind: str, brain_id: int | None, params: dict, title: str, user_id: int | None = None, dedupe_key: str = "", retry_of: int | None = None) -> int:
    """Encola un trabajo. Con `dedupe_key`, si ya hay uno igual en cola o en marcha devuelve ese en lugar de duplicarlo."""
    if kind not in _KINDS:
        raise ValueError(f"tipo de trabajo desconocido: {kind}")
    with _factory()() as db:
        if dedupe_key:
            dup = db.scalar(select(Job).where(Job.dedupe_key == dedupe_key, Job.status.in_(("queued", "running"))))
            if dup:
                return dup.id
        j = Job(brain_id=brain_id, kind=kind, title=title[:300], params=params, created_by=user_id, dedupe_key=dedupe_key, retry_of=retry_of)
        db.add(j)
        db.commit()
        jid = j.id
    _enqueue(jid, kind)
    return jid


def _enqueue(jid: int, kind: str) -> None:
    if INLINE:
        _run(jid)
        return
    _pool(kind).submit(_run, jid)


def _run(jid: int) -> None:
    with _factory()() as db:
        j = db.get(Job, jid)
        if not j or j.status != "queued":  # cancelado mientras esperaba
            return
        kind, brain_id, params = j.kind, j.brain_id, dict(j.params or {})
        j.status, j.started_at = "running", _now()
        db.commit()
    ctx = JobCtx(jid, brain_id, params)
    status, error, result = "done", "", None
    try:
        result = _KINDS[kind].fn(ctx, params)
    except Cancelled:
        status, error = "cancelled", "cancelado por un usuario"
    except Exception as e:  # noqa: BLE001
        log.exception("trabajo %s (%s) fallido", jid, kind)
        status, error = "failed", (str(e) or e.__class__.__name__)[:1000]
    _CANCEL.discard(jid)
    ctx.flush()
    with _factory()() as db:
        j = db.get(Job, jid)
        if j:
            j.status, j.error, j.finished_at = status, error, _now()
            if isinstance(result, dict):
                j.result = result
            if status == "done" and j.progress_total:
                j.progress_done = j.progress_total
            db.commit()


def cancel(jid: int) -> str:
    """En cola: se cancela al instante. En marcha: se avisa al manejador, que para en su próximo punto de control."""
    with _factory()() as db:
        j = db.get(Job, jid)
        if not j or j.status not in ("queued", "running"):
            return "finished"
        if j.status == "queued":
            j.status, j.finished_at, j.error = "cancelled", _now(), "cancelado por un usuario"
            db.commit()
            return "cancelled"
    _CANCEL.add(jid)
    return "cancelling"


def retry(jid: int, user_id: int | None = None) -> int:
    with _factory()() as db:
        j = db.get(Job, jid)
        if not j or j.status not in ("failed", "cancelled"):
            raise ValueError("solo se reintentan trabajos fallidos o cancelados")
        args = (j.kind, j.brain_id, dict(j.params or {}), j.title, user_id, j.dedupe_key, j.id)
    return submit(*args[:5], dedupe_key=args[5], retry_of=args[6])


def recover() -> dict:
    """Al arrancar: lo que estaba a medias se marca como interrumpido; los tipos idempotentes se relanzan."""
    out = {"interrupted": 0, "resumed": 0}
    with _factory()() as db:
        stale = db.scalars(select(Job).where(Job.status.in_(("queued", "running")))).all()
        todo = []
        for j in stale:
            j.status, j.finished_at, j.error = "failed", _now(), "interrumpido por un reinicio del servicio"
            out["interrupted"] += 1
            if j.kind in _KINDS and _KINDS[j.kind].resume:
                todo.append((j.kind, j.brain_id, dict(j.params or {}), j.title, j.created_by, j.dedupe_key, j.id))
        db.commit()
    for kind, brain_id, params, title, uid, dk, rid in todo:
        submit(kind, brain_id, params, title, uid, dk, rid)
        out["resumed"] += 1
    return out


def prune() -> int:
    """Quita los trabajos terminados antiguos: los reescaneos programados que acabaron bien (sin autor, repetitivos) a los `jobs_keep_scheduled_days`
    y el resto a los `jobs_keep_days`. Los fallidos y cancelados siempre se conservan el plazo largo, porque son los que alguien puede querer ver."""
    now = _now()
    with _factory()() as db:
        noise = db.execute(delete(Job).where(Job.status == "done", Job.created_by.is_(None), Job.dedupe_key.like("doc.scan:%"), Job.finished_at < now - timedelta(days=appsettings.get("jobs_keep_scheduled_days"))))
        old = db.execute(delete(Job).where(Job.status.in_(("done", "failed", "cancelled")), Job.finished_at < now - timedelta(days=appsettings.get("jobs_keep_days"))))
        db.commit()
        return (noise.rowcount or 0) + (old.rowcount or 0)


def out(j: Job, detail: bool = False, user_name: str = "") -> dict:
    d = {"id": j.id, "kind": j.kind, "label": label_of(j.kind), "title": j.title, "status": j.status, "done": j.progress_done, "total": j.progress_total,
         "message": j.message, "error": j.error, "attempts": j.attempts, "retry_of": j.retry_of, "user": user_name,
         "created_at": j.created_at, "started_at": j.started_at, "finished_at": j.finished_at}
    if detail:
        d.update(params=j.params, log=j.log or [], result=j.result)
    return d
