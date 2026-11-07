"""Memory health score (#292): a few numbers per brain, measured once a day and kept as a time series, that say whether the memory is
getting better or worse, so that a release or a configuration change that degrades the recall shows before an agent answers with a
stale fact.

- **Coverage:** the share of the reference queries' expected texts that the recall finds (as a reference-query run counts them).
- **Staleness:** the share of the reference queries whose recall brings something marked as possibly outdated: a current fact past
  its relation's shelf life, or an episode fragment or a document passage that states something no longer true. A fact no longer true
  that the recall shows as history does not count: it is labelled as such.
- **Noise:** how much a vague or off-topic question brings back (items and characters of the context), on a built-in set of such
  questions (a greeting, a single word, «go on with what we were doing») and on the reference queries that expect nothing. Ideally 0.
- **Redundancy:** the share of current facts that repeat another current fact between the same two entities: the same text, or
  embeddings closer than REDUNDANT_COSINE with the same numbers and identifiers («PostgreSQL 14» and «PostgreSQL 16» are not a
  repeat: they are a change). Past MAX_SAMPLE candidate facts it is estimated on the most recent ones and says so.
- **Open contradictions** (in the functional relations; none if no relation is functional) and **facts to review** (past their
  shelf life; none if no relation has one), as their screens count them.

A brain is measured once a UTC day (`due`, called by the notification loop every few minutes): the day is the run's key in the
database, so a restart never measures twice and never skips a day. A curator can measure again (`POST /health/run`): that day's numbers
are replaced. Each part is measured on its own; a part that fails is left empty (`null`) and named in `failed`, the rest is kept.
The probes are recalls, one embedding each, and never logged for ratings. Nothing here writes to the graph.

After each measurement, the `health.degraded` notification fires when the coverage falls at least `health_coverage_drop` since the
previous measurement (over the expected texts that are in both, so editing the reference queries is not a drop) or a number crosses
its threshold (`health_coverage_min`, `health_staleness_max`, `health_noise_max`, `health_redundancy_max`; 0 is off). It closes when a
later measurement is back within them.
"""
import hashlib
import logging
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from . import jobs
from .deps import BrainCtx, audit, brain_access
from .models import Brain, HealthRun, Job, RefQuery
from .store import _factory

log = logging.getLogger("mimirsynth.health")
router = APIRouter(prefix="/api/brains/{slug}/health")
curator = brain_access("curator")

KIND = "health.snapshot"
KEEP_DAYS = 400            # runs kept per brain
MAX_FACTS = 50000          # current facts read to measure redundancy (the most recent first)
MAX_SAMPLE = 3000          # candidate facts whose embeddings are read; past it, an estimate
REDUNDANT_COSINE = 0.93    # two facts between the same entities this close, with the same numbers, say the same thing
# Questions that ask for nothing in particular: a good recall returns (almost) nothing for them. In the two interface languages.
VAGUE = ("hola", "ok", "gracias", "vale, sigue con lo que estábamos haciendo", "¿y ahora qué?",
         "hello", "thanks", "ok, go on with what we were doing")
HEADLINE = ("coverage", "staleness", "noise", "redundancy", "contradictions", "stale_facts")

_FACTS = ("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.invalid_at IS NULL AND r.expired_at IS NULL "
          "RETURN r.uuid AS uuid, r.fact AS fact, a.uuid AS source_uuid, b.uuid AS target_uuid "
          "ORDER BY coalesce(r.valid_at, r.created_at) DESC, r.uuid LIMIT $n")
_VECTORS = "MATCH ()-[r:RELATES_TO]->() WHERE r.uuid IN $u RETURN r.uuid AS uuid, r.fact_embedding AS e"
_TOKEN = re.compile(r"\w(?:[\w.:/-]*\w)?")


def _today() -> date:
    return datetime.now(timezone.utc).date()


# --- the numbers --------------------------------------------------------------------------------

def _norm(text) -> str:
    return " ".join(str(text or "").lower().split())


def _ids(text) -> frozenset[str]:
    """The numbers and identifiers of a fact (anything with a digit: 14, 10.0.0.1, pve-02): what usually changes when a fact changes."""
    return frozenset(t for t in _TOKEN.findall(_norm(text)) if any(c.isdigit() for c in t))


def _cosine(a, b) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na, nb = sum(x * x for x in a) ** 0.5, sum(y * y for y in b) ** 0.5
    return num / (na * nb) if na and nb else 0.0


def near_duplicate(a: dict, b: dict) -> bool:
    """Two current facts between the same entities that say the same thing."""
    if _norm(a.get("fact")) == _norm(b.get("fact")):
        return True
    if _ids(a.get("fact")) != _ids(b.get("fact")):
        return False
    ea, eb = a.get("embedding"), b.get("embedding")
    return bool(ea) and bool(eb) and len(ea) == len(eb) and _cosine(ea, eb) >= REDUNDANT_COSINE


def _groups(facts: list[dict]) -> list[list[dict]]:
    """The facts grouped by the pair of entities they link (in either direction), only groups of two or more, the most recent first."""
    by: dict[tuple, list[dict]] = {}
    for f in facts:
        by.setdefault(tuple(sorted((str(f["source_uuid"]), str(f["target_uuid"])))), []).append(f)
    return [g for g in by.values() if len(g) > 1]


def repeats(group: list[dict]) -> int:
    """How many facts of a group repeat another one: in each cluster of near duplicates, all but one."""
    return sum(len(c) - 1 for c in clusters(group))


def clusters(group: list[dict]) -> list[list[dict]]:
    """The facts of a group that say the same thing, together (only clusters of two or more), in the group's order."""
    parent = list(range(len(group)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            if root(i) != root(j) and near_duplicate(group[i], group[j]):
                parent[root(j)] = root(i)
    by: dict[int, list[dict]] = {}
    for i, f in enumerate(group):
        by.setdefault(root(i), []).append(f)
    return [c for c in by.values() if len(c) > 1]


def redundancy(graph, max_facts: int = MAX_FACTS, max_sample: int = MAX_SAMPLE) -> dict:
    from .db import rows
    facts = rows(graph.query(_FACTS, {"n": max_facts}))
    groups = _groups(facts)
    candidates = sum(len(g) for g in groups)
    sample, n = [], 0
    for g in groups:
        if n + len(g) > max_sample and sample:
            break
        sample.append(g[:max_sample])
        n += len(sample[-1])
    vectors = {}
    uuids = [f["uuid"] for g in sample for f in g]
    for i in range(0, len(uuids), 500):
        for r in rows(graph.query(_VECTORS, {"u": uuids[i:i + 500]})):
            vectors[r["uuid"]] = r["e"]
    found = sum(repeats([{**f, "embedding": vectors.get(f["uuid"])} for f in g]) for g in sample)
    sampled = n < candidates
    estimate = round(found * candidates / n) if sampled and n else found
    return {"redundancy": round(estimate / len(facts), 4) if facts else None, "redundant_facts": estimate, "current_facts": len(facts),
            "redundancy_sampled": sampled, "facts_truncated": len(facts) >= max_facts}


def outdated(out: dict) -> int:
    """Items of a recall marked as possibly outdated: current facts past their shelf life, fragments and passages that state something
    no longer true. A fact no longer true shown as history is labelled, so it is not counted."""
    return (sum(1 for f in out.get("facts") or [] if f.get("status") != "invalidated" and f.get("stale_since"))
            + sum(1 for c in out.get("chunks") or [] if c.get("superseded"))
            + sum(1 for p in out.get("documents") or [] if p.get("superseded")))


def _item(qid, item: dict) -> str:
    return hashlib.sha1(f"{qid}|{_norm(item.get('text'))}|{item.get('kind', 'any')}".encode()).hexdigest()[:12]


def size(out: dict) -> tuple[int, int]:
    """Items and characters of context a recall returned."""
    return (len(out.get("facts") or []) + len(out.get("chunks") or []) + len(out.get("documents") or []), len(out.get("context") or ""))


def probes(recall, queries: list[dict], check=lambda: None) -> dict:
    """Coverage, staleness and noise from recalls: `recall(text)` returns what the recall returns. `queries`: the reference queries."""
    from .refqueries import evaluate
    expected = found = probed = stale = errors = 0
    noisy: list[tuple[int, int]] = []
    items: dict[str, int] = {}   # each expected text (hashed with its query and kind): 1 found, 0 not; to compare two runs fairly
    for q in [*queries, *({"query": v, "vague": True} for v in VAGUE)]:
        check()
        try:
            out = recall(q["query"])
        except Exception as e:  # noqa: BLE001  (one question that fails does not stop the measurement)
            log.warning("health probe failed: %s", e)
            errors += 1
            continue
        if not q.get("vague"):
            r = evaluate(q, out)
            expected, found, probed = expected + r["expected"], found + r["found"], probed + 1
            for i in r["expect"]:
                items[_item(q["id"], i)] = int(bool(i["found_in"]))
            stale += outdated(out) > 0
        if q.get("vague") or not q.get("expect"):
            noisy.append(size(out))
    return {"coverage": round(found / expected, 4) if expected else None, "expected": expected, "found": found,
            "reference_queries": len(queries), "staleness": round(stale / probed, 4) if probed else None, "stale_results": stale,
            "noise": round(sum(n for n, _ in noisy) / len(noisy), 2) if noisy else None,
            "noise_chars": round(sum(c for _, c in noisy) / len(noisy)) if noisy else None,
            "noise_empty": round(sum(1 for n, _ in noisy if not n) / len(noisy), 4) if noisy else None, "noise_queries": len(noisy),
            "probe_errors": errors, "coverage_items": items}


def measure(brain_id: int, check=lambda: None, progress=lambda m: None) -> dict:
    """All the numbers of one brain. Each part on its own: one that fails is `null` and named in `failed`."""
    from . import appsettings, conflicts, shelflife, usage
    from .db import graph
    from .federation import sources_for
    from .ontology import get_ontology
    from .recall import recall
    from .refqueries import _q_out
    from .vocab import alias_map
    with _factory()() as db:
        b = db.get(Brain, brain_id)
        gname = b.graph_name
        queries = [_q_out(q) for q in db.scalars(select(RefQuery).where(RefQuery.brain_id == brain_id).order_by(RefQuery.id))]
        src = sources_for(db, b)
        amap, functional = alias_map(db, brain_id), conflicts._brain_functional(db, brain_id)
        dismissed = conflicts._dismissals(db, brain_id)
        lives = shelflife.shelf_lives(get_ontology(db, brain_id))
    g = graph(gname)
    out: dict = {"failed": []}
    lang = appsettings.get("default_language") or "es"

    def part(name: str, fn):
        check()
        progress(name)
        try:
            out.update(fn())
        except jobs.Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("health of brain %s: %s failed: %s", brain_id, name, e)
            out["failed"].append(name)

    if usage.paused(brain_id):   # the probes are recalls, one embedding each: a brain over its AI budget is not probed
        out["probes_paused"] = True
    else:
        extra = {"sources": src} if src else {}
        part("probes", lambda: probes(lambda text: recall(brain_id, gname, text, 8, 4, 6000, lang=lang, **extra), queries, check))
    part("redundancy", lambda: redundancy(g))
    part("contradictions", lambda: {"contradictions": conflicts.scan(g, amap, functional, dismissed=dismissed)["total"]
                                    if functional else None})

    def stale():
        if not lives:
            return {"stale_facts": None}
        with _factory()() as db:
            return {"stale_facts": shelflife.scan(db, db.get(Brain, brain_id), limit=1)["total"]}
    part("stale_facts", stale)
    for k in HEADLINE:
        out.setdefault(k, None)
    return out


# --- runs and the daily schedule ----------------------------------------------------------------

def _alive(db, job_id: int | None) -> bool:
    j = db.get(Job, job_id) if job_id else None
    return bool(j) and j.status in ("queued", "running")


def start(brain_id: int, day: date, reason: str, user_id: int | None = None) -> int | None:
    """Queues the measurement of a brain for a day: the day's run is created, or reset if it is not running. None if it already runs."""
    with _factory()() as db:
        r = db.scalar(select(HealthRun).where(HealthRun.brain_id == brain_id, HealthRun.day == day))
        if r and r.status in ("queued", "running") and _alive(db, r.job_id):
            return None
        if r is None:
            r = HealthRun(brain_id=brain_id, day=day)
            db.add(r)
        r.status, r.reason, r.error, r.created_by = "queued", reason, "", user_id
        try:
            db.commit()
        except IntegrityError:   # another worker created it a moment ago
            db.rollback()
            return None
        rid = r.id
    jid = jobs.submit(KIND, brain_id, {"run_id": rid}, "Medir la salud de la memoria", user_id, dedupe_key=f"{KIND}:{brain_id}")
    with _factory()() as db:
        r = db.get(HealthRun, rid)
        r.job_id = jid
        db.commit()
    return rid


def due(today: date | None = None) -> list[int]:
    """The brains not measured yet today (or whose measurement was cut by a restart): one run each. Called every few minutes."""
    today = today or _today()
    with _factory()() as db:
        brains = list(db.scalars(select(Brain.id).order_by(Brain.id)))
        runs = {r.brain_id: r for r in db.scalars(select(HealthRun).where(HealthRun.day == today))}
        todo = [b for b in brains if b not in runs or (runs[b].status in ("queued", "running") and not _alive(db, runs[b].job_id))]
    return [rid for b in todo if (rid := start(b, today, "daily")) is not None]


@jobs.register(KIND, "Medir la salud de la memoria", limit=1)
def _job(ctx: "jobs.JobCtx", p: dict) -> dict:
    with _factory()() as db:
        r = db.get(HealthRun, p["run_id"])
        if not r:
            return {}
        brain_id = r.brain_id
        r.status = "running"
        db.commit()
    try:
        m = measure(brain_id, ctx.check, lambda part: ctx.progress(0, 0, part))
    except BaseException as e:
        with _factory()() as db:
            r = db.get(HealthRun, p["run_id"])
            r.status, r.finished_at = "error", datetime.now(timezone.utc)
            r.error = "cancelada" if isinstance(e, jobs.Cancelled) else str(e)[:500]
            db.commit()
        raise
    with _factory()() as db:
        r = db.get(HealthRun, p["run_id"])
        r.status, r.metrics, r.finished_at = "done", m, datetime.now(timezone.utc)
        db.execute(delete(HealthRun).where(HealthRun.brain_id == brain_id, HealthRun.day < _today() - timedelta(days=KEEP_DAYS)))
        db.commit()
        day = r.day
    try:
        _alert(brain_id, day, m)
    except Exception:  # noqa: BLE001  (a notification that fails does not lose the measurement)
        log.warning("health of brain %s: the notification failed", brain_id, exc_info=True)
    return {k: m.get(k) for k in HEADLINE}


def _pct(v: float) -> str:
    return f"{round(v * 100, 1):g} %"


def coverage_drop(m: dict, prev: dict | None) -> tuple[float, float, int] | None:
    """(before, now, texts compared): the coverage of the two runs over the expected texts that are in both, so that adding, editing
    or deleting a reference query never reads as a drop. None if there is nothing in common."""
    cur, old = (m or {}).get("coverage_items") or {}, (prev or {}).get("coverage_items") or {}
    common = cur.keys() & old.keys()
    if not common:
        return None
    return sum(old[k] for k in common) / len(common), sum(cur[k] for k in common) / len(common), len(common)


def crossings(m: dict, prev: dict | None) -> list[str]:
    """What in a measurement crosses the thresholds of Administration → Settings → Notifications, one sentence each."""
    from . import appsettings
    out = []
    drop = float(appsettings.get("health_coverage_drop"))
    d = coverage_drop(m, prev)
    if drop and d and d[0] - d[1] >= drop - 1e-9:
        out.append(f"la cobertura ha bajado del {_pct(d[0])} al {_pct(d[1])} sobre los {d[2]} textos esperados que estaban en las dos mediciones")
    for key, setting, above, text in (
            ("coverage", "health_coverage_min", False, "la cobertura es del {v}, por debajo del {t}"),
            ("staleness", "health_staleness_max", True, "el {v} de las consultas de referencia trae algo desactualizado, más del {t}"),
            ("redundancy", "health_redundancy_max", True, "el {v} de los hechos vigentes repite otro, más del {t}"),
            ("noise", "health_noise_max", True, "una pregunta vaga trae de media {v} elementos, más de {t}")):
        t, v = float(appsettings.get(setting)), m.get(key)
        if not t or not isinstance(v, (int, float)) or (v <= t if above else v >= t):
            continue
        fmt = (lambda x: f"{x:g}") if key == "noise" else _pct
        out.append(text.format(v=fmt(v), t=fmt(t)))
    return out


def _alert(brain_id: int, day: date, m: dict) -> None:
    """After a measurement: a `health.degraded` notification if something crosses a threshold, closed when nothing does."""
    from . import notify
    with _factory()() as db:
        b = db.get(Brain, brain_id)
        prev = db.scalar(select(HealthRun.metrics).where(HealthRun.brain_id == brain_id, HealthRun.status == "done", HealthRun.day < day)
                         .order_by(HealthRun.day.desc()).limit(1))
        name, slug = b.name, b.slug
    reasons, key = crossings(m, prev), f"health:{slug}"
    if reasons:
        notify.emit("health.degraded", f"La salud de la memoria de «{name}» ha empeorado",
                    "; ".join(reasons).capitalize() + ". Revísala en Resumen → Salud de la memoria.", brain_id=brain_id, key=key)
    else:
        notify.resolve("health.degraded", key, "La salud de la memoria vuelve a estar dentro de sus umbrales.")


def latest(db, since_days: int = 2) -> dict[int, dict]:
    """The last finished measurement of each brain in the last `since_days` days: brain id -> metrics (for Prometheus)."""
    out = {}
    for bid, metrics in db.execute(select(HealthRun.brain_id, HealthRun.metrics).where(
            HealthRun.status == "done", HealthRun.day >= _today() - timedelta(days=since_days)).order_by(HealthRun.day)).all():
        out[bid] = metrics or {}
    return out


# --- API ----------------------------------------------------------------------------------------

def _out(r: HealthRun) -> dict:
    return {"id": r.id, "day": r.day.isoformat(), "status": r.status, "reason": r.reason, "metrics": r.metrics, "error": r.error,
            "job_id": r.job_id, "created_at": r.created_at, "finished_at": r.finished_at}


@router.get("")
def history(days: int = Query(90, ge=1, le=KEEP_DAYS), ctx: BrainCtx = Depends(curator)):
    """The brain's measurements of the last `days` days, the oldest first, and the last finished one."""
    rows = ctx.db.scalars(select(HealthRun).where(HealthRun.brain_id == ctx.brain.id, HealthRun.day >= _today() - timedelta(days=days - 1))
                          .order_by(HealthRun.day)).all()
    done = [r for r in rows if r.status == "done"]
    return {"items": [_out(r) for r in rows], "latest": _out(done[-1]) if done else None,
            "measuring": any(r.status in ("queued", "running") for r in rows)}


@router.post("/run", status_code=202)
def run_now(ctx: BrainCtx = Depends(curator)):
    """Measures again now; today's numbers are replaced when it finishes."""
    rid = start(ctx.brain.id, _today(), "manual", ctx.user.id)
    if rid is None:
        raise HTTPException(409, "la salud de la memoria ya se está midiendo")
    audit(ctx.db, ctx.user, "health.run", ctx.brain, run=rid)
    return {"run": rid}
