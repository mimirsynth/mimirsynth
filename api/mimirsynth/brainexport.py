"""Export one brain to a package (#130): a `.tar.gz`, optionally encrypted with a password (see packcrypt), that holds everything the
brain is and nothing that only makes sense in this instance.

What goes in, under a versioned `manifest.json`:
- `graph/graph.dump`: the graph's `DUMP`, exact and fast to restore on the same FalkorDB version. The payload carries the graph's
  name: restore it under that key in an instance that does not have it, then copy it to another name if needed.
- `graph/nodes.jsonl` and `graph/edges.jsonl`: the same graph as JSON, for another FalkorDB version. Graphiti's vectors only with
  the vectors option.
- `brain.json`, `ontology.json`, `vocabulary.json` (aliases, change history, type corrections), `proposals.jsonl`,
  `ref_queries.json` (#115) and `documents/` (sources without their secrets, metadata, normalized text and originals).
- `vectors/` (optional): the chunks of the search index with their embeddings.

What never goes in: members, API tokens, AI engines, notification channels (their secrets are sealed with this instance's key),
federation grants, jobs and the graph's snapshots, which are separate graphs.

Secrets (#116): every text goes through the detector before it is packaged, whatever the brain's policy. A certain secret is masked;
a possible one is only counted. A graph with a certain secret goes without its dump, which cannot be edited, and only as JSON, masked.
A document whose original had or has a certain secret, or whose text was never checked, goes without its original.
"""
import hashlib
import json
import os
import secrets
import shutil
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from starlette.background import BackgroundTask

from . import docstore, index, jobs, packcrypt, secretguard
from .config import settings
from .db import client
from .deps import BrainCtx, admin_of_brain, audit
from .i18n import tr
from .models import (Brain, BrainOntology, DocSource, Document, Job, Proposal, RefQuery, RefRun, RetypeSuggestion, User, VocabAlias,
                     VocabOp)
from .secretscan import redact, scan
from .store import _factory

KIND = "brain.export"
FORMAT_VERSION = 1
PAGE = 1000  # graph rows per query: FalkorDB caps result sets and times out long queries
EXCLUDED = ["members", "api_tokens", "ai_engines", "notification_channels", "federation_grants", "jobs", "graph_snapshots"]
_PASSWORDS: dict[str, str] = {}  # only in memory and only until the job starts: job params are stored and shown

router = APIRouter(prefix="/api/brains/{slug}/exports")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dir(jid: int) -> Path:
    return docstore.root() / "_exports" / str(int(jid))


def _val(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _row(obj, skip: set[str] = frozenset()) -> dict:
    return {c.key: _val(getattr(obj, c.key)) for c in obj.__table__.columns if c.key not in skip}


def _dump(v) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


class _Guard:
    """Masks the certain secrets of what goes into the package and counts what it finds: the rule, never the value."""

    def __init__(self, brain: Brain):
        lang = secretguard.instance_lang()
        self.allow, self.names = brain.secret_allow or "", secretguard.labels(lang)
        self.marker = tr("[secreto eliminado: {{label}}]", lang, label="{label}")
        self.masked: dict[str, int] = {}
        self.flagged: dict[str, int] = {}

    def text(self, s):
        """The text to package and whether it had a certain secret."""
        if not isinstance(s, str) or not s:
            return s, False
        found = scan(s, self.allow)
        for f in found:
            d = self.masked if f.certain else self.flagged
            d[f.rule] = d.get(f.rule, 0) + 1
        if not any(f.certain for f in found):
            return s, False
        return redact(s, found, marker=self.marker, labels=self.names), True

    def has(self, s) -> bool:
        """Whether a text holds a certain secret, without counting it (it was counted where it came from)."""
        return isinstance(s, str) and any(f.certain for f in scan(s, self.allow))


def _props(props: dict, guard: _Guard, vectors: bool) -> tuple[dict, dict, bool]:
    out, vec, hit = {}, {}, False
    for k, v in props.items():
        if k.endswith("_embedding") and isinstance(v, list):  # Graphiti's vectors: name_embedding, fact_embedding
            if vectors:
                vec[k] = v
            continue
        if isinstance(v, str):
            v, h = guard.text(v)
            hit |= h
        elif isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            checked = [guard.text(x) for x in v]
            v, hit = [x for x, _ in checked], hit or any(h for _, h in checked)
        out[k] = v
    return out, vec, hit


def _falkor_version() -> dict:
    out: dict = {}
    try:
        conn = client().connection
        out["redis"] = conn.info("server").get("redis_version")
        for m in conn.execute_command("MODULE", "LIST"):
            d = dict(zip(*[iter(x.decode() if isinstance(x, bytes) else x for x in m)] * 2))
            if d.get("name") == "graph":
                out["graph_module"] = d.get("ver")
    except Exception:  # noqa: BLE001  (the version is informative: the dump's own header is what decides)
        pass
    return out


def _graph(job: jobs.JobCtx, name: str, stage: Path, guard: _Guard, vectors: bool, say) -> dict:
    (stage / "graph").mkdir()
    c = client()
    if name not in c.list_graphs():
        (stage / "graph" / "nodes.jsonl").touch()
        (stage / "graph" / "edges.jsonl").touch()
        return {"name": name, "nodes": 0, "edges": 0, "dump": None, "dump_omitted": "no_graph"}
    g, secret, counts = c.select_graph(name), False, {}
    for what, q in (("nodes", f"MATCH (n) WHERE id(n) > $last RETURN id(n), labels(n), properties(n) ORDER BY id(n) LIMIT {PAGE}"),
                    ("edges", f"MATCH (a)-[e]->(b) WHERE id(e) > $last RETURN id(e), type(e), id(a), id(b), properties(e) ORDER BY id(e) LIMIT {PAGE}")):
        n, last = 0, -1
        with open(stage / "graph" / f"{what}.jsonl", "w", encoding="utf-8") as f:
            while True:
                job.check()
                rows = g.query(q, {"last": last}).result_set
                for r in rows:
                    p, v, hit = _props(r[-1] or {}, guard, vectors)
                    secret |= hit
                    item = {"id": r[0], "labels": r[1]} if what == "nodes" else {"id": r[0], "type": r[1], "source": r[2], "target": r[3]}
                    f.write(_dump({**item, "props": p, **({"vectors": v} if v else {})}) + "\n")
                n += len(rows)
                say(f"{what}: {n}")
                if len(rows) < PAGE:
                    break
                last = rows[-1][0]
        counts[what] = n
    out = {"name": name, **counts, "dump": None, "dump_omitted": None}
    if secret:
        out["dump_omitted"] = "secrets"
    else:
        (stage / "graph" / "graph.dump").write_bytes(c.connection.dump(name))
        out["dump"] = "graph/graph.dump"
    return out


def _names(db, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    return {u.id: (u.display_name or u.name) for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


def _proposals(db, brain: Brain, stage: Path, guard: _Guard) -> int:
    rows = db.scalars(select(Proposal).where(Proposal.brain_id == brain.id).order_by(Proposal.id)).all()
    who = _names(db, {p.author_id for p in rows} | {p.reviewer_id for p in rows})
    with open(stage / "proposals.jsonl", "w", encoding="utf-8") as f:
        for p in rows:
            d = _row(p, {"brain_id", "token_id", "author_id", "reviewer_id"})
            hit = False
            for k in ("name", "body", "review_note", "source_description"):
                d[k], h = guard.text(d[k])
                hit |= h
            if hit:  # the stored positions no longer match the masked text
                d["secret_findings"], d["masked_on_export"] = None, True
            f.write(_dump({**d, "author": who.get(p.author_id, ""), "reviewer": who.get(p.reviewer_id, "")}) + "\n")
    return len(rows)


def _link(src: Path, dst: Path) -> None:
    try:
        os.link(src, dst)  # uploads live in the same volume: no copy
    except OSError:
        shutil.copyfile(src, dst)


def _documents(job: jobs.JobCtx, db, brain: Brain, stage: Path, guard: _Guard, step) -> tuple[dict, set[int]]:
    """Sources, metadata, normalized text and originals. Returns the counts and the documents whose text had a certain secret."""
    base = stage / "documents"
    base.mkdir()
    sources = {s.id: s for s in db.scalars(select(DocSource).where(DocSource.brain_id == brain.id).order_by(DocSource.id))}
    (base / "sources.json").write_text(_dump([{**_row(s, {"brain_id", "created_by", "config", "status", "last_error"}),
                                               "config": {k: v for k, v in (s.config or {}).items() if k != "secrets"},
                                               "secrets_removed": sorted((s.config or {}).get("secrets") or {})} for s in sources.values()]),
                                       encoding="utf-8")
    docs = db.scalars(select(Document).where(Document.brain_id == brain.id, Document.status != "deleted").order_by(Document.id)).all()
    tainted: set[int] = set()
    omitted: dict[str, int] = {}
    with open(base / "documents.jsonl", "w", encoding="utf-8") as f:
        for i, d in enumerate(docs):
            job.check()
            step(f"documents: {i + 1}/{len(docs)}")
            out = _row(d, {"brain_id", "created_by", "storage_ref", "text_ref"})
            ddir = base / str(d.id)
            ddir.mkdir()
            hit = False
            out["text"] = None
            if d.text_ref:
                try:
                    t, hit = guard.text(docstore.resolve(d.text_ref).read_text(encoding="utf-8", errors="replace"))
                    (ddir / "text.txt").write_text(t, encoding="utf-8")
                    out["text"] = f"documents/{d.id}/text.txt"
                except (OSError, ValueError):
                    pass
            if hit:
                tainted.add(d.id)
            reason = None
            if hit or any(s.get("action") in ("masked", "blocked") for s in (d.meta or {}).get("secrets") or []):
                reason = "secrets"  # the stored text is masked, the original is not
            elif not out["text"]:
                reason = "unchecked"  # never indexed: nothing says what the original holds
            else:
                src = sources.get(d.source_id)
                try:
                    path = docstore.original_path(d.storage_ref, src.kind, src.config or {}, d.external_id)
                    name = "original" + (docstore.ext_of(d.filename) or path.suffix.lower())
                    _link(path, ddir / name)
                    out["original"] = f"documents/{d.id}/{name}"
                except (OSError, ValueError, AttributeError):
                    reason = "missing"
            if reason:
                out["original"], out["original_omitted"] = None, reason
                omitted[reason] = omitted.get(reason, 0) + 1
            f.write(_dump(out) + "\n")
    return {"sources": len(sources), "documents": len(docs), "originals_omitted": omitted}, tainted


def _vectors(job: jobs.JobCtx, brain: Brain, stage: Path, guard: _Guard, tainted: set[int]) -> dict:
    """The search index with its embeddings. Chunks of a document with a secret, or that hold one, stay out."""
    from .store import engine
    (stage / "vectors").mkdir()
    out = {"doc_chunks": 0, "episode_chunks": 0, "skipped": 0}
    queries = {"doc_chunks": "SELECT document_id, chunk_idx, heading_path, char_start, char_end, page, text, content_hash, "
                             "CAST(embedding AS text) AS embedding FROM doc_chunks WHERE brain_id = :b ORDER BY document_id, chunk_idx",
               "episode_chunks": "SELECT episode_uuid, chunk_idx, name, text, valid_at, content_hash, CAST(embedding AS text) AS embedding "
                                 "FROM episode_chunks WHERE brain_id = :b ORDER BY episode_uuid, chunk_idx"}
    with engine().connect() as c:
        for table, q in queries.items():
            with open(stage / "vectors" / f"{table}.jsonl", "w", encoding="utf-8") as f:
                for r in c.execution_options(stream_results=True, yield_per=500).execute(text(q), {"b": brain.id}).mappings():
                    if out[table] % 500 == 0:
                        job.check()
                    d = {k: _val(v) for k, v in r.items()}
                    if d.get("document_id") in tainted or guard.has(d["text"]):
                        out["skipped"] += 1
                        continue
                    d["embedding"] = json.loads(d["embedding"]) if d["embedding"] else None
                    f.write(_dump(d) + "\n")
                    out[table] += 1
    return out


def _curation(db, brain: Brain, stage: Path) -> dict:
    onto = db.get(BrainOntology, brain.id)
    (stage / "ontology.json").write_text(_dump(onto.data if onto else None), encoding="utf-8")
    ops = db.scalars(select(VocabOp).where(VocabOp.brain_id == brain.id).order_by(VocabOp.id)).all()
    who = _names(db, {o.user_id for o in ops})
    vocab = {"aliases": [_row(a, {"brain_id", "created_by"}) for a in db.scalars(select(VocabAlias).where(VocabAlias.brain_id == brain.id).order_by(VocabAlias.id))],
             "ops": [{**_row(o, {"brain_id", "user_id"}), "user": who.get(o.user_id, "")} for o in ops],
             "retype": [_row(r, {"brain_id"}) for r in db.scalars(select(RetypeSuggestion).where(RetypeSuggestion.brain_id == brain.id).order_by(RetypeSuggestion.id))]}
    (stage / "vocabulary.json").write_text(_dump(vocab), encoding="utf-8")
    refs = [_row(q, {"brain_id", "created_by"}) for q in db.scalars(select(RefQuery).where(RefQuery.brain_id == brain.id).order_by(RefQuery.id))]
    run = db.scalar(select(RefRun).where(RefRun.brain_id == brain.id, RefRun.status == "done").order_by(RefRun.id.desc()).limit(1))
    (stage / "ref_queries.json").write_text(_dump({"queries": refs, "last_run": {k: _val(getattr(run, k)) for k in ("params", "summary", "finished_at")} if run else None}),
                                            encoding="utf-8")
    return {"aliases": len(vocab["aliases"]), "vocab_ops": len(vocab["ops"]), "retype": len(vocab["retype"]), "ref_queries": len(refs)}


def _sha256(path: Path) -> str:
    return docstore.sha256_file(path)


def build(job: jobs.JobCtx, brain_id: int, vectors: bool, password: str | None) -> dict:
    from importlib.metadata import PackageNotFoundError, version

    from .embed import resolve_embedding
    work = _dir(job.id)
    shutil.rmtree(work, ignore_errors=True)
    stage = work / "stage"
    stage.mkdir(parents=True)
    try:
        with _factory()() as db:
            brain = db.get(Brain, brain_id)
            guard = _Guard(brain)
            n_docs = db.query(Document).filter(Document.brain_id == brain.id, Document.status != "deleted").count()
            done, total = 0, 5 + n_docs + (1 if vectors else 0) + (1 if password else 0)

            def step(msg: str) -> None:
                nonlocal done
                done += 1
                job.progress(done, total, msg)

            step("graph")
            graph = _graph(job, brain.graph_name, stage, guard, vectors, lambda m: job.progress(done, total, m))
            step("proposals")
            counts = {"proposals": _proposals(db, brain, stage, guard)}
            docs, tainted = _documents(job, db, brain, stage, guard, step)
            counts.update(docs)
            step("curation")
            counts.update(_curation(db, brain, stage))
            (stage / "brain.json").write_text(_dump(_row(brain, {"id", "created_by"})), encoding="utf-8")
            vec = None
            if vectors:
                step("vectors")
                vec = _vectors(job, brain, stage, guard, tainted) if index.enabled() else {"skipped_reason": "no_index"}
            slug = brain.slug
        try:
            app_version = version("mimirsynth")
        except PackageNotFoundError:
            app_version = "0.0.0"
        emb = resolve_embedding()
        files = sorted(p for p in stage.rglob("*") if p.is_file())
        secret_summary = {"masked": guard.masked, "flagged": guard.flagged}
        manifest = {"format": "mimirsynth-brain", "format_version": FORMAT_VERSION, "created_at": _now().isoformat(), "mimirsynth": app_version,
                    "falkordb": _falkor_version(), "embedding": {"model": emb["model"], "dim": emb["dim"]},
                    "brain": {"slug": slug, "graph_name": graph["name"]}, "options": {"vectors": vectors, "encrypted": bool(password)},
                    "graph": graph, "counts": counts, "vectors": vec, "secrets": secret_summary, "excluded": EXCLUDED,
                    "files": [{"path": p.relative_to(stage).as_posix(), "size": p.stat().st_size, "sha256": _sha256(p)} for p in files]}
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        step("package")
        name = f"{slug}-{_now():%Y%m%d-%H%M%S}.mimirsynth.tar.gz"
        tar = work / name
        with tarfile.open(tar, "w:gz", compresslevel=6) as t:  # the manifest first: an importer can check it before reading the rest
            t.add(stage / "manifest.json", arcname="manifest.json")
            for p in files:
                job.check()
                t.add(p, arcname=p.relative_to(stage).as_posix())
        shutil.rmtree(stage)
        if password:
            step("encryption")
            packcrypt.encrypt_file(tar, work / (name + ".enc"), password, check=job.check)
            tar.unlink()
            name += ".enc"
        final = work / name
        return {"file": name, "size": final.stat().st_size, "sha256": _sha256(final), "encrypted": bool(password), "vectors": vectors,
                "expires_at": (_now() + timedelta(hours=settings.export_ttl_hours)).isoformat(), "graph": graph, "counts": counts,
                "secrets": secret_summary}
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise


@jobs.register(KIND, "Exportación de un brain", limit=1,
               interrupted="interrumpida por un reinicio del servicio: vuelve a exportar (si llevaba contraseña, solo estaba en memoria y se ha perdido)")
def _run(job: jobs.JobCtx, params: dict) -> dict:
    password = _PASSWORDS.pop(params.get("key") or "", None)
    if params.get("encrypted") and not password:
        raise RuntimeError("la contraseña del cifrado ya no está en memoria (el servicio se ha reiniciado); vuelve a exportar")
    return build(job, job.brain_id, bool(params.get("vectors")), password)


def _expired(j: Job) -> bool:
    exp = (j.result or {}).get("expires_at")
    return bool(exp) and datetime.fromisoformat(exp) < _now()


def purge() -> int:
    """Removes the packages that expired or were downloaded, and what an interrupted export left behind."""
    base = docstore.root() / "_exports"
    if not base.exists():
        return 0
    n = 0
    with _factory()() as db:
        for d in base.iterdir():
            j = db.get(Job, int(d.name)) if d.name.isdigit() else None
            if j and (j.status in ("queued", "running") or (j.status == "done" and not _expired(j) and not (j.result or {}).get("downloaded_at"))):
                continue
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    return n


def _state(j: Job) -> str:
    if j.status != "done":
        return j.status
    r = j.result or {}
    if r.get("downloaded_at"):
        return "downloaded"
    if _expired(j) or not (_dir(j.id) / r.get("file", "")).is_file():
        return "expired"
    return "ready"


class ExportIn(BaseModel):
    vectors: bool = False
    password: str | None = Field(None, max_length=1024)


@router.post("", status_code=202)
def start(body: ExportIn, ctx: BrainCtx = Depends(admin_of_brain)):
    """Starts an export as a job. The password, if any, is only kept in memory until the job starts."""
    if body.password is not None and len(body.password) < packcrypt.MIN_PASSWORD:
        raise HTTPException(400, "la contraseña necesita al menos 12 caracteres")
    if ctx.db.scalar(select(Job.id).where(Job.brain_id == ctx.brain.id, Job.kind == KIND, Job.status.in_(("queued", "running")))):
        raise HTTPException(409, "ya hay una exportación de este brain en marcha")
    key = ""
    if body.password:
        key = secrets.token_urlsafe(16)
        _PASSWORDS[key] = body.password
    audit(ctx.db, ctx.user, "brain.export", ctx.brain, vectors=body.vectors, encrypted=bool(body.password))
    jid = jobs.submit(KIND, ctx.brain.id, {"vectors": body.vectors, "encrypted": bool(body.password), "key": key},
                      f"Exportación de {ctx.brain.slug}", ctx.user.id)
    return {"id": jid}


@router.get("")
def list_exports(ctx: BrainCtx = Depends(admin_of_brain)):
    rows = ctx.db.scalars(select(Job).where(Job.brain_id == ctx.brain.id, Job.kind == KIND).order_by(Job.id.desc()).limit(20)).all()
    who = _names(ctx.db, {j.created_by for j in rows})
    out = []
    for j in rows:
        r = j.result or {}
        out.append({"id": j.id, "state": _state(j), "done": j.progress_done, "total": j.progress_total, "message": j.message, "error": j.error,
                    "user": who.get(j.created_by, ""), "created_at": j.created_at, "finished_at": j.finished_at,
                    "vectors": bool((j.params or {}).get("vectors")), "encrypted": bool((j.params or {}).get("encrypted")),
                    **{k: r.get(k) for k in ("file", "size", "sha256", "expires_at", "downloaded_at", "graph", "counts", "secrets")}})
    return {"ttl_hours": settings.export_ttl_hours, "items": out}


@router.get("/{jid:int}/download")
def download(jid: int, ctx: BrainCtx = Depends(admin_of_brain)):
    """The package, once: it is deleted when sent. An expired or already downloaded one answers 410."""
    j = ctx.db.get(Job, jid)
    if not j or j.brain_id != ctx.brain.id or j.kind != KIND or j.status != "done":
        raise HTTPException(404, "exportación no encontrada")
    state = _state(j)
    if state == "downloaded":
        raise HTTPException(410, "esta exportación ya se ha descargado; vuelve a exportar")
    if state == "expired":
        raise HTTPException(410, "esta exportación ha caducado; vuelve a exportar")
    r = dict(j.result)
    p = _dir(jid) / r["file"]
    sending = p.with_name(p.name + ".sending")
    try:
        os.rename(p, sending)  # whoever renames it first is the only one who gets it
    except OSError:
        raise HTTPException(410, "esta exportación ya se ha descargado; vuelve a exportar") from None
    j.result = {**r, "downloaded_at": _now().isoformat()}
    ctx.db.commit()
    audit(ctx.db, ctx.user, "brain.export.download", ctx.brain, job=jid, size=r.get("size"), encrypted=bool(r.get("encrypted")))
    return FileResponse(sending, media_type="application/octet-stream", filename=r["file"], content_disposition_type="attachment",
                        background=BackgroundTask(shutil.rmtree, _dir(jid), True))
