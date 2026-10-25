"""Limitador de peticiones de ventana deslizante para el inicio de sesión, el doble factor y la recuperación de contraseña.

Los intentos se guardan en la base de datos: los comparten varios procesos y sobreviven a un reinicio (un atacante no vacía el contador
reiniciando). Si la base de datos falla, se usa un contador en memoria para no dejar el acceso sin protección."""
import logging
import random
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, text

from .models import RateHit
from .store import _factory, engine

log = logging.getLogger("mimirsynth.ratelimit")
KEEP = 24 * 3600  # los intentos más antiguos que la ventana mayor que se usa (1 h) no sirven para nada
_HITS: dict[str, deque] = defaultdict(deque)
_LOCK = threading.Lock()


def _allow_memory(key: str, limit: int, window: float) -> bool:
    now = time.monotonic()
    with _LOCK:
        q = _HITS[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def _allow_db(key: str, limit: int, window: float) -> bool:
    now = datetime.now(timezone.utc)
    with _factory()() as db:
        if engine().dialect.name == "postgresql":  # serializa los intentos de una misma clave entre procesos
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})
        db.execute(delete(RateHit).where(RateHit.key == key, RateHit.at < now - timedelta(seconds=window)))
        if (db.scalar(select(func.count()).select_from(RateHit).where(RateHit.key == key)) or 0) >= limit:
            db.commit()
            return False
        db.add(RateHit(key=key, at=now))
        if random.random() < 0.01:  # limpieza ocasional de claves que no han vuelto a aparecer
            db.execute(delete(RateHit).where(RateHit.at < now - timedelta(seconds=KEEP)))
        db.commit()
        return True


def allow(key: str, limit: int, window: float) -> bool:
    """True si aún cabe una petición más de `key` en los últimos `window` segundos (y la cuenta)."""
    try:
        return _allow_db(key, limit, window)
    except Exception as e:  # noqa: BLE001  (base de datos no disponible o tabla aún sin crear)
        log.warning("limitador en memoria (la base de datos falló: %s)", e)
        return _allow_memory(key, limit, window)


def reset() -> None:
    with _LOCK:
        _HITS.clear()
    try:
        with _factory()() as db:
            db.execute(delete(RateHit)); db.commit()
    except Exception:  # noqa: BLE001
        pass
