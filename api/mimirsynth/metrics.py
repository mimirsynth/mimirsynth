"""Prometheus metrics (#131): `GET /metrics`, in the Prometheus text format, for whoever watches the instance.

- **Who can read it:** nobody by default. An instance administrator generates its token under Administration → Metrics (shown once;
  only its hash is kept, in `app_settings`), and from then on a request needs `Authorization: Bearer <token>`; without it, or with
  another one, it answers 401. Without a token the route answers 404, as if it did not exist. Generating a new one replaces the old
  one at once; revoking it turns the route off. An instance behind a reverse proxy usually publishes every path, so it is the token,
  not the network, that keeps it private.
- **Labels:** a closed list (`LABELS`): the brain's slug, the kind and model of an AI engine, the kind of a job and closed values such
  as a state. Never a query, a document, a person or any text of the memories: they would multiply the series and leak content.
- **Two sources.** What happens in this process (recall time, finished jobs, calls to AI engines) is counted in memory, starts again
  with each restart and is read with `rate()` or `increase()`. What is stored (jobs waiting, proposals, documents, notification
  deliveries) is read from the database when Prometheus asks; the size of each graph (entities, facts, episodes) is counted in the
  background at most every GRAPH_EVERY seconds, so a large graph never slows the scrape: the first one after a start lacks it.
- `/api/health` already says whether PostgreSQL and FalkorDB answer: it is not repeated here.
- Nothing here raises into the code it measures: a metric that fails is logged and skipped.
"""
import hmac
import logging
import secrets
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import appsettings
from .deps import audit, hash_token, require_admin
from .models import AppSetting, Brain, Document, Job, NotifyDelivery, Proposal, User, now
from .store import _factory, get_db

log = logging.getLogger("mimirsynth.metrics")
router = APIRouter()
LABELS = frozenset({"brain", "part", "state", "kind", "model", "outcome", "status", "direction", "version"})
REGISTRY = CollectorRegistry(auto_describe=True)
GRAPH_EVERY = 300.0
FAST = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
ENGINE = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0)
SLOW = (0.1, 0.5, 1.0, 5.0, 15.0, 30.0, 60.0, 300.0, 900.0, 3600.0)

RECALL = Histogram("mimirsynth_recall_seconds", "Time of a recall, by part: embed, facts, chunks, documents and total",
                   ["brain", "part"], buckets=FAST, registry=REGISTRY)
RECALL_DOCS = Counter("mimirsynth_recall_documents", "Recalls by state of their document search: ok, timeout, error or off",
                      ["brain", "state"], registry=REGISTRY)
JOBS = Histogram("mimirsynth_job_seconds", "Time of the background jobs that finished, by kind and status: done, failed or cancelled",
                 ["kind", "status"], buckets=SLOW, registry=REGISTRY)
AI_CALLS = Counter("mimirsynth_ai_requests", "Calls to AI engines, by outcome: ok, rate_limited, server_error or client_error",
                   ["kind", "model", "outcome"], registry=REGISTRY)
AI_SECONDS = Histogram("mimirsynth_ai_request_seconds", "Time of the calls to AI engines that got an answer",
                       ["kind", "model"], buckets=ENGINE, registry=REGISTRY)
AI_TOKENS = Counter("mimirsynth_ai_tokens", "Tokens sent to (in) and received from (out) AI engines", ["kind", "model", "direction"],
                    registry=REGISTRY)

_SLUGS: dict[int, str] = {}                    # brain id -> slug, refreshed on each scrape (a brain's slug can change)
_GRAPH: tuple[float, dict[str, dict]] = (0.0, {})  # (when, slug -> sizes)
_GRAPH_LOCK = threading.Lock()
_refreshing = False


def _slug(brain_id: int | None) -> str:
    """The brain's slug for a label; `""` outside a brain (an engine test, a model change)."""
    if not brain_id:
        return ""
    s = _SLUGS.get(brain_id)
    if s is None:
        with _factory()() as db:
            s = db.scalar(select(Brain.slug).where(Brain.id == brain_id)) or str(brain_id)
        _SLUGS[brain_id] = s
    return s


def _model(name: str) -> str:
    return (name or "")[:120]


def recall_done(brain_id: int, seconds: dict[str, float], docs_state: str) -> None:
    """A recall finished: the time of each of its parts and the state of its document search."""
    try:
        b = _slug(brain_id)
        for part, s in seconds.items():
            RECALL.labels(b, part).observe(max(0.0, s))
        RECALL_DOCS.labels(b, docs_state).inc()
    except Exception:  # noqa: BLE001
        log.warning("no se pudo medir un recall", exc_info=True)


def documents_searched(brain_id: int, seconds: float) -> None:
    """The document search of a recall finished, also when the recall stopped waiting for it (its timeout)."""
    try:
        RECALL.labels(_slug(brain_id), "documents").observe(max(0.0, seconds))
    except Exception:  # noqa: BLE001
        log.warning("no se pudo medir una búsqueda documental", exc_info=True)


def job_done(kind: str, status: str, seconds: float) -> None:
    try:
        JOBS.labels(kind, status).observe(max(0.0, seconds))
    except Exception:  # noqa: BLE001
        log.warning("no se pudo medir un trabajo", exc_info=True)


def _outcome(status: int) -> str:
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "server_error"
    return "client_error" if status >= 400 else "ok"


def ai_call(kind: str, model: str, status: int, tin: int = 0, tout: int = 0) -> None:
    """A call to an AI engine, counted where its consumption is counted (`usage.record`)."""
    try:
        m = _model(model)
        AI_CALLS.labels(kind, m, _outcome(status)).inc()
        if tin:
            AI_TOKENS.labels(kind, m, "in").inc(tin)
        if tout:
            AI_TOKENS.labels(kind, m, "out").inc(tout)
    except Exception:  # noqa: BLE001
        log.warning("no se pudo medir una llamada a un motor de IA", exc_info=True)


def ai_time(kind: str, model: str, seconds: float) -> None:
    try:
        AI_SECONDS.labels(kind, _model(model)).observe(max(0.0, seconds))
    except Exception:  # noqa: BLE001
        log.warning("no se pudo medir el tiempo de una llamada a un motor de IA", exc_info=True)


def _sizes(graph_name: str) -> dict:
    from .db import client
    g = client().select_graph(graph_name)
    one = lambda q: g.query(q).result_set[0][0]  # noqa: E731
    return {"entities": one("MATCH (n:Entity) RETURN count(n)"),
            "episodes": one("MATCH (e:Episodic) RETURN count(e)"),
            "current": one("MATCH ()-[r:RELATES_TO]->() WHERE r.invalid_at IS NULL RETURN count(r)"),
            "invalidated": one("MATCH ()-[r:RELATES_TO]->() WHERE r.invalid_at IS NOT NULL RETURN count(r)")}


def refresh_graph() -> None:
    """Counts the size of every brain's graph. A brain whose graph does not answer keeps no value until the next count."""
    global _GRAPH, _refreshing
    try:
        from .db import list_graphs
        with _factory()() as db:
            brains = db.execute(select(Brain.slug, Brain.graph_name)).all()
        existing = set(list_graphs())
        out = {}
        for slug, graph_name in brains:
            if graph_name not in existing:
                continue
            try:
                out[slug] = _sizes(graph_name)
            except Exception:  # noqa: BLE001
                log.warning("no se pudo contar el grafo del brain %s", slug, exc_info=True)
        _GRAPH = (time.monotonic(), out)
    except Exception:  # noqa: BLE001
        log.warning("no se pudo contar el tamaño de los grafos", exc_info=True)
        _GRAPH = (time.monotonic(), {})
    finally:
        _refreshing = False


def _graph_due() -> None:
    """Starts a count in the background if the last one is older than GRAPH_EVERY (inline while testing)."""
    global _refreshing
    from . import jobs
    with _GRAPH_LOCK:
        if _refreshing or (_GRAPH[0] and time.monotonic() - _GRAPH[0] < GRAPH_EVERY):
            return
        _refreshing = True
    if jobs.INLINE:
        refresh_graph()
    else:
        threading.Thread(target=refresh_graph, name="metrics-graph", daemon=True).start()


def _age(d: datetime | None) -> float:
    if d is None:
        return 0.0
    d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - d).total_seconds())


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("mimirsynth")
    except Exception:  # noqa: BLE001  (run without installing)
        return "0.0.0"


class _Stored:
    """What is in the database and the graph, read on each scrape."""

    def describe(self):
        return []

    def collect(self):
        info = GaugeMetricFamily("mimirsynth_info", "The running version", labels=["version"])
        info.add_metric([_version()], 1)
        yield info
        try:
            yield from self._database()
        except Exception:  # noqa: BLE001  (the database is down: /api/health says so)
            log.warning("no se pudieron leer las métricas de la base de datos", exc_info=True)
        _graph_due()
        sizes = _GRAPH[1]
        ent = GaugeMetricFamily("mimirsynth_brain_entities", "Entities in the brain's graph", labels=["brain"])
        epi = GaugeMetricFamily("mimirsynth_brain_episodes", "Episodes in the brain's graph", labels=["brain"])
        facts = GaugeMetricFamily("mimirsynth_brain_facts", "Facts in the brain's graph, current or invalidated", labels=["brain", "state"])
        for slug, s in sorted(sizes.items()):
            ent.add_metric([slug], s["entities"])
            epi.add_metric([slug], s["episodes"])
            facts.add_metric([slug, "current"], s["current"])
            facts.add_metric([slug, "invalidated"], s["invalidated"])
        yield from (ent, epi, facts)

    def _database(self):
        with _factory()() as db:
            slugs = dict(db.execute(select(Brain.id, Brain.slug)).all())
            _SLUGS.clear()
            _SLUGS.update(slugs)
            jobs = GaugeMetricFamily("mimirsynth_jobs", "Background jobs waiting or running, by kind", labels=["kind", "status"])
            for kind, status, n in db.execute(select(Job.kind, Job.status, func.count()).where(Job.status.in_(("queued", "running")))
                                              .group_by(Job.kind, Job.status)).all():
                jobs.add_metric([kind, status], n)
            oldest = GaugeMetricFamily("mimirsynth_jobs_oldest_queued_seconds", "Age of the oldest job still waiting, by kind", labels=["kind"])
            for kind, created in db.execute(select(Job.kind, func.min(Job.created_at)).where(Job.status == "queued").group_by(Job.kind)).all():
                oldest.add_metric([kind], _age(created))
            props = GaugeMetricFamily("mimirsynth_proposals", "Proposals by state: pending, approved, rejected, ingested or failed",
                                      labels=["brain", "status"])
            for bid, status, n in db.execute(select(Proposal.brain_id, Proposal.status, func.count())
                                             .group_by(Proposal.brain_id, Proposal.status)).all():
                props.add_metric([slugs.get(bid, str(bid)), status], n)
            waiting = GaugeMetricFamily("mimirsynth_proposals_oldest_pending_seconds", "Age of the oldest proposal waiting for a curator",
                                        labels=["brain"])
            for bid, created in db.execute(select(Proposal.brain_id, func.min(Proposal.created_at)).where(Proposal.status == "pending")
                                           .group_by(Proposal.brain_id)).all():
                waiting.add_metric([slugs.get(bid, str(bid))], _age(created))
            docs = GaugeMetricFamily("mimirsynth_documents", "Documents by state: pending, indexing, active or error", labels=["brain", "status"])
            for bid, status, n in db.execute(select(Document.brain_id, Document.status, func.count()).where(Document.status != "deleted")
                                             .group_by(Document.brain_id, Document.status)).all():
                docs.add_metric([slugs.get(bid, str(bid)), status], n)
            deliveries = GaugeMetricFamily("mimirsynth_notify_deliveries", "Notification deliveries waiting to be sent or failed",
                                           labels=["status"])
            for status, n in db.execute(select(NotifyDelivery.status, func.count()).where(NotifyDelivery.status.in_(("pending", "failed")))
                                        .group_by(NotifyDelivery.status)).all():
                deliveries.add_metric([status], n)
        yield from (jobs, oldest, props, waiting, docs, deliveries)


REGISTRY.register(_Stored())


TOKEN_KEY = "metrics_token"   # app_settings row: {hash, prefix, created_at, created_by}; no row, no metrics
_LAST: dict[str, float] = {}   # when the metrics were last read with the token, in this process


def _stored() -> dict | None:
    v = appsettings.stored(TOKEN_KEY)
    return v if isinstance(v, dict) and v.get("hash") else None


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request):
    """The metrics, for a request with the token generated under Administration → Metrics; 404 while there is none."""
    tok = _stored()
    if not tok:
        raise HTTPException(404)
    scheme, _, given = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(hash_token(given.strip()), tok["hash"]):
        raise HTTPException(401, "falta el token de las métricas o no es válido", headers={"WWW-Authenticate": "Bearer"})
    _LAST["at"] = time.time()
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


def _state(db: Session) -> dict:
    tok = _stored()
    by = db.get(User, tok["created_by"]) if tok and tok.get("created_by") else None
    last = datetime.fromtimestamp(_LAST["at"], timezone.utc).isoformat() if tok and "at" in _LAST else None
    return {"enabled": bool(tok), "prefix": tok["prefix"] if tok else "", "created_at": tok.get("created_at") if tok else None,
            "created_by": (by.display_name or by.name or by.email) if by else None, "last_read_at": last,
            "url": (appsettings.get("public_url") or "").rstrip("/") + "/metrics"}


@router.get("/api/admin/metrics")
def metrics_state(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Whether the metrics are on, with the token's prefix, who made it and when they were last read (since this process started)."""
    return _state(db)


@router.post("/api/admin/metrics/token")
def new_token(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """A new token, shown once. It replaces the previous one at once: whoever reads the metrics needs the new one."""
    raw = "msm_" + secrets.token_urlsafe(32)
    replaced = bool(_stored())
    value = {"hash": hash_token(raw), "prefix": raw[:10], "created_at": now().isoformat(), "created_by": user.id}
    row = db.get(AppSetting, TOKEN_KEY)
    if row:
        row.value, row.updated_at, row.updated_by = {"v": value}, now(), user.id
    else:
        db.add(AppSetting(key=TOKEN_KEY, value={"v": value}, updated_by=user.id))
    db.commit()
    appsettings.invalidate()
    _LAST.clear()
    audit(db, user, "metrics.token.rotate" if replaced else "metrics.token.create", prefix=value["prefix"])
    return {**_state(db), "token": raw}


@router.delete("/api/admin/metrics/token")
def revoke_token(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Revokes the token: /metrics answers 404 again."""
    row = db.get(AppSetting, TOKEN_KEY)
    if row:
        prefix = ((row.value or {}).get("v") or {}).get("prefix", "")
        db.delete(row)
        db.commit()
        appsettings.invalidate()
        _LAST.clear()
        audit(db, user, "metrics.token.revoke", prefix=prefix)
    return _state(db)
