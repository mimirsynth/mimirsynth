from datetime import datetime, timezone

from .config import settings
from .graphdb import backend


def graph(name: str | None = None):
    return backend().graph(name or settings.default_graph)


def list_graphs() -> list[str]:
    """The brains' graphs: the hidden ones («_» first: snapshots) left out."""
    return [g for g in backend().list_graphs() if not g.startswith("_")]


def vector(expr: str) -> str:
    """Cypher that stores the list `expr` as a vector property, in the active backend's dialect."""
    return backend().vector(expr)


def cosine(a: str, b: str) -> str:
    """Cypher for the cosine similarity of two vectors in [0, 1], in the active backend's dialect."""
    return backend().cosine(a, b)


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
    """The result of a query -> a list of dicts, keyed by the header."""
    names = [h[1] if isinstance(h, (list, tuple)) else h for h in result.header]
    return [dict(zip(names, r)) for r in result.result_set]
