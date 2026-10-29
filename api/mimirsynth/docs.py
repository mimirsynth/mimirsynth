"""Memoria documental: subida por partes, indexación en segundo plano, búsqueda híbrida, descarga y contexto ampliado.
Los originales viven en el almacén de ficheros; la base de datos guarda la referencia, los trozos y sus vectores."""
import hashlib
import json
import logging
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from . import appsettings, docindex, docstore, index, jobs
from .config import settings
from .deps import BrainCtx, audit, contributor_of_brain, reader
from .docextract import ExtractError, chunk, extract
from .embed import gate, get_embedder
from .models import Brain, DocSource, Document
from .roles import allows
from .store import _factory

log = logging.getLogger("mimirsynth.docs")
router = APIRouter(prefix="/api/brains/{slug}/docs")
_PROGRESS: dict[int, dict] = {}
_SEM = threading.Semaphore(2)  # indexaciones simultáneas (los embeddings comparten motor)
EMBED_BATCH = 48


# --- indexación -------------------------------------------------------------------------------

def _embed(texts: list[str]) -> list[list[float]]:
    for attempt in range(1, 5):
        try:
            return get_embedder().embed(texts)
        except Exception:  # noqa: BLE001
            if attempt == 4:
                raise
            time.sleep(4 * attempt)
    return []


def run_index(doc_id: int, job: "jobs.JobCtx | None" = None) -> str:
    """Extrae, trocea, calcula embeddings y sustituye los trozos del documento. Deja el resultado en su estado (active | error)
    y devuelve el error (vacío si fue bien)."""
    with _SEM, _factory()() as db:
        d = db.get(Document, doc_id)
        if not d:
            return ""
        d.status, d.error = "indexing", ""
        db.commit()
        try:
            if not index.enabled():
                raise RuntimeError("el índice documental requiere PostgreSQL con pgvector")
            src = db.get(DocSource, d.source_id)
            path = docstore.original_path(d.storage_ref, src.kind, src.config or {}, d.external_id)
            text, title = extract(path, docstore.ext_of(d.filename) or path.suffix)
            tdir = docstore.doc_dir(d.brain_id, d.source_id, d.id)
            tdir.mkdir(parents=True, exist_ok=True)
            tpath = tdir / f"{d.sha256}.norm.txt"
            tpath.write_text(text, encoding="utf-8")
            d.text_ref = docstore.rel(tpath)
            chunks = chunk(text)
            if not chunks:
                raise ExtractError("el documento no tiene contenido")
            if title and (d.meta or {}).get("title_auto"):
                d.title = title[:500]
            vecs: list[list[float]] = []
            _PROGRESS[doc_id] = {"done": 0, "total": len(chunks)}
            with gate.writing():  # vectores y trozos del mismo motor aunque se esté cambiando de modelo (ver reembed)
                for i in range(0, len(chunks), EMBED_BATCH):
                    if job:
                        job.check()
                    batch = chunks[i:i + EMBED_BATCH]
                    vecs += _embed([f"{d.title}\n{c['heading_path']}\n{c['text']}" for c in batch])
                    _PROGRESS[doc_id]["done"] = min(i + EMBED_BATCH, len(chunks))
                    if job:
                        job.progress(_PROGRESS[doc_id]["done"], len(chunks), "calculando embeddings")
                docindex.replace_chunks(d.brain_id, d.id, chunks, vecs, d.sha256)
            d.chunks, d.status = len(chunks), "active"
        except jobs.Cancelled:
            d.status, d.error = "error", "indexación cancelada"
            _PROGRESS.pop(doc_id, None)
            db.commit()
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("indexación fallida del documento %s", doc_id)
            d.status, d.error = "error", str(e)[:500]
        _PROGRESS.pop(doc_id, None)
        d.last_seen_at = datetime.now(timezone.utc)
        db.commit()
        return d.error if d.status == "error" else ""


@jobs.register("doc.index", "Indexar documento", limit=2, resume=True)
def _job_index(ctx: "jobs.JobCtx", p: dict) -> dict:
    ctx.progress(0, 0, "extrayendo y troceando")
    err = run_index(p["doc_id"], ctx)
    if err:
        raise RuntimeError(err)
    with _factory()() as db:
        d = db.get(Document, p["doc_id"])
        return {"chunks": d.chunks if d else 0}


def start_index(doc_id: int, user_id: int | None = None) -> int | None:
    with _factory()() as db:
        d = db.get(Document, doc_id)
        if not d:
            return None
        brain_id, title = d.brain_id, d.title or d.filename
    return jobs.submit("doc.index", brain_id, {"doc_id": doc_id}, f"Indexar «{title}»", user_id, dedupe_key=f"doc.index:{doc_id}")


# --- utilidades -------------------------------------------------------------------------------

def _upload_source(db, brain: Brain, user_id: int | None) -> DocSource:
    s = db.scalar(select(DocSource).where(DocSource.brain_id == brain.id, DocSource.kind == "upload"))
    if not s:
        s = DocSource(brain_id=brain.id, kind="upload", name="Subidas", created_by=user_id)
        db.add(s)
        db.commit()
    return s


def _out(d: Document, source_name: str = "") -> dict:
    return {"id": d.id, "source_id": d.source_id, "source": source_name, "title": d.title, "filename": d.filename, "mime": d.mime, "size": d.size,
            "sha256": d.sha256, "status": d.status, "error": d.error, "chunks": d.chunks, "progress": _PROGRESS.get(d.id),
            "created_at": d.first_seen_at, "updated_at": d.source_updated_at or d.last_seen_at, "url": d.url, "external_id": d.external_id}


def _doc(ctx: BrainCtx, doc_id: int) -> Document:
    d = ctx.db.get(Document, doc_id)
    if not d or d.brain_id != ctx.brain.id:
        raise HTTPException(404, "documento no encontrado")
    return d


# --- lectura ----------------------------------------------------------------------------------

def _public_config(s: DocSource) -> dict:
    """Configuración de la fuente sin secretos: de una wiki se devuelve solo lo no sensible y si tiene clave."""
    c = dict(s.config or {})
    if s.kind == "wiki":
        return {"adapter": c.get("adapter"), "settings": c.get("settings", {}), "collection_ids": c.get("collection_ids", []), "secrets_set": sorted((c.get("secrets") or {}).keys())}
    return c if s.kind == "directory" else {}


@router.get("/sources")
def sources(ctx: BrainCtx = Depends(reader)):
    out = []
    for s in ctx.db.scalars(select(DocSource).where(DocSource.brain_id == ctx.brain.id).order_by(DocSource.id)):
        counts = dict(ctx.db.execute(select(Document.status, func.count()).where(Document.source_id == s.id).group_by(Document.status)).all())
        out.append({"id": s.id, "kind": s.kind, "name": s.name, "config": _public_config(s), "sync_interval": s.sync_interval, "enabled": s.enabled, "status": s.status, "last_sync_at": s.last_sync_at,
                    "last_error": s.last_error, "documents": sum(counts.values()), "by_status": counts})
    return {"enabled": index.enabled(), "sources": out}


SORTS = {"updated": func.coalesce(Document.source_updated_at, Document.last_seen_at), "title": func.lower(Document.title), "size": Document.size, "chunks": Document.chunks}


@router.get("")
def list_documents(q: str = Query("", max_length=200), status: str = "", source_id: int | None = None, path: str = Query("", max_length=300),
                   sort: str = "updated", order: str = "desc", limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), ctx: BrainCtx = Depends(reader)):
    """Lista paginada de documentos con filtros (texto en título/fichero, fuente, estado, carpeta) y orden. `status_counts` cuenta por estado con el resto de filtros aplicados."""
    def esc(t: str) -> str:  # los % y _ del usuario no son comodines
        return t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    conds = [Document.brain_id == ctx.brain.id, Document.status != "deleted"]
    if q.strip():
        like = f"%{esc(q.strip())}%"
        conds.append(Document.title.ilike(like, escape="\\") | Document.filename.ilike(like, escape="\\"))
    if source_id:
        conds.append(Document.source_id == source_id)
    if path.strip():
        pth = path.strip().strip("/")
        conds.append(Document.external_id.like(f"{esc(pth)}/%", escape="\\") | (Document.external_id == pth))
    counts = dict(ctx.db.execute(select(Document.status, func.count()).where(*conds).group_by(Document.status)).all())
    if status:
        conds.append(Document.status == status)
    stmt = select(Document, DocSource.name).join(DocSource, DocSource.id == Document.source_id).where(*conds)
    total = ctx.db.scalar(select(func.count()).select_from(Document).where(*conds))
    key = SORTS.get(sort, SORTS["updated"])
    rows = ctx.db.execute(stmt.order_by(key.asc() if order == "asc" else key.desc(), Document.id.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "limit": limit, "offset": offset, "status_counts": counts, "items": [_out(d, n) for d, n in rows]}


@router.get("/search")
def search(q: str = Query(min_length=2, max_length=500), k: int = Query(8, ge=1, le=30), source_id: int | None = None, ctx: BrainCtx = Depends(reader)):
    if not index.enabled():
        return {"enabled": False, "results": []}
    try:
        qvec = get_embedder().embed([q])[0]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"el motor de embeddings no responde: {str(e)[:120]}")
    out = []
    for r in docindex.search(ctx.brain.id, qvec, q, k=k, source_id=source_id):
        cite = r["title"] + (f" › {r['heading_path']}" if r["heading_path"] else "") + (f" (p. {r['page']})" if r["page"] else "")
        out.append({"document_id": r["document_id"], "chunk": r["chunk_idx"], "title": r["title"], "citation": cite, "heading_path": r["heading_path"], "page": r["page"],
                    "text": r["text"], "similarity": r["similarity"], "score": r["score"], "url": r["url"], "filename": r["filename"],
                    "char_start": r["char_start"], "char_end": r["char_end"], "updated_at": r["source_updated_at"] or r["last_seen_at"]})
    return {"enabled": True, "results": out}


@router.get("/{doc_id:int}")
def detail(doc_id: int, chunks: int = Query(0, le=500), ctx: BrainCtx = Depends(reader)):
    d = _doc(ctx, doc_id)
    src = ctx.db.get(DocSource, d.source_id)
    return {**_out(d, src.name if src else ""), "chunk_list": docindex.list_chunks(d.id, limit=chunks) if chunks else []}


@router.get("/{doc_id:int}/text")
def full_text(doc_id: int, ctx: BrainCtx = Depends(reader)):
    """Texto normalizado completo del documento (el que se trocea), con tope de 1 MB para la pantalla."""
    d = _doc(ctx, doc_id)
    if not d.text_ref:
        raise HTTPException(404, "el documento aún no tiene texto extraído")
    p = docstore.resolve(d.text_ref)
    if not p.is_file():
        raise HTTPException(404, "el texto extraído ya no está disponible")
    raw = p.read_text(encoding="utf-8")
    cap = 1024 * 1024
    return {"document_id": d.id, "title": d.title, "chars": len(raw), "truncated": len(raw) > cap, "text": raw[:cap]}


@router.get("/{doc_id:int}/file")
def download(doc_id: int, ctx: BrainCtx = Depends(reader)):
    d = _doc(ctx, doc_id)
    src = ctx.db.get(DocSource, d.source_id)
    try:
        p = docstore.original_path(d.storage_ref, src.kind, src.config or {}, d.external_id)
    except ValueError:
        raise HTTPException(404, "fichero no disponible")
    if not p.is_file():
        raise HTTPException(404, "el fichero original ya no está disponible")
    return FileResponse(p, media_type=d.mime or "application/octet-stream", filename=d.filename or p.name, content_disposition_type="attachment",
                        headers={"X-Content-Type-Options": "nosniff"})


@router.get("/{doc_id:int}/context")
def context(doc_id: int, chunk_idx: int = Query(alias="chunk", ge=0), radius: int = Query(1, ge=0, le=5), ctx: BrainCtx = Depends(reader)):
    """Texto ampliado alrededor de un pasaje: va del inicio del trozo anterior al fin del posterior, leído del texto normalizado."""
    d = _doc(ctx, doc_id)
    near = docindex.neighbors(d.id, chunk_idx, radius)
    if not near or not d.text_ref:
        raise HTTPException(404, "pasaje no encontrado")
    a, b = min(n["char_start"] for n in near), max(n["char_end"] for n in near)
    b = min(b, a + 20000)
    txt = docstore.resolve(d.text_ref).read_text(encoding="utf-8")[a:b]
    return {"document_id": d.id, "title": d.title, "from_chunk": near[0]["chunk_idx"], "to_chunk": near[-1]["chunk_idx"], "char_start": a, "char_end": b, "text": txt}


# --- escritura --------------------------------------------------------------------------------

@router.delete("/{doc_id:int}")
def delete_document(doc_id: int, ctx: BrainCtx = Depends(contributor_of_brain)):
    d = _doc(ctx, doc_id)
    src = ctx.db.get(DocSource, d.source_id)
    if src and src.kind != "upload":
        raise HTTPException(409, "el documento pertenece a una fuente sincronizada: quítalo de su origen o elimina la fuente")
    if not allows(ctx.role, "admin") and d.created_by != ctx.user.id:
        raise HTTPException(403, "solo un administrador o quien lo subió puede borrar el documento")
    docindex.delete_document(d.id)
    docstore.remove_document(d.brain_id, d.source_id, d.id)
    title = d.title
    ctx.db.delete(d)
    ctx.db.commit()
    audit(ctx.db, ctx.user, "document.delete", ctx.brain, id=doc_id, title=title)
    return {"ok": True}


@router.post("/{doc_id:int}/reindex")
def reindex(doc_id: int, ctx: BrainCtx = Depends(contributor_of_brain)):
    d = _doc(ctx, doc_id)
    if not allows(ctx.role, "admin"):
        raise HTTPException(403, "requiere rol admin o superior")
    if d.status == "indexing":
        raise HTTPException(409, "ya se está indexando")
    start_index(d.id, ctx.user.id)
    audit(ctx.db, ctx.user, "document.reindex", ctx.brain, id=doc_id)
    return {"ok": True}


# --- subida por partes ------------------------------------------------------------------------

class UploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    size: int = Field(gt=0)
    title: str = Field("", max_length=500)


def _meta(uid: str, ctx: BrainCtx) -> tuple[Path, dict]:
    d = docstore.uploads_dir() / uid
    try:
        if not uid.isalnum() or not d.is_dir():
            raise FileNotFoundError
        m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "subida no encontrada")
    if m["brain_id"] != ctx.brain.id or m["user_id"] != ctx.user.id:
        raise HTTPException(404, "subida no encontrada")
    return d, m


@router.post("/uploads", status_code=201)
def upload_init(body: UploadIn, ctx: BrainCtx = Depends(contributor_of_brain)):
    ext = docstore.ext_of(body.filename)
    if ext not in docstore.ALLOWED_EXT:
        raise HTTPException(415, f"formato no admitido ({ext or 'sin extensión'}). Admitidos: {', '.join(sorted(docstore.ALLOWED_EXT))}")
    if body.size > appsettings.get("doc_max_mb") * 1024 * 1024:
        raise HTTPException(413, f"supera el máximo de {appsettings.get('doc_max_mb')} MB")
    uid = uuid.uuid4().hex
    d = docstore.uploads_dir() / uid
    d.mkdir()
    (d / "meta.json").write_text(json.dumps({"brain_id": ctx.brain.id, "user_id": ctx.user.id, "filename": docstore.clean_name(body.filename), "size": body.size, "title": body.title}), encoding="utf-8")
    return {"upload_id": uid, "part_size": min(appsettings.get("doc_part_mb"), 64) * 1024 * 1024}


@router.put("/uploads/{uid}/parts/{n:int}")
async def upload_part(uid: str, n: int, request: Request, ctx: BrainCtx = Depends(contributor_of_brain)):
    d, m = _meta(uid, ctx)
    if n < 0 or n > 100000:
        raise HTTPException(400, "número de parte inválido")
    limit = appsettings.get("doc_part_mb") * 1024 * 1024
    tmp, size = d / f"part-{n:06d}.tmp", 0
    with open(tmp, "wb") as f:
        async for blk in request.stream():
            size += len(blk)
            if size > limit:
                f.close(); tmp.unlink(missing_ok=True)
                raise HTTPException(413, "la parte supera el tamaño máximo")
            f.write(blk)
    tmp.replace(d / f"part-{n:06d}")
    return {"part": n, "bytes": size}


@router.delete("/uploads/{uid}")
def upload_abort(uid: str, ctx: BrainCtx = Depends(contributor_of_brain)):
    d, _ = _meta(uid, ctx)
    shutil.rmtree(d, ignore_errors=True)
    return {"ok": True}


@router.post("/uploads/{uid}/complete", status_code=201)
def upload_complete(uid: str, ctx: BrainCtx = Depends(contributor_of_brain)):
    d, m = _meta(uid, ctx)
    parts = sorted(p for p in d.iterdir() if p.name.startswith("part-") and not p.name.endswith(".tmp"))
    if [p.name for p in parts] != [f"part-{i:06d}" for i in range(len(parts))] or not parts:
        raise HTTPException(409, "faltan partes de la subida")
    whole, h, total = d / "assembled", hashlib.sha256(), 0
    with open(whole, "wb") as out:
        for p in parts:
            with open(p, "rb") as f:
                for blk in iter(lambda: f.read(1 << 20), b""):
                    h.update(blk); total += len(blk); out.write(blk)
    if total != m["size"]:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(409, f"el tamaño recibido ({total}) no coincide con el declarado ({m['size']})")
    sha = h.hexdigest()
    dup = ctx.db.scalar(select(Document).where(Document.brain_id == ctx.brain.id, Document.sha256 == sha, Document.status != "deleted"))
    if dup:
        shutil.rmtree(d, ignore_errors=True)
        return {**_out(dup), "duplicate": True}
    src = _upload_source(ctx.db, ctx.brain, ctx.user.id)
    ext = docstore.ext_of(m["filename"])
    title = (m.get("title") or "").strip()
    doc = Document(brain_id=ctx.brain.id, source_id=src.id, external_id=uid, title=title or Path(m["filename"]).stem, filename=m["filename"], size=total, sha256=sha,
                   mime=_mime(ext), status="pending", created_by=ctx.user.id, meta={"title_auto": not title})
    ctx.db.add(doc)
    ctx.db.commit()
    dest = docstore.doc_dir(ctx.brain.id, src.id, doc.id)
    dest.mkdir(parents=True, exist_ok=True)
    final = dest / f"{sha}{ext}"
    shutil.move(str(whole), final)
    doc.storage_ref = docstore.rel(final)
    ctx.db.commit()
    shutil.rmtree(d, ignore_errors=True)
    audit(ctx.db, ctx.user, "document.upload", ctx.brain, id=doc.id, filename=m["filename"], size=total)
    start_index(doc.id, ctx.user.id)
    return {**_out(doc, src.name), "duplicate": False}


def _mime(ext: str) -> str:
    return {".md": "text/markdown", ".markdown": "text/markdown", ".txt": "text/plain", ".rst": "text/x-rst", ".log": "text/plain",
            ".html": "text/html", ".htm": "text/html", ".pdf": "application/pdf"}.get(ext, "application/octet-stream")
