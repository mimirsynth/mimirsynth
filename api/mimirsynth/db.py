from datetime import datetime, timezone

from .config import settings
from .graphdb import ReadOnlyGraph, backend

_read_only: set[str] | None = None  # the graphs of the read-only brains (#359), read once and dropped when a brain changes


def read_only_graphs() -> set[str]:
    global _read_only
    if _read_only is None:
        from sqlalchemy import select

        from .models import Brain
        from .store import _factory
        try:
            with _factory()() as db:
                _read_only = set(db.scalars(select(Brain.graph_name).where(Brain.read_only.is_(True))))
        except Exception:  # noqa: BLE001  (the control database not ready: nothing is known to be read-only yet, and it is asked again)
            return set()
    return _read_only


def forget_read_only() -> None:
    global _read_only
    _read_only = None


def _watch_brains() -> None:
    """Any session that commits a change to a brain (created, adopted, made read-only or full, renamed, deleted) drops the list."""
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    def after_flush(session, _ctx):
        from .models import Brain
        if any(isinstance(o, Brain) for o in (*session.new, *session.dirty, *session.deleted)):
            session.info["brains_changed"] = True

    def after_commit(session):
        if session.info.pop("brains_changed", False):
            forget_read_only()

    event.listen(Session, "after_flush", after_flush)
    event.listen(Session, "after_commit", after_commit)


_watch_brains()


def graph(name: str | None = None):
    name = name or settings.default_graph
    b = backend()
    g = b.graph(name)
    return ReadOnlyGraph(g, name, b) if name in read_only_graphs() else g


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
