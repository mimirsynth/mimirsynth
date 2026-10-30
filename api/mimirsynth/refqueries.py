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

from . import appsettings, jobs, notify
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
    q = RefQuery(brain_id=ctx.brain.id, query=body.query.strip(), expect=[i.model_dump() for i in body.expect],
                 avoid=[i.model_dump() for i in body.avoid], docs=body.docs, note=body.note, created_by=ctx.user.id)
    ctx.db.add(q); ctx.db.commit()
    audit(ctx.db, ctx.user, "refquery.create", ctx.brain, id=q.id)
    return _q_out(q)


@router.patch("/{qid:int}")
def update_query(qid: int, body: QueryPatch, ctx: BrainCtx = Depends(curator)):
    q = _get(ctx, qid)
    if body.query is not None:
        q.query = body.query.strip()
    if body.expect is not None:
        q.expect = [i.model_dump() for i in body.expect]
    if body.avoid is not None:
        q.avoid = [i.model_dump() for i in body.avoid]
    if body.docs is not None or body.clear_docs:
        q.docs = None if body.clear_docs else body.docs
    if body.note is not None:
        q.note = body.note
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
        ctx.db.add(RefQuery(brain_id=ctx.brain.id, query=it.query.strip(), expect=[i.model_dump() for i in it.expect],
                            avoid=[i.model_dump() for i in it.avoid], docs=it.docs, note=it.note, created_by=ctx.user.id))
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


def run_after_switch() -> list[int]:
    """Tras un cambio de modelo de embeddings: una ejecución en cada brain que tenga consultas de referencia."""
    with _factory()() as db:
        brains = db.scalars(select(RefQuery.brain_id).distinct()).all()
    return [submit_run(b, {}, "embedding.switched") for b in brains]


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


def compare(summary: dict, prev: dict | None) -> dict | None:
    """Diferencia con la ejecución anterior con los ajustes en vigor. Empeora si se encuentran menos esperados o aparecen más falsos
    positivos o más consultas con la sección de documentos al revés."""
    if not prev:
        return None
    d = {k: summary[k] - prev.get(k, 0) for k in ("found", "false_positives", "docs_mismatch", "expected")}
    d["regressed"] = d["found"] < 0 or d["false_positives"] > 0 or d["docs_mismatch"] > 0
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
        summary["delta"] = compare(summary, prev.summary if prev else None)
        r = db.get(RefRun, p["run_id"])
        r.status, r.summary, r.results, r.finished_at = "done", summary, results, datetime.now(timezone.utc)
        db.commit()
    d = summary["delta"]
    if reason == "embedding.switched" and d and d["regressed"]:
        notify.emit("refquery.regressed", f"Las consultas de referencia de «{name}» empeoran tras el cambio de modelo",
                    f"Esperados encontrados: {d['found']:+d}. Falsos positivos: {d['false_positives']:+d}. Revisa la similitud mínima de un pasaje "
                    f"(Administración → Recuerdo) y la ejecución #{p['run_id']} en Preguntar → Consultas de referencia.",
                    brain_id=bid, key=f"refquery:{slug}")
    return {"run_id": p["run_id"], **{k: summary[k] for k in ("queries", "expected", "found", "false_positives")}}
