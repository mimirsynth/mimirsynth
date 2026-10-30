"""Consultas de referencia por brain (#115): preguntas con lo que su recall debe traer y lo que no, y ejecuciones que miden cuántos
relevantes se recuperan y cuántos falsos positivos aparecen. Sirven para cambiar el umbral de los pasajes, el modelo de embeddings
o los pesos del recall con datos y no a ojo: se puede simular otro umbral sin tocar los ajustes y comparar con la ejecución anterior.

Una ejecución corre como trabajo (con progreso y cancelación). Tras un cambio de modelo de embeddings se lanza sola en cada brain
que tenga consultas, y si empeora respecto a la anterior se avisa.
"""
import logging
import statistics
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from . import appsettings, jobs, notify, secretguard
from .deps import BrainCtx, audit, brain_access
from .models import Brain, RefQuery, RefRun
from .store import _factory

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/brains/{slug}/refqueries")
curator = brain_access("curator")
MAX_QUERIES = 500


class Item(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    kind: str = Field("any", pattern="^(any|fact|chunk|doc)$")


class QueryIn(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    expect: list[Item] = Field(default_factory=list, max_length=50)
    avoid: list[Item] = Field(default_factory=list, max_length=50)
    docs: bool | None = None
    note: str = Field("", max_length=2000)


class QueryPatch(BaseModel):
    query: str | None = Field(None, min_length=1, max_length=4000)
    expect: list[Item] | None = Field(None, max_length=50)
    avoid: list[Item] | None = Field(None, max_length=50)
    docs: bool | None = None
    clear_docs: bool = False  # docs=None en el cuerpo no se distingue de «no tocar»: esto lo vuelve a «da igual»
    note: str | None = Field(None, max_length=2000)


class ImportIn(BaseModel):
    items: list[QueryIn] = Field(max_length=MAX_QUERIES)
    replace: bool = False


class Params(BaseModel):
    """Lo que se simula. Vacío = los ajustes en vigor."""
    min_sim: float | None = Field(None, ge=0, le=1)
    docs: int | None = Field(None, ge=0, le=6)
    facts: int | None = Field(None, ge=0, le=30)
    chunks: int | None = Field(None, ge=0, le=15)


class RunIn(BaseModel):
    params: Params = Field(default_factory=Params)
    sweep: list[float] = Field(default_factory=list, max_length=6)  # varios umbrales: una ejecución por cada uno


def _q_out(q: RefQuery) -> dict:
    return {"id": q.id, "query": q.query, "expect": q.expect or [], "avoid": q.avoid or [], "docs": q.docs, "note": q.note,
            "created_at": q.created_at, "updated_at": q.updated_at}


def _run_out(r: RefRun, full: bool = False) -> dict:
    out = {"id": r.id, "status": r.status, "reason": r.reason, "params": r.params or {}, "summary": r.summary, "error": r.error,
           "job_id": r.job_id, "created_at": r.created_at, "finished_at": r.finished_at}
    if full:
        out["results"] = r.results or []
    return out


def _clean(ctx: BrainCtx, text: str) -> str:
    """Un texto de una consulta de referencia pasa por el detector de secretos del brain: al guardar como esperado un hecho del grafo,
    que no pasó por él al ingerirse, no se copia una credencial a otra tabla."""
    try:
        return secretguard.guard(ctx.brain, text)[0]
    except secretguard.Blocked as e:
        raise HTTPException(422, f"la consulta de referencia contiene secretos ({', '.join(e.labels)})") from None


def _items_of(ctx: BrainCtx, items: list[Item]) -> list[dict]:
    return [{"text": _clean(ctx, i.text), "kind": i.kind} for i in items]


def _get(ctx: BrainCtx, qid: int) -> RefQuery:
    q = ctx.db.get(RefQuery, qid)
    if not q or q.brain_id != ctx.brain.id:
        raise HTTPException(404, "consulta de referencia no encontrada")
    return q


def _count(ctx: BrainCtx) -> int:
    return ctx.db.scalar(select(func.count()).select_from(RefQuery).where(RefQuery.brain_id == ctx.brain.id)) or 0


@router.get("")
def list_queries(ctx: BrainCtx = Depends(curator)):
    rows = ctx.db.scalars(select(RefQuery).where(RefQuery.brain_id == ctx.brain.id).order_by(RefQuery.id)).all()
    last = ctx.db.scalar(select(RefRun).where(RefRun.brain_id == ctx.brain.id).order_by(RefRun.id.desc()).limit(1))
    return {"items": [_q_out(q) for q in rows], "last_run": _run_out(last) if last else None}


@router.post("", status_code=201)
def create_query(body: QueryIn, ctx: BrainCtx = Depends(curator)):
    if _count(ctx) >= MAX_QUERIES:
        raise HTTPException(409, f"un brain admite como mucho {MAX_QUERIES} consultas de referencia")
    q = RefQuery(brain_id=ctx.brain.id, query=_clean(ctx, body.query.strip()), expect=_items_of(ctx, body.expect),
                 avoid=_items_of(ctx, body.avoid), docs=body.docs, note=_clean(ctx, body.note), created_by=ctx.user.id)
    ctx.db.add(q); ctx.db.commit()
    audit(ctx.db, ctx.user, "refquery.create", ctx.brain, id=q.id)
    return _q_out(q)


@router.patch("/{qid:int}")
def update_query(qid: int, body: QueryPatch, ctx: BrainCtx = Depends(curator)):
    q = _get(ctx, qid)
    if body.query is not None:
        q.query = _clean(ctx, body.query.strip())
    if body.expect is not None:
        q.expect = _items_of(ctx, body.expect)
    if body.avoid is not None:
        q.avoid = _items_of(ctx, body.avoid)
    if body.docs is not None or body.clear_docs:
        q.docs = None if body.clear_docs else body.docs
    if body.note is not None:
        q.note = _clean(ctx, body.note)
    q.updated_at = datetime.now(timezone.utc)
    ctx.db.commit()
    audit(ctx.db, ctx.user, "refquery.update", ctx.brain, id=q.id)
    return _q_out(q)


@router.delete("/{qid:int}")
def delete_query(qid: int, ctx: BrainCtx = Depends(curator)):
    q = _get(ctx, qid)
    ctx.db.delete(q); ctx.db.commit()
    audit(ctx.db, ctx.user, "refquery.delete", ctx.brain, id=qid)
    return {"ok": True}


@router.get("/export")
def export_queries(ctx: BrainCtx = Depends(curator)):
    """Las consultas en el mismo formato que acepta la importación (sin ids), para llevarlas a otro brain o a otra instancia."""
    rows = ctx.db.scalars(select(RefQuery).where(RefQuery.brain_id == ctx.brain.id).order_by(RefQuery.id)).all()
    return {"items": [{k: v for k, v in _q_out(q).items() if k in ("query", "expect", "avoid", "docs", "note")} for q in rows]}


@router.post("/import")
def import_queries(body: ImportIn, ctx: BrainCtx = Depends(curator)):
    """Añade las consultas (o sustituye todas, con `replace`). Una consulta con el mismo texto que otra ya guardada se salta."""
    if body.replace:
        for q in ctx.db.scalars(select(RefQuery).where(RefQuery.brain_id == ctx.brain.id)).all():
            ctx.db.delete(q)
        ctx.db.flush()
    have = {_norm(q) for q in ctx.db.scalars(select(RefQuery.query).where(RefQuery.brain_id == ctx.brain.id))}
    if len(have) + len(body.items) > MAX_QUERIES:
        raise HTTPException(409, f"un brain admite como mucho {MAX_QUERIES} consultas de referencia")
    added = 0
    for it in body.items:
        if _norm(it.query) in have:
            continue
        have.add(_norm(it.query))
        ctx.db.add(RefQuery(brain_id=ctx.brain.id, query=_clean(ctx, it.query.strip()), expect=_items_of(ctx, it.expect),
                            avoid=_items_of(ctx, it.avoid), docs=it.docs, note=_clean(ctx, it.note), created_by=ctx.user.id))
        added += 1
    ctx.db.commit()
    audit(ctx.db, ctx.user, "refquery.import", ctx.brain, added=added, replace=body.replace)
    return {"added": added, "skipped": len(body.items) - added}


# --- ejecuciones ------------------------------------------------------------------------------

@router.post("/runs", status_code=202)
def start_run(body: RunIn, ctx: BrainCtx = Depends(curator)):
    if not _count(ctx):
        raise HTTPException(409, "el brain no tiene consultas de referencia")
    sets = [{**body.params.model_dump(exclude_none=True), "min_sim": s} for s in sorted(set(body.sweep))] or [body.params.model_dump(exclude_none=True)]
    runs = [submit_run(ctx.brain.id, p, "manual", ctx.user.id) for p in sets]
    audit(ctx.db, ctx.user, "refquery.run", ctx.brain, runs=runs, params=sets)
    return {"runs": runs}


@router.get("/runs")
def list_runs(ctx: BrainCtx = Depends(curator)):
    rows = ctx.db.scalars(select(RefRun).where(RefRun.brain_id == ctx.brain.id).order_by(RefRun.id.desc()).limit(50)).all()
    return {"items": [_run_out(r) for r in rows]}


@router.get("/runs/{rid:int}")
def get_run(rid: int, ctx: BrainCtx = Depends(curator)):
    r = ctx.db.get(RefRun, rid)
    if not r or r.brain_id != ctx.brain.id:
        raise HTTPException(404, "ejecución no encontrada")
    return _run_out(r, full=True)


def submit_run(brain_id: int, params: dict, reason: str, user_id: int | None = None) -> int:
    with _factory()() as db:
        r = RefRun(brain_id=brain_id, params=params, reason=reason, created_by=user_id)
        db.add(r); db.commit()
        rid = r.id
    label = "con los ajustes en vigor" if not params else "simulando " + ", ".join(f"{k}={v}" for k, v in sorted(params.items()))
    jid = jobs.submit("refquery.run", brain_id, {"run_id": rid}, f"Consultas de referencia ({label})", user_id)
    with _factory()() as db:
        r = db.get(RefRun, rid)
        if r and r.job_id is None:
            r.job_id = jid; db.commit()
    return rid


KEEP_RUNS = 20  # ejecuciones que se conservan por brain (cada una guarda el detalle de todas sus consultas)


def _brains_with_queries() -> list[int]:
    with _factory()() as db:
        return list(db.scalars(select(RefQuery.brain_id).distinct()).all())


def run_before_switch() -> list[int]:
    """Al empezar un cambio de modelo de embeddings, mientras el recall usa todavía el modelo anterior: la ejecución base con la que
    se comparará la de después del cambio."""
    return [submit_run(b, {}, "embedding.before") for b in _brains_with_queries()]


def run_after_switch() -> list[int]:
    """Tras un cambio de modelo de embeddings: una ejecución en cada brain que tenga consultas de referencia."""
    return [submit_run(b, {}, "embedding.switched") for b in _brains_with_queries()]


def _purge(db, brain_id: int) -> None:
    old = db.scalars(select(RefRun.id).where(RefRun.brain_id == brain_id, RefRun.status.in_(("done", "error")))
                     .order_by(RefRun.id.desc()).offset(KEEP_RUNS)).all()
    if old:
        db.query(RefRun).filter(RefRun.id.in_(old)).delete(synchronize_session=False)
        db.commit()


def _norm(t: str) -> str:
    return " ".join((t or "").lower().split())


def evaluate(q: dict, out: dict) -> dict:
    """Compara lo que devolvió el recall con lo que la consulta espera. Un texto cuenta como encontrado si aparece (sin contar
    mayúsculas ni espacios) dentro de algún elemento del tipo indicado: hecho, fragmento de episodio o pasaje de documento."""
    texts = {"fact": [_norm(f.get("fact")) for f in out.get("facts", [])],
             "chunk": [_norm(c.get("text")) for c in out.get("chunks", [])],
             "doc": [_norm(p.get("text")) for p in out.get("documents", [])]}

    def where(item: dict) -> list[str]:
        t = _norm(item["text"])
        return [k for k in (("fact", "chunk", "doc") if item.get("kind", "any") == "any" else (item["kind"],)) if any(t in x for x in texts[k])]

    expect = [{**i, "found_in": where(i)} for i in q.get("expect") or []]
    avoid = [{**i, "found_in": where(i)} for i in q.get("avoid") or []]
    docs_ok = None if q.get("docs") is None else bool(out.get("documents")) == q["docs"]
    return {"id": q["id"], "query": q["query"], "expected": len(expect), "found": sum(1 for i in expect if i["found_in"]),
            "false_positives": sum(1 for i in avoid if i["found_in"]), "docs_ok": docs_ok, "documents_state": out.get("documents_state"),
            "counts": {k: len(v) for k, v in texts.items()}, "ms": (out.get("ms") or {}).get("total"), "expect": expect, "avoid": avoid}


def summarize(results: list[dict]) -> dict:
    ok = [r for r in results if not r.get("error")]
    expected, found = sum(r["expected"] for r in ok), sum(r["found"] for r in ok)
    by_kind = {k: {"found": sum(1 for r in ok for i in r["expect"] if k in i["found_in"]),
                   "false_positives": sum(1 for r in ok for i in r["avoid"] if k in i["found_in"])} for k in ("fact", "chunk", "doc")}
    ms = [r["ms"] for r in ok if r.get("ms") is not None]
    return {"queries": len(results), "errors": len(results) - len(ok), "expected": expected, "found": found,
            "recall": round(found / expected, 3) if expected else None, "false_positives": sum(r["false_positives"] for r in ok),
            "docs_mismatch": sum(1 for r in ok if r["docs_ok"] is False), "by_kind": by_kind,
            "ms_p50": round(statistics.median(ms)) if ms else None, "ms_max": max(ms) if ms else None}


def _items(results: list[dict]) -> tuple[dict, dict, dict]:
    """Por cada (consulta, texto, tipo): si se encontró. Y por consulta: si la sección de documentos salió como se esperaba."""
    ok = [r for r in results or [] if not r.get("error")]
    expect = {(r["id"], _norm(i["text"]), i.get("kind", "any")): bool(i["found_in"]) for r in ok for i in r["expect"]}
    avoid = {(r["id"], _norm(i["text"]), i.get("kind", "any")): bool(i["found_in"]) for r in ok for i in r["avoid"]}
    docs = {r["id"]: r["docs_ok"] for r in ok if r.get("docs_ok") is not None}
    return expect, avoid, docs


def compare(results: list[dict], prev: list[dict] | None) -> dict | None:
    """Diferencia con la ejecución anterior con los ajustes en vigor, **solo sobre lo que está en las dos**: las mismas consultas y
    los mismos textos esperados y prohibidos. Añadir, borrar o editar una consulta no cuenta como empeorar. Empeora si se deja de
    encontrar algún esperado que antes salía, aparece algún falso positivo que antes no salía, o una consulta pasa a tener la
    sección de documentos al revés."""
    if prev is None:
        return None
    (ce, ca, cd), (pe, pa, pd) = _items(results), _items(prev)
    ke, ka, kd = ce.keys() & pe.keys(), ca.keys() & pa.keys(), cd.keys() & pd.keys()
    lost = sorted(k for k in ke if pe[k] and not ce[k])
    new_fp = sorted(k for k in ka if ca[k] and not pa[k])
    docs_worse = sorted(k for k in kd if pd[k] and not cd[k])
    d = {"found": sum(ce[k] for k in ke) - sum(pe[k] for k in ke), "false_positives": sum(ca[k] for k in ka) - sum(pa[k] for k in ka),
         "docs_mismatch": sum(not cd[k] for k in kd) - sum(not pd[k] for k in kd),
         "compared": len({k[0] for k in ke | ka} | kd), "lost": [{"id": k[0], "text": k[1]} for k in lost[:20]],
         "new_false_positives": [{"id": k[0], "text": k[1]} for k in new_fp[:20]]}
    d["regressed"] = bool(lost or new_fp or docs_worse)
    return d


@jobs.register("refquery.run", "Consultas de referencia", limit=1)
def _job_run(ctx: "jobs.JobCtx", p: dict) -> dict:
    from .federation import sources_for
    from .recall import recall
    with _factory()() as db:
        r = db.get(RefRun, p["run_id"])
        if not r:
            return {}
        brain = db.get(Brain, r.brain_id)
        params, reason = dict(r.params or {}), r.reason
        queries = [_q_out(q) for q in db.scalars(select(RefQuery).where(RefQuery.brain_id == brain.id).order_by(RefQuery.id))]
        src = sources_for(db, brain)
        bid, graph, slug, name = brain.id, brain.graph_name, brain.slug, brain.name
        r.status = "running"; db.commit()
    lang = appsettings.get("default_language") or "es"
    results = []
    try:
        for n, q in enumerate(queries, 1):
            ctx.check()
            ctx.progress(n - 1, len(queries), q["query"][:80])
            try:
                out = recall(bid, graph, q["query"], params.get("facts", 8), params.get("chunks", 4), 6000, n_docs=params.get("docs"),
                             lang=lang, min_sim=params.get("min_sim"), **({"sources": src} if src else {}))
                results.append(evaluate(q, out))
            except Exception as e:  # noqa: BLE001  (una consulta que falla no tumba la ejecución)
                log.warning("consulta de referencia %s falló: %s", q["id"], e)
                results.append({"id": q["id"], "query": q["query"], "error": str(e)[:300], "expected": len(q["expect"]), "found": 0,
                                "false_positives": 0, "docs_ok": None, "expect": [], "avoid": []})
        ctx.progress(len(queries), len(queries))
    except BaseException as e:
        with _factory()() as db:
            r = db.get(RefRun, p["run_id"])
            r.status, r.error, r.finished_at = "error", ("cancelada" if isinstance(e, jobs.Cancelled) else str(e)[:500]), datetime.now(timezone.utc)
            db.commit()
        raise
    summary = summarize(results)
    with _factory()() as db:
        prev = next((x for x in db.scalars(select(RefRun).where(RefRun.brain_id == bid, RefRun.id < p["run_id"], RefRun.status == "done")
                                            .order_by(RefRun.id.desc()).limit(50)) if not x.params), None)
        summary["previous_run"] = prev.id if prev else None
        summary["delta"] = compare(results, prev.results if prev else None)
        r = db.get(RefRun, p["run_id"])
        r.status, r.summary, r.results, r.finished_at = "done", summary, results, datetime.now(timezone.utc)
        db.commit()
        _purge(db, bid)
    d = summary["delta"]
    if reason == "embedding.switched" and d is None:   # sin base no se puede decir si empeora: se dice, en vez de callar
        notify.emit("refquery.regressed", f"Las consultas de referencia de «{name}» no tienen con qué compararse tras el cambio de modelo",
                    f"No hay una ejecución anterior con los ajustes en vigor, así que no se sabe si el modelo nuevo empeora. La ejecución #{p['run_id']} "
                    "queda como referencia para el próximo cambio.", severity="info", brain_id=bid, key=f"refquery:{slug}")
    elif reason == "embedding.switched" and d["regressed"]:
        notify.emit("refquery.regressed", f"Las consultas de referencia de «{name}» empeoran tras el cambio de modelo",
                    f"Sobre {d['compared']} consultas comparables: esperados que dejan de salir {len(d['lost'])}, falsos positivos nuevos "
                    f"{len(d['new_false_positives'])}. Revisa la similitud mínima de un pasaje (Administración → Recuerdo) y la ejecución "
                    f"#{p['run_id']} en Preguntar → Consultas de referencia.", brain_id=bid, key=f"refquery:{slug}")
    return {"run_id": p["run_id"], **{k: summary[k] for k in ("queries", "expected", "found", "false_positives")}}
