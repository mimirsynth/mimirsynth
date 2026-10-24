from datetime import datetime, timezone
from functools import lru_cache

from falkordb import FalkorDB

from .config import settings


@lru_cache
def client() -> FalkorDB:
    return FalkorDB(host=settings.falkor_host, port=settings.falkor_port)


def graph(name: str | None = None):
    return client().select_graph(name or settings.default_graph)


def list_graphs() -> list[str]:
    return [g for g in client().list_graphs() if not g.startswith("_")]


def parse_ts(value) -> datetime | None:
    """ISO-8601 de Graphiti (con 'Z' o '+00:00', con o sin microsegundos) -> datetime UTC."""
    if not value:
        return None
    s = str(value).replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def fact_status(valid_at, invalid_at, expired_at, at: datetime | None = None) -> str:
    """vigente | invalidado (dejó de ser cierto) | futuro (aún no válido en `at`)."""
    at = at or datetime.now(timezone.utc)
    v, i = parse_ts(valid_at), parse_ts(invalid_at)
    if v and v > at:
        return "future"
    if i and i <= at:
        return "invalidated"
    return "current"


def rows(result) -> list[dict]:
    """result_set de falkordb -> lista de dicts usando la cabecera."""
    names = [h[1] if isinstance(h, (list, tuple)) else h for h in result.header]
    return [dict(zip(names, r)) for r in result.result_set]
