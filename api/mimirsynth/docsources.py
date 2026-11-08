"""Fuentes de documentos de tipo directorio: una carpeta del servidor (montada en solo lectura) que se referencia sin copiar y se reescanea.
El reescaneo detecta ficheros nuevos, cambiados y desaparecidos por tamaño, fecha y sha256, e indexa solo lo que cambió."""
import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

import hashlib
import re

from . import appsettings, docindex, docs, docstore, gitsource, jobs, wikis
from .i18n import SOURCE, tr
from .secretbox import seal, unseal
from .deps import BrainCtx, admin_of_brain, audit
from .models import DocSource, Document
from .store import _factory

log = logging.getLogger("mimirsynth.docsources")
router = APIRouter(prefix="/api/brains/{slug}/docs")
MAX_FILES = 200_000


# --- API --------------------------------------------------------------------------------------

class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    root: str = Field(min_length=1, max_length=80)
    subpath: str = Field("", max_length=300)
    sync_interval: int | None = Field(None, ge=5, le=60 * 24 * 30)  # minutos; vacío = solo manual


class SourcePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    subpath: str | None = Field(None, max_length=300)
    enabled: bool | None = None
    sync_interval: int | None = Field(None, ge=5, le=60 * 24 * 30)
    clear_interval: bool = False
    collection_ids: list[str] | None = Field(None, max_length=500)  # wiki; empty = every collection
    confirm_removed: int | None = None  # wiki: the documents that dropping collections removes from the index, as the form showed them
    values: dict[str, str] | None = None  # wiki: campos de conexión a cambiar (un secreto vacío conserva el guardado)
    branch: str | None = Field(None, max_length=200)  # git: empty = the repository's default branch
    include: list[str] | None = Field(None, max_length=gitsource.MAX_PATTERNS)  # git
    username: str | None = Field(None, max_length=100)  # git
    token: str | None = Field(None, max_length=1000)  # git: empty keeps the stored one
    clear_token: bool = False  # git


def _src(ctx: BrainCtx, sid: int) -> DocSource:
    s = ctx.db.get(DocSource, sid)
    if not s or s.brain_id != ctx.brain.id:
        raise HTTPException(404, "fuente no encontrada")
    return s


def _checked(root: str, subpath: str) -> dict:
    cfg = {"root": root, "subpath": subpath.strip().strip("/")}
    try:
        base = docstore.source_base(cfg)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not base.is_dir():
        raise HTTPException(400, f"la carpeta no existe o no es accesible: {root}/{cfg['subpath']}".rstrip("/"))
    return cfg


@router.get("/roots")
def roots(ctx: BrainCtx = Depends(admin_of_brain)):
    return {"roots": [{"name": n, "available": p.is_dir()} for n, p in sorted(docstore.roots().items())]}


@router.post("/sources", status_code=201)
def create_source(body: SourceIn, ctx: BrainCtx = Depends(admin_of_brain)):
    cfg = _checked(body.root, body.subpath)
    s = DocSource(brain_id=ctx.brain.id, kind="directory", name=body.name.strip(), config=cfg, sync_interval=body.sync_interval, created_by=ctx.user.id)
    ctx.db.add(s)
    ctx.db.commit()
    audit(ctx.db, ctx.user, "docsource.create", ctx.brain, id=s.id, root=cfg["root"], subpath=cfg["subpath"])
    return {"id": s.id, "job": _submit_scan(s, ctx.user.id, manual=True)}


@router.patch("/sources/{sid:int}")
def patch_source(sid: int, body: SourcePatch, request: Request, ctx: BrainCtx = Depends(admin_of_brain)):
    s = _src(ctx, sid)
    if s.kind not in ("directory", "wiki", "git"):
        raise HTTPException(409, "la fuente de subidas no se edita")
    if body.name is not None:
        s.name = body.name.strip()
    if body.subpath is not None and s.kind == "directory":
        s.config = _checked(s.config["root"], body.subpath)
    change: dict = {}
    if s.kind != "git" and (body.branch is not None or body.include is not None or body.token or body.clear_token):
        raise HTTPException(409, "esos campos son de una fuente Git")
    if s.kind == "wiki" and (body.collection_ids is not None or body.values):
        _need_instance_admin(ctx, request)
        cfg = dict(s.config or {})
        if body.values:  # solo se cambian los campos enviados; los secretos vacíos conservan el guardado
            new = wiki_config(cfg["adapter"], {k: v for k, v in body.values.items() if v.strip()}, cfg.get("collection_ids", []))
            cfg["settings"] = {**cfg.get("settings", {}), **new["settings"]}
            cfg["secrets"] = {**cfg.get("secrets", {}), **new["secrets"]}
            try:
                cfg["collection_names"] = _names(cfg, wikis.make(cfg["adapter"], wiki_values(cfg)).collections())
            except wikis.WikiError as e:
                raise HTTPException(400, str(e))
        if body.collection_ids is not None:
            change = _collections_change(ctx, s, cfg, list(dict.fromkeys(body.collection_ids)), body.confirm_removed)
            cfg["collection_ids"] = change["ids"]
        s.config = cfg
    if s.kind == "git" and (body.branch is not None or body.include is not None or body.username is not None or body.token or body.clear_token):
        _need_instance_admin(ctx, request)
        s.config = _git_patch(s.config or {}, body)
        change = {"scan": True}
    if body.enabled is not None:
        s.enabled = body.enabled
    if body.clear_interval:
        s.sync_interval = None
    elif body.sync_interval is not None:
        s.sync_interval = body.sync_interval
    gone = [d.id for d in change.get("drop", [])]
    for d in change.get("drop", []):  # only the pages of the collections taken out; the originals in the wiki are never touched
        docindex.delete_document(d.id)
        docstore.remove_document(d.brain_id, d.source_id, d.id)
        ctx.db.delete(d)
    ctx.db.commit()
    for doc_id in gone:  # duplicates in other sources whose original was one of these
        docs.promote_duplicates(doc_id)
    names = (s.config or {}).get("collection_names") or {}
    detail = {"collections_added": [names.get(c, c) for c in change["added"]], "collections_removed": [names.get(c, c) for c in change["removed"]],
              "documents_removed": len(gone)} if change.get("changed") else {}
    audit(ctx.db, ctx.user, "docsource.update", ctx.brain, id=s.id, **detail)
    job = _submit_scan(s, ctx.user.id, manual=False) if change.get("scan") else None  # a failed scan removes nothing, as any rescan
    return {"ok": True, "documents_removed": len(gone), "job": job}


def _names(cfg: dict, collections: list[dict]) -> dict[str, str]:
    """The names of the wiki's collections as last seen, to find the collection of pages indexed before their id was stored."""
    return {**(cfg.get("collection_names") or {}), **{c["id"]: c["name"] for c in collections}}


def _collection_of(d: Document, names: dict[str, str]) -> str | None:
    """The collection a wiki page came from: its stored id or, for an older page, the one collection with its name. None: not known."""
    meta = d.meta or {}
    if meta.get("collection_id"):
        return meta["collection_id"]
    ids = [i for i, n in names.items() if n and n == meta.get("collection")]
    return ids[0] if len(ids) == 1 else None


def _per_collection(db, s: DocSource, names: dict[str, str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in db.scalars(select(Document).where(Document.source_id == s.id)):
        c = _collection_of(d, names)
        if c is not None:
            out[c] = out.get(c, 0) + 1
    return out


def _collections_change(ctx: BrainCtx, s: DocSource, cfg: dict, new: list[str], confirmed: int | None) -> dict:
    """What changing the selection does (empty = every collection). Adding asks for a scan. Removing drops the pages of the removed
    collections, only those whose collection is known, once the administrator has confirmed how many."""
    old = cfg.get("collection_ids") or []
    names = cfg.get("collection_names") or {}
    if not new:  # every collection: nothing is removed, and the ones not indexed yet come with a scan
        return {"ids": [], "added": [], "removed": [], "drop": [], "scan": bool(old), "changed": bool(old)}
    added = [c for c in new if c not in old] if old else []
    removed = [c for c in (old or list(names)) if c not in new]
    drop = [d for d in ctx.db.scalars(select(Document).where(Document.source_id == s.id)) if _collection_of(d, names) not in (None, *new)]
    n = len(drop)
    if drop and confirmed != n:
        raise HTTPException(409, f"quitar esas colecciones retira {n} documentos del índice: confírmalo")
    return {"ids": new, "added": added, "removed": removed, "drop": drop, "scan": bool(added), "changed": bool(added or removed or drop)}


@router.delete("/sources/{sid:int}")
def delete_source(sid: int, ctx: BrainCtx = Depends(admin_of_brain)):
    s = _src(ctx, sid)
    if s.kind == "upload":
        raise HTTPException(409, "la fuente de subidas no se elimina")
    gone = []
    for d in ctx.db.scalars(select(Document).where(Document.source_id == s.id)).all():
        docindex.delete_document(d.id)
        docstore.remove_document(d.brain_id, d.source_id, d.id)
        gone.append(d.id)
        ctx.db.delete(d)
    ctx.db.delete(s)
    ctx.db.commit()
    if s.kind == "git":
        gitsource.remove(s.brain_id, s.id)  # the local clone; the repository itself is never touched
    n = len(gone)
    audit(ctx.db, ctx.user, "docsource.delete", ctx.brain, id=sid, documents=n)
    for doc_id in gone:  # duplicados en otras fuentes cuyo original estaba en esta
        docs.promote_duplicates(doc_id)
    return {"ok": True, "documents_removed": n}  # los originales de la carpeta no se tocan


@router.post("/sources/{sid:int}/scan", status_code=202)
def scan_now(sid: int, ctx: BrainCtx = Depends(admin_of_brain)):
    s = _src(ctx, sid)
    if s.kind not in ("directory", "wiki", "git"):
        raise HTTPException(409, "las subidas no se reescanean")
    audit(ctx.db, ctx.user, "docsource.scan", ctx.brain, id=s.id)
    return {"job": _submit_scan(s, ctx.user.id, manual=True)}


def _submit_scan(s: DocSource, user_id: int | None, manual: bool) -> int:
    what = {"wiki": "wiki", "git": "repositorio"}.get(s.kind, "carpeta")
    return jobs.submit("doc.scan", s.brain_id, {"source_id": s.id, "manual": manual}, f"Sincronizar {what} «{s.name}»", user_id, dedupe_key=f"doc.scan:{s.id}")


# --- wiki -------------------------------------------------------------------------------------

class WikiConn(BaseModel):
    adapter: str = Field("outline", max_length=30)
    values: dict[str, str] = Field(default_factory=dict)  # los campos que declara el adaptador (los secretos también: se cifran al guardar)


class WikiIn(WikiConn):
    name: str = Field(min_length=1, max_length=120)
    collection_ids: list[str] = Field(default_factory=list, max_length=500)
    sync_interval: int | None = Field(None, ge=5, le=60 * 24 * 30)


def _need_instance_admin(ctx: BrainCtx, request: Request) -> None:
    """El servidor hace peticiones a la URL que se le da: solo el administrador de la instancia (nunca un token) puede apuntarlo a una wiki."""
    if not ctx.user.is_admin or getattr(request.state, "token", None) is not None:
        raise HTTPException(403, "conectar una wiki requiere administrador de la instancia")


def wiki_config(adapter: str, values: dict, collection_ids: list[str]) -> dict:
    """Separa lo que se puede mostrar de lo que va cifrado."""
    secret = wikis.secret_names(adapter)
    return {"adapter": adapter, "settings": {k: v.strip() for k, v in values.items() if k not in secret and v.strip()},
            "secrets": {k: seal(v.strip()) for k, v in values.items() if k in secret and v.strip()}, "collection_ids": collection_ids}


def wiki_values(cfg: dict) -> dict:
    return {**(cfg.get("settings") or {}), **{k: unseal(v) for k, v in (cfg.get("secrets") or {}).items()}}


@router.get("/wiki/adapters")
def wiki_adapters(ctx: BrainCtx = Depends(admin_of_brain)):
    return {"adapters": wikis.describe()}


@router.post("/wiki/collections")
def wiki_collections(body: WikiConn, request: Request, ctx: BrainCtx = Depends(admin_of_brain)):
    """Comprueba la conexión y devuelve las colecciones disponibles para elegir cuáles indexar. No guarda nada."""
    _need_instance_admin(ctx, request)
    try:
        return {"collections": wikis.make(body.adapter, body.values).collections()}
    except wikis.WikiError as e:
        raise HTTPException(400, str(e))


@router.get("/sources/{sid:int}/wiki/collections")
def source_wiki_collections(sid: int, request: Request, ctx: BrainCtx = Depends(admin_of_brain)):
    """Colecciones disponibles ahora en una wiki ya conectada (con las credenciales guardadas), para cambiar cuáles se indexan sin volver a escribirlas."""
    _need_instance_admin(ctx, request)
    s = _src(ctx, sid)
    if s.kind != "wiki":
        raise HTTPException(409, "la fuente no es una wiki")
    cfg = s.config or {}
    try:
        cols = wikis.make(cfg.get("adapter", ""), wiki_values(cfg)).collections()
    except wikis.WikiError as e:
        raise HTTPException(400, str(e))
    s.config = {**cfg, "collection_names": _names(cfg, cols)}  # so a save right after can tell which pages a collection holds
    ctx.db.commit()
    return {"collections": cols, "selected": cfg.get("collection_ids") or [], "documents": _per_collection(ctx.db, s, s.config["collection_names"])}


@router.post("/sources/wiki", status_code=201)
def create_wiki(body: WikiIn, request: Request, ctx: BrainCtx = Depends(admin_of_brain)):
    _need_instance_admin(ctx, request)
    try:
        cols = wikis.make(body.adapter, body.values).collections()  # valida la conexión antes de guardar
    except wikis.WikiError as e:
        raise HTTPException(400, str(e))
    cfg = wiki_config(body.adapter, body.values, body.collection_ids)
    cfg["collection_names"] = {c["id"]: c["name"] for c in cols}
    s = DocSource(brain_id=ctx.brain.id, kind="wiki", name=body.name.strip(), config=cfg, sync_interval=body.sync_interval, created_by=ctx.user.id)
    ctx.db.add(s)
    ctx.db.commit()
    audit(ctx.db, ctx.user, "docsource.create", ctx.brain, id=s.id, kind="wiki", adapter=body.adapter, collections=len(body.collection_ids))
    return {"id": s.id, "job": _submit_scan(s, ctx.user.id, manual=True)}


# --- git (#118) -------------------------------------------------------------------------------

class GitIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=500)
    branch: str = Field("", max_length=200)  # empty = the repository's default branch
    include: list[str] | None = Field(None, max_length=gitsource.MAX_PATTERNS)  # None = the default paths
    username: str = Field("", max_length=100)
    token: str = Field("", max_length=1000)  # read-only; sealed like every stored secret
    sync_interval: int | None = Field(None, ge=5, le=60 * 24 * 30)


def git_token(cfg: dict) -> str:
    return unseal((cfg.get("secrets") or {}).get("token", ""))


def _git_checked(url: str, branch: str, include: list[str] | None, username: str, token: str) -> dict:
    """The source's settings, validated, after checking that the repository answers with that branch and that token, and that the
    paths select at least one file (#214): if none, saving is refused with the top-level folders, so the form can be fixed."""
    try:
        url, branch, include = gitsource.check_url(url), gitsource.check_branch(branch), gitsource.check_include(include)
        gitsource.probe(url, branch, token, username)
        seen = gitsource.preview(url, branch, include, token, username)  # None: not checked in time, the sync will say it
        if seen is not None and not seen.picked:
            raise ValueError(seen.empty_message())
    except ValueError as e:
        raise HTTPException(400, str(e))
    except gitsource.GitError as e:
        raise HTTPException(400, f"no se pudo conectar con el repositorio: {e}")
    out = {"url": url, "branch": branch, "include": include, "settings": {"username": username.strip()} if username.strip() else {}}
    if seen is not None:
        out["matched"] = seen.counts
    return out


@router.post("/sources/git", status_code=201)
def create_git(body: GitIn, request: Request, ctx: BrainCtx = Depends(admin_of_brain)):
    """A Git repository as a source (#118). The server connects to the address it is given: instance administrator only."""
    _need_instance_admin(ctx, request)
    cfg = _git_checked(body.url, body.branch, body.include, body.username, body.token.strip())
    if body.token.strip():
        cfg["secrets"] = {"token": seal(body.token.strip())}
    s = DocSource(brain_id=ctx.brain.id, kind="git", name=body.name.strip(), config=cfg, sync_interval=body.sync_interval, created_by=ctx.user.id)
    ctx.db.add(s)
    ctx.db.commit()
    audit(ctx.db, ctx.user, "docsource.create", ctx.brain, id=s.id, kind="git", url=cfg["url"], branch=cfg["branch"], token=bool(body.token.strip()))
    return {"id": s.id, "job": _submit_scan(s, ctx.user.id, manual=True)}


def _git_patch(cfg: dict, body: SourcePatch) -> dict:
    """New branch, paths or credentials, checked against the repository. The next sync reads the whole tree again (it forgets the
    commit it last saw), so a path taken out leaves the index and one added comes in."""
    token = "" if body.clear_token else (body.token or "").strip() or git_token(cfg)
    username = (body.username if body.username is not None else (cfg.get("settings") or {}).get("username", "")) or ""
    new = _git_checked(cfg.get("url", ""), cfg.get("branch", "") if body.branch is None else body.branch,
                       cfg.get("include") if body.include is None else body.include, username, token)
    out = {k: v for k, v in cfg.items() if k not in ("commit", "secrets", "matched")}
    out.update(new)
    if token:
        out["secrets"] = {"token": seal(token)} if (body.token or "").strip() else cfg.get("secrets", {})
    return out


def _scan_git(db, s: DocSource, ctx: "jobs.JobCtx", manual: bool) -> dict:
    """Sync of a Git repository by commit: with no new commit nothing is read; otherwise only new or changed files (by their blob)
    are downloaded and indexed, and the ones gone from the chosen paths leave the index. If git fails, nothing is deleted."""
    cfg = s.config or {}
    url, branch, token, username = cfg.get("url", ""), cfg.get("branch", ""), git_token(cfg), (cfg.get("settings") or {}).get("username", "")
    ctx.progress(0, 0, "actualizando el repositorio")
    try:
        d, head = gitsource.fetch(s.brain_id, s.id, url, branch, token, username)
    except (gitsource.GitError, ValueError) as e:
        raise RuntimeError(f"no se pudo actualizar el repositorio: {str(e).rstrip('.')}. No se ha borrado nada")
    existing = {x.external_id: x for x in db.scalars(select(Document).where(Document.source_id == s.id))}
    if head.commit == cfg.get("commit") and not manual:
        ctx.note(f"sin commits nuevos ({head.commit[:12]})")
        return {"added": 0, "changed": 0, "unchanged": len(existing), "removed": 0, "indexed": 0, "errors": 0, "commit": head.commit[:12]}
    found = gitsource.match(gitsource.tree(d, head.commit, url), cfg.get("include") or gitsource.DEFAULT_INCLUDE)
    picked = found.picked
    if len(picked) > gitsource.MAX_FILES:
        raise RuntimeError(f"las rutas elegidas recogen {len(picked)} ficheros, más del límite de {gitsource.MAX_FILES}: acótalas. No se ha borrado nada")
    if not picked and not existing:  # nothing to do and nothing to keep: a failed sync says so, a «done» with 0 files would not (#214)
        raise RuntimeError(found.empty_message())
    if not picked and not manual:
        raise RuntimeError(tr("Ningún fichero coincide con las rutas elegidas, pero la fuente tenía documentos: ¿rama o rutas cambiadas? No se ha "
                              "borrado nada; pulsa «Escanear» si es a propósito. Carpetas de primer nivel del repositorio: {{folders}}.", SOURCE,
                              folders=gitsource.folders(found.top)))
    if not picked:
        ctx.note(found.empty_message())
    ctx.note(f"commit {head.commit[:12]}: {len(picked)} ficheros en las rutas elegidas")
    need = [p for p, blob in picked.items() if p not in existing or (existing[p].meta or {}).get("blob") != blob]
    ctx.progress(0, 0, f"descargando {len(need)} ficheros nuevos o cambiados")
    try:
        gitsource.checkout(d, head.commit, need, url, token, username)
    except gitsource.GitError as e:
        raise RuntimeError(f"no se pudieron descargar los ficheros: {str(e).rstrip('.')}. No se ha borrado nada")
    limit = appsettings.get("doc_max_mb") * 1024 * 1024
    sizes = {p: (d / p).stat().st_size for p in need if (d / p).is_file()}
    if sum(n for n in sizes.values() if n <= limit) > gitsource.MAX_TOTAL_MB * 1024 * 1024:
        raise RuntimeError(f"los ficheros nuevos o cambiados pasan de {gitsource.MAX_TOTAL_MB} MB: acota las rutas. No se ha borrado nada")
    added = changed = unchanged = removed = errors = skipped = 0
    to_index: list[int] = []
    seen: set[str] = set()
    for i, (path, blob) in enumerate(picked.items(), 1):
        ctx.check()
        ctx.progress(i, len(picked), f"comparando: {path[:120]}")
        doc = existing.get(path)
        if doc and (doc.meta or {}).get("blob") == blob:
            seen.add(path)
            unchanged += 1
            if manual and doc.status in ("error", "pending"):
                to_index.append(doc.id)
            continue
        if not 0 < sizes.get(path, 0) <= limit:
            skipped += 1  # empty, too large or not on disk: left out (and out of the index if it was in)
            continue
        try:
            data = gitsource.read(d, path)
        except (OSError, ValueError) as e:
            errors += 1
            ctx.note(f"{path}: no se pudo leer ({str(e)[:100]})")
            continue
        seen.add(path)
        sha = hashlib.sha256(data).hexdigest()
        ext = docstore.ext_of(path)
        meta = {"repo": gitsource.web_base(url) or url, "branch": branch or None, "commit": head.commit, "blob": blob, "path": path, "title_auto": False}
        link = gitsource.web_link(url, head.commit, path) or ""
        if doc:
            old_dir = docstore.doc_dir(doc.brain_id, doc.source_id, doc.id)
            for f in list(old_dir.glob("*")) if old_dir.is_dir() else []:
                f.unlink(missing_ok=True)
            doc.url, doc.size, doc.sha256, doc.source_updated_at, doc.meta, doc.status, doc.error = link, len(data), sha, head.committed_at, meta, "pending", ""
            changed += 1
        else:
            doc = Document(brain_id=s.brain_id, source_id=s.id, external_id=path, title=path[:500], filename=os.path.basename(path), url=link, size=len(data),
                           sha256=sha, mime=docs._mime(ext), status="pending", source_updated_at=head.committed_at, created_by=s.created_by, meta=meta)
            db.add(doc)
            db.flush()
            added += 1
        dest = docstore.doc_dir(doc.brain_id, doc.source_id, doc.id)
        dest.mkdir(parents=True, exist_ok=True)
        snap = dest / f"{sha}{ext}"
        snap.write_bytes(data)  # the file at that commit: the «original» that is downloaded and that the chunks point to
        doc.storage_ref = docstore.rel(snap)
        to_index.append(doc.id)
        if i % 25 == 0:
            db.commit()
    gone: list[int] = []
    for path, doc in existing.items():
        if path not in seen:
            ctx.check()
            docindex.delete_document(doc.id)
            docstore.remove_document(doc.brain_id, doc.source_id, doc.id)
            gone.append(doc.id)
            db.delete(doc)
            removed += 1
    s.config = {**cfg, "commit": head.commit, "commit_at": head.committed_at.isoformat(), "matched": found.counts}
    db.commit()
    for doc_id in gone:  # if one was the original of duplicates, the oldest of them is indexed instead
        docs.promote_duplicates(doc_id)
    ctx.note(f"nuevos {added}, cambiados {changed}, sin cambios {unchanged}, eliminados {removed}" + (f", fuera por tamaño {skipped}" if skipped else ""))
    done, errors = _index_all(db, ctx, to_index, errors)
    return {"added": added, "changed": changed, "unchanged": unchanged, "removed": removed, "indexed": done, "errors": errors, "commit": head.commit[:12]}


# --- reescaneo --------------------------------------------------------------------------------

def _walk(base) -> list[tuple[str, os.stat_result]]:
    """Ficheros admitidos bajo `base`: sin ocultos, sin enlaces que salgan de la carpeta, sin superar el tamaño máximo."""
    from .config import settings
    out: list[tuple[str, os.stat_result]] = []
    limit = appsettings.get("doc_max_mb") * 1024 * 1024
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fn in sorted(filenames):
            if fn.startswith(".") or not docstore.scannable(fn):
                continue
            full = os.path.join(dirpath, fn)
            try:
                real = os.path.realpath(full)
                if os.path.commonpath([str(base), real]) != str(base):
                    continue
                st = os.stat(real)
            except (OSError, ValueError):
                continue
            rel = os.path.relpath(full, base).replace(os.sep, "/")
            if len(rel) > 480 or st.st_size > limit or st.st_size == 0:
                continue
            out.append((rel, st))
            if len(out) >= MAX_FILES:
                return out
    return out


@jobs.register("doc.scan", "Sincronizar fuente", limit=1, resume=True)
def scan_source(ctx: "jobs.JobCtx", p: dict) -> dict:
    manual = bool(p.get("manual"))
    with _factory()() as db:
        s = db.get(DocSource, p["source_id"])
        if not s:
            raise RuntimeError("la fuente ya no existe")
        s.status = "scanning"
        db.commit()
        try:
            res = _scan_wiki(db, s, ctx, manual) if s.kind == "wiki" else _scan_git(db, s, ctx, manual) if s.kind == "git" else _scan(db, s, ctx, manual)
            s.status, s.last_error = "idle", ""
            from . import notify
            notify.resolve("docsource.error", f"source:{s.id}")
            return res
        except jobs.Cancelled:
            s.status, s.last_error = "idle", "escaneo cancelado"
            raise
        except Exception as e:  # noqa: BLE001
            db.rollback()
            s.status, s.last_error = "error", str(e)[:500]
            from . import notify
            notify.emit("docsource.error", f"No se pudo sincronizar la fuente «{s.name}»", s.last_error[:300], brain_id=s.brain_id, key=f"source:{s.id}")
            raise
        finally:
            s.last_sync_at = datetime.now(timezone.utc)
            db.commit()


def _scan(db, s: DocSource, ctx: "jobs.JobCtx", manual: bool) -> dict:
    base = docstore.source_base(s.config or {})
    if not base.is_dir():
        raise RuntimeError(f"la carpeta no está disponible ({s.config.get('root')}/{s.config.get('subpath', '')}): ¿volumen desmontado? No se ha borrado nada")
    ctx.progress(0, 0, "recorriendo la carpeta")
    files = _walk(base)
    existing = {d.external_id: d for d in db.scalars(select(Document).where(Document.source_id == s.id))}
    if not files and existing:
        if not manual:  # un escaneo programado no vacía el índice por su cuenta: podría ser un volumen desmontado
            raise RuntimeError("la carpeta aparece vacía pero la fuente tenía documentos: ¿volumen desmontado? No se ha borrado nada. Pulsa «Escanear» si la has vaciado a propósito")
        ctx.note(f"la carpeta está vacía: se retiran los {len(existing)} documentos del índice (escaneo manual)")
    ctx.note(f"{len(files)} ficheros admitidos en la carpeta")
    added = changed = unchanged = removed = errors = 0
    to_index: list[int] = []
    seen: set[str] = set()
    for i, (rel, st) in enumerate(files, 1):
        ctx.check()
        ctx.progress(i, len(files), f"comparando: {rel[:120]}")
        seen.add(rel)
        d = existing.get(rel)
        mtime = float(st.st_mtime)
        if d and d.size == st.st_size and abs(float((d.meta or {}).get("mtime", -1)) - mtime) < 0.001:
            unchanged += 1
            if manual and d.status in ("error", "pending"):
                to_index.append(d.id)
            continue
        try:
            sha = docstore.sha256_file(docstore.source_file(s.config, rel))
        except (OSError, ValueError) as e:
            errors += 1
            ctx.note(f"{rel}: no se pudo leer ({str(e)[:100]})")
            continue
        meta = {**(d.meta if d else {"title_auto": True}), "mtime": mtime}
        stamp = datetime.fromtimestamp(mtime, tz=timezone.utc)
        if d and d.sha256 == sha:  # solo cambió la fecha
            d.meta, d.size, d.source_updated_at = meta, st.st_size, stamp
            unchanged += 1
            if d.status in ("error", "pending") and manual:
                to_index.append(d.id)
        elif d:
            d.meta, d.size, d.sha256, d.source_updated_at, d.status, d.error = meta, st.st_size, sha, stamp, "pending", ""
            changed += 1
            to_index.append(d.id)
        else:
            nd = Document(brain_id=s.brain_id, source_id=s.id, external_id=rel, title=os.path.splitext(os.path.basename(rel))[0][:500],
                          filename=os.path.basename(rel), size=st.st_size, sha256=sha, mime=docs._mime(docstore.ext_of(rel)), status="pending",
                          source_updated_at=stamp, created_by=s.created_by, meta=meta)
            db.add(nd)
            db.flush()
            added += 1
            to_index.append(nd.id)
        if i % 50 == 0:
            db.commit()
    gone: list[int] = []
    for rel, d in existing.items():  # desaparecidos de la carpeta
        if rel not in seen:
            ctx.check()
            docindex.delete_document(d.id)
            docstore.remove_document(d.brain_id, d.source_id, d.id)
            gone.append(d.id)
            db.delete(d)
            removed += 1
    db.commit()
    for doc_id in gone:  # si alguno era el original de duplicados, el más antiguo pasa a indexarse
        docs.promote_duplicates(doc_id)
    ctx.note(f"nuevos {added}, cambiados {changed}, sin cambios {unchanged}, eliminados {removed}" + (f", errores de lectura {errors}" if errors else ""))
    done, errors = _index_all(db, ctx, to_index, errors)
    return {"added": added, "changed": changed, "unchanged": unchanged, "removed": removed, "indexed": done, "errors": errors}


def _index_all(db, ctx: "jobs.JobCtx", to_index: list[int], errors: int) -> tuple[int, int]:
    """Indexa de uno en uno los documentos nuevos o cambiados, con el progreso en el trabajo. Un fallo no detiene el resto."""
    done = 0
    for n, doc_id in enumerate(dict.fromkeys(to_index), 1):
        ctx.check()
        title = db.get(Document, doc_id).filename
        ctx.progress(n - 1, len(to_index), f"indexando {n}/{len(to_index)}: {title[:100]}")
        err = docs.run_index(doc_id)
        if err:
            errors += 1
            ctx.note(f"{title}: {err[:200]}")
        else:
            done += 1
    return done, errors


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _scan_wiki(db, s: DocSource, ctx: "jobs.JobCtx", manual: bool) -> dict:
    """Reescaneo incremental de una wiki: compara la fecha de modificación de cada página y solo recalcula lo que cambió."""
    cfg = s.config or {}
    api = wikis.make(cfg.get("adapter", ""), wiki_values(cfg))
    ctx.progress(0, 0, "listando las páginas de la wiki")
    pages = []
    for page in api.documents(cfg.get("collection_ids") or []):  # si la wiki falla a mitad, la excepción corta aquí y no se borra nada
        ctx.check()
        pages.append(page)
        if len(pages) % 25 == 0:
            ctx.progress(0, 0, f"listando las páginas de la wiki ({len(pages)})")
    existing = {d.external_id: d for d in db.scalars(select(Document).where(Document.source_id == s.id))}
    if not pages and existing and not manual:
        raise RuntimeError("la wiki no devolvió ninguna página pero la fuente tenía documentos: ¿clave o colecciones cambiadas? No se ha borrado nada. Pulsa «Escanear» si es a propósito")
    ctx.note(f"{len(pages)} páginas en la wiki")
    seen_names = {pg.collection_id: pg.collection for pg in pages if pg.collection_id}
    if seen_names:
        s.config = {**cfg, "collection_names": {**(cfg.get("collection_names") or {}), **seen_names}}
    added = changed = unchanged = removed = errors = 0
    to_index: list[int] = []
    seen: set[str] = set()
    for i, pg in enumerate(pages, 1):
        ctx.check()
        ctx.progress(i, len(pages), f"comparando: {pg.title[:100]}")
        seen.add(pg.id)
        d = existing.get(pg.id)
        stamp = pg.updated_at
        if d and d.source_updated_at and d.source_updated_at.replace(tzinfo=d.source_updated_at.tzinfo or stamp.tzinfo) == stamp and d.title == pg.title[:500]:
            unchanged += 1
            if pg.collection_id and (d.meta or {}).get("collection_id") != pg.collection_id:  # pages indexed before the id was stored
                d.meta = {**(d.meta or {}), "collection": pg.collection, "collection_id": pg.collection_id}
            if manual and d.status in ("error", "pending"):
                to_index.append(d.id)
            continue
        html = pg.format == "html"
        body = pg.read().strip()  # solo ahora se descarga el contenido: una página sin cambios no cuesta ninguna petición
        text = f"<h1>{_esc(pg.title)}</h1>\n{body}\n" if html else f"# {pg.title}\n\n{body}\n"
        data = text.encode("utf-8")
        sha = hashlib.sha256(data).hexdigest()
        if not body:
            unchanged += 1  # página vacía: no hay nada que indexar
            continue
        meta = {"collection": pg.collection, "collection_id": pg.collection_id, "title_auto": False}
        if d and d.sha256 == sha:  # solo cambió la fecha o el título no afecta al texto
            d.source_updated_at, d.meta, d.url = stamp, meta, pg.url
            unchanged += 1
            if manual and d.status in ("error", "pending"):
                to_index.append(d.id)
            continue
        ext = ".html" if html else ".md"
        fname = (re.sub(r"[^\w\- ]+", "", pg.title).strip().replace(" ", "-")[:80] or "pagina") + ext
        if d:
            old_dir = docstore.doc_dir(d.brain_id, d.source_id, d.id)
            for f in list(old_dir.glob("*")) if old_dir.is_dir() else []:
                f.unlink(missing_ok=True)
            d.title, d.filename, d.url, d.size, d.sha256, d.source_updated_at, d.meta, d.status, d.error, d.mime = pg.title[:500], fname, pg.url, len(data), sha, stamp, meta, "pending", "", ("text/html" if html else "text/markdown")
            changed += 1
        else:
            d = Document(brain_id=s.brain_id, source_id=s.id, external_id=pg.id, title=pg.title[:500], filename=fname, url=pg.url, size=len(data), sha256=sha,
                         mime="text/html" if html else "text/markdown", status="pending", source_updated_at=stamp, created_by=s.created_by, meta=meta)
            db.add(d)
            db.flush()
            added += 1
        dest = docstore.doc_dir(d.brain_id, d.source_id, d.id)
        dest.mkdir(parents=True, exist_ok=True)
        snap = dest / f"{sha}{ext}"
        snap.write_bytes(data)  # instantánea de la página: es el «original» que se descarga y sobre el que apuntan los trozos
        d.storage_ref = docstore.rel(snap)
        to_index.append(d.id)
        if i % 25 == 0:
            db.commit()
    gone: list[int] = []
    for ext_id, d in existing.items():
        if ext_id not in seen:
            ctx.check()
            docindex.delete_document(d.id)
            docstore.remove_document(d.brain_id, d.source_id, d.id)
            gone.append(d.id)
            db.delete(d)
            removed += 1
    db.commit()
    for doc_id in gone:  # si alguno era el original de duplicados, el más antiguo pasa a indexarse
        docs.promote_duplicates(doc_id)
    ctx.note(f"nuevas {added}, cambiadas {changed}, sin cambios {unchanged}, eliminadas {removed}")
    done, errors = _index_all(db, ctx, to_index, errors)
    return {"added": added, "changed": changed, "unchanged": unchanged, "removed": removed, "indexed": done, "errors": errors}


# --- reescaneo programado ---------------------------------------------------------------------

def due_sources(now: datetime | None = None) -> list[tuple[int, int]]:
    now = now or datetime.now(timezone.utc)
    out = []
    with _factory()() as db:
        for s in db.scalars(select(DocSource).where(DocSource.kind.in_(("directory", "wiki", "git")), DocSource.enabled.is_(True), DocSource.sync_interval.is_not(None))):
            last = s.last_sync_at.replace(tzinfo=s.last_sync_at.tzinfo or timezone.utc) if s.last_sync_at else None
            if s.status != "scanning" and (last is None or now - last >= timedelta(minutes=s.sync_interval)):
                out.append((s.id, s.brain_id))
    return out


async def periodic() -> None:
    await asyncio.sleep(20)
    last_prune = 0.0
    while True:
        try:
            if time.monotonic() - last_prune > 3600:  # el arranque ya poda; después, una vez por hora
                last_prune = time.monotonic()
                n = await asyncio.to_thread(jobs.prune)
                if n:
                    log.info("trabajos antiguos retirados: %d", n)
                from . import brainexport, brainimport
                await asyncio.to_thread(brainexport.purge)
                await asyncio.to_thread(brainimport.purge)
            for sid, brain_id in await asyncio.to_thread(due_sources):
                jobs.submit("doc.scan", brain_id, {"source_id": sid, "manual": False}, "Escaneo programado de carpeta", None, dedupe_key=f"doc.scan:{sid}")
        except Exception:  # noqa: BLE001
            log.exception("fallo al programar reescaneos")
        await asyncio.sleep(60)
