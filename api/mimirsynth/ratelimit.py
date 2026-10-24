"""Limitador sencillo en memoria (ventana deslizante) para el inicio de sesión y la recuperación de contraseña."""
import threading
import time
from collections import defaultdict, deque

_HITS: dict[str, deque] = defaultdict(deque)
_LOCK = threading.Lock()


def allow(key: str, limit: int, window: float) -> bool:
    """True si aún cabe una petición más de `key` en los últimos `window` segundos (y la cuenta)."""
    now = time.monotonic()
    with _LOCK:
        q = _HITS[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def reset() -> None:
    with _LOCK:
        _HITS.clear()
