"""Import a brain from a package made by brainexport (#136): as a new brain, in full or only its structure (ontology and aliases, as
a template).

The package comes from outside, so nothing is written until all of it has been checked:
- the tar holds only regular files, each one listed in the manifest with its size and sha256, under the paths an export writes
  (a fixed list: no `..`, no absolute paths, no links), and every listed file is there;
- the manifest is a known format and version, and its counts match the graph's lines;
- the graph's labels and relation types are plain names (they go into Cypher), every edge joins two nodes of the package and the
  vectors, when they are reused, have the dimension of the embedding model in use.

Then, in one job with progress:
- graph: the JSON copy, in batches, with Graphiti's indices. Only on request («fast restore», for packages one exported oneself) the
  dump (`RESTORE`), when FalkorDB's graph module has the exporter's version: nothing validates an RDB payload as the JSON is
  validated, so what it restored is compared with the JSON copy (labels and relation types with their counts, property names and
  uuids) and, if anything differs, dropped for the JSON copy. `group_id` is always rewritten to the new brain's graph;
- vectors: reused when the embedding model and its dimension are the exporter's; otherwise computed again in the same job (graph,
  episode index and documents);
- PostgreSQL: brain, ontology, vocabulary, type corrections, reference queries, proposals and documents, with new ids.

The importer is the owner. Members, tokens, AI engines and notification channels are set up here; directory and wiki sources come
disabled, without their secrets. A failure removes everything the import created; if the service restarts in the middle, the next
start does it (see `purge`).
"""
import asyncio
import hashlib
from collections import Counter
import json
import logging
import re
import secrets
import shutil
import tarfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, select, text
from sqlalchemy.orm import Session

from . import appsettings, docindex, docstore, index, jobs, packcrypt, secretguard
from .brainexport import FORMAT_VERSION, _falkor_version
from .brains import GRAPH, SLUG, _count
from .config import settings
from .db import client, rows
from .deps import audit, require_admin
from .models import (
    Base,
    Brain,
    BrainOntology,
    DocSource,
    Document,
    Job,
    Membership,
    Proposal,
    RefQuery,
    RetypeSuggestion,
    User,
    VocabAlias,
    VocabOp,
)
from .store import _factory, get_db

log = logging.getLogger("mimirsynth.brainimport")
KIND = "brain.import"
MODES = ("full", "structure")
BATCH = 500  # graph rows per query
EMBED_BATCH = 48
MAX_FILES = 500_000
MAX_JSON = 64 << 20  # the manifest and each single JSON file
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")  # labels and relation types: they go into the Cypher text
VECTORS = ("name_embedding", "fact_embedding")  # Graphiti's, the only ones a package carries
FILES = {"brain.json", "ontology.json", "vocabulary.json", "proposals.jsonl", "ref_queries.json", "graph/graph.dump", "graph/nodes.jsonl",
         "graph/edges.jsonl", "documents/sources.json", "documents/documents.jsonl", "vectors/doc_chunks.jsonl", "vectors/episode_chunks.jsonl"}
DOC_FILE = re.compile(r"^documents/([0-9]{1,12})/(text\.txt|original(\.[A-Za-z0-9_+-]{1,16})?)$")
REQUIRED = {"brain.json", "ontology.json", "vocabulary.json", "proposals.jsonl", "ref_queries.json", "graph/nodes.jsonl", "graph/edges.jsonl",
            "documents/sources.json", "documents/documents.jsonl"}
KEEP = {"audit_log", "jobs"}  # what an undone import leaves: the record that it was tried
_PASSWORDS: dict[str, str] = {}  # only in memory and only until the job starts, as in an export

router = APIRouter(prefix="/api/brain-imports")


class Invalid(ValueError):
    """The package is not one this instance can import; nothing has been written."""


class WrongPassword(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _base() -> Path:
    d = docstore.root() / "_imports"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- the upload, in parts, as documents do ---------------------------------------------------------

class UploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    size: int = Field(gt=0)


def _meta(uid: str, user: User) -> tuple[Path, dict]:
    d = _base() / uid
    try:
        if not re.fullmatch(r"[0-9a-f]{32}", uid) or not d.is_dir():
            raise FileNotFoundError
        m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "subida no encontrada") from None
    if m["user_id"] != user.id:
        raise HTTPException(404, "subida no encontrada")
    return d, m


@router.post("/uploads", status_code=201)
def upload_init(body: UploadIn, user: User = Depends(require_admin)):
    if body.size > settings.import_max_mb * 1024 * 1024:
        raise HTTPException(413, f"supera el máximo de {settings.import_max_mb} MB")
    if shutil.disk_usage(_base()).free < body.size * 2:  # the package and, at least, what it unpacks to
        raise HTTPException(507, "no hay espacio suficiente en el almacén de documentos para importar este paquete")
    uid = uuid.uuid4().hex
    d = _base() / uid
    d.mkdir()
    (d / "meta.json").write_text(json.dumps({"user_id": user.id, "filename": docstore.clean_name(body.filename), "size": body.size}), encoding="utf-8")
    return {"upload_id": uid, "part_size": min(appsettings.get("doc_part_mb"), 64) * 1024 * 1024}


@router.put("/uploads/{uid}/parts/{n:int}")
async def upload_part(uid: str, n: int, request: Request, user: User = Depends(require_admin)):
    d, m = _meta(uid, user)
    if m.get("complete") or n < 0 or n > 100000:
        raise HTTPException(400, "número de parte inválido")
    limit = appsettings.get("doc_part_mb") * 1024 * 1024
    tmp, size = d / f"part-{n:06d}.tmp", 0
    with open(tmp, "wb") as f:
        async for blk in request.stream():
            size += len(blk)
            if size > limit:
                f.close()
                tmp.unlink(missing_ok=True)
                raise HTTPException(413, "la parte supera el tamaño máximo")
            f.write(blk)
    tmp.replace(d / f"part-{n:06d}")
    return {"part": n, "bytes": size}


@router.delete("/uploads/{uid}")
def upload_abort(uid: str, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    d, _ = _meta(uid, user)
    if _busy(db, uid):
        raise HTTPException(409, "este paquete se está importando")
    shutil.rmtree(d, ignore_errors=True)
    return {"ok": True}


@router.post("/uploads/{uid}/complete")
def upload_complete(uid: str, user: User = Depends(require_admin)):
    """Joins the parts and says what the package holds (its manifest), unless it is encrypted."""
    d, m = _meta(uid, user)
    if not m.get("complete"):
        parts = sorted(p for p in d.iterdir() if p.name.startswith("part-") and not p.name.endswith(".tmp"))
        if not parts or [p.name for p in parts] != [f"part-{i:06d}" for i in range(len(parts))]:
            raise HTTPException(409, "faltan partes de la subida")
        total = 0
        with open(d / "package", "wb") as out:
            for p in parts:
                with open(p, "rb") as f:
                    for blk in iter(lambda: f.read(1 << 20), b""):
                        total += len(blk)
                        out.write(blk)
                p.unlink()
        if total != m["size"]:
            shutil.rmtree(d, ignore_errors=True)
            raise HTTPException(409, f"el tamaño recibido ({total}) no coincide con el declarado ({m['size']})")
        m["complete"] = True
        (d / "meta.json").write_text(json.dumps(m), encoding="utf-8")
    try:
        return {"upload_id": uid, **preview(d / "package")}
    except Invalid as e:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(400, f"paquete rechazado: {e}") from None


def _summary(man: dict) -> dict:
    from .embed import resolve_embedding
    emb, here = resolve_embedding(), _falkor_version().get("graph_module")
    theirs = man.get("embedding") or {}
    g = man.get("graph") or {}
    return {"slug": (man.get("brain") or {}).get("slug"), "created_at": man.get("created_at"), "mimirsynth": man.get("mimirsynth"),
            "graph": {"nodes": g.get("nodes"), "edges": g.get("edges"), "dump": bool(g.get("dump")),
                      "same_falkordb": bool(here) and here == (man.get("falkordb") or {}).get("graph_module")},
            "counts": man.get("counts") or {}, "options": man.get("options") or {},
            "embedding": {"model": theirs.get("model"), "dim": theirs.get("dim"), "same": _same_model(man, emb)}}


def preview(pkg: Path) -> dict:
    if packcrypt.is_encrypted(pkg):
        return {"encrypted": True, "manifest": None}
    try:
        with tarfile.open(pkg, "r:gz") as t:
            man = _read_manifest(t)
    except (tarfile.TarError, OSError, EOFError):
        raise Invalid("no es un paquete de MimirSynth (no se puede leer como .tar.gz)") from None
    return {"encrypted": False, "manifest": _summary(man)}


# --- what a package must be --------------------------------------------------------------------------

def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _read_manifest(t: tarfile.TarFile) -> dict:
    first = t.next()
    if first is None or first.name != "manifest.json" or not first.isfile() or first.size > MAX_JSON:
        raise Invalid("el paquete no empieza por su manifiesto")
    try:
        man = json.load(t.extractfile(first))
    except ValueError:
        raise Invalid("el manifiesto no es JSON válido") from None
    _files(man)
    return man


def _files(man) -> dict[str, tuple[int, str]]:
    """The manifest's files, each with its size and sha256, after checking the manifest itself."""
    if not isinstance(man, dict) or man.get("format") != "mimirsynth-brain":
        raise Invalid("no es un paquete de MimirSynth")
    v = man.get("format_version")
    if not _int(v) or v < 1 or v > FORMAT_VERSION:
        raise Invalid(f"versión de paquete {v!r} no admitida (esta instancia lee hasta la {FORMAT_VERSION})")
    g, b = man.get("graph"), man.get("brain")
    if not isinstance(g, dict) or not _int(g.get("nodes")) or not _int(g.get("edges")) or not isinstance(b, dict):
        raise Invalid("el manifiesto no dice qué lleva el grafo")
    files = man.get("files")
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise Invalid("la lista de ficheros del manifiesto no es válida")
    out: dict[str, tuple[int, str]] = {}
    for f in files:
        p = f.get("path") if isinstance(f, dict) else None
        if not isinstance(p, str) or not (p in FILES or DOC_FILE.match(p)):
            raise Invalid(f"ruta no admitida en el manifiesto: {str(p)[:200]!r}")
        if p in out:
            raise Invalid(f"fichero repetido en el manifiesto: {p}")
        size, sha = f.get("size"), f.get("sha256")
        if not _int(size) or size < 0 or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise Invalid(f"el manifiesto no da un tamaño y una huella válidos para {p}")
        out[p] = (size, sha)
    if missing := sorted(REQUIRED - set(out)):
        raise Invalid(f"faltan ficheros obligatorios: {', '.join(missing)}")
    return out


def _unpack(job: jobs.JobCtx, src: Path, stage: Path) -> dict:
    """Writes the package's files in `stage`, each one checked against the manifest. Returns the manifest."""
    stage.mkdir()
    try:
        t = tarfile.open(src, "r:gz")
    except (tarfile.TarError, OSError, EOFError):
        raise Invalid("no es un paquete de MimirSynth (no se puede leer como .tar.gz)") from None
    try:
        with t:
            man = _read_manifest(t)
            files, seen = _files(man), set()
            need = sum(s for s, _ in files.values())
            if shutil.disk_usage(stage).free < need * 1.1:
                raise RuntimeError(f"no hay espacio suficiente para desempaquetarlo: necesita {need >> 20} MB")
            while (m := t.next()) is not None:
                job.check()
                if m.name not in files:
                    raise Invalid(f"lleva un fichero que no está en su manifiesto: {m.name[:200]!r}")
                if m.name in seen:
                    raise Invalid(f"fichero repetido: {m.name}")
                if not m.isfile():
                    raise Invalid(f"{m.name} no es un fichero normal (es un enlace o un directorio)")
                size, sha = files[m.name]
                if m.size != size:
                    raise Invalid(f"el tamaño de {m.name} no coincide con el del manifiesto")
                dest = stage / m.name  # the name is one of a fixed list (see `_files`): it cannot leave the stage
                dest.parent.mkdir(parents=True, exist_ok=True)
                h, got = hashlib.sha256(), 0
                with t.extractfile(m) as fi, open(dest, "wb") as fo:
                    for blk in iter(lambda: fi.read(1 << 20), b""):
                        got += len(blk)
                        h.update(blk)
                        fo.write(blk)
                if got != size or h.hexdigest() != sha:
                    raise Invalid(f"el contenido de {m.name} no coincide con su huella del manifiesto")
                seen.add(m.name)
                job.progress(len(seen), len(files) + 2, f"desempaquetando: {len(seen)}/{len(files)}")
    except (tarfile.TarError, EOFError, OSError) as e:
        raise Invalid(f"el .tar.gz está dañado o incompleto ({e.__class__.__name__})") from None
    if missing := sorted(set(files) - seen):
        raise Invalid(f"faltan ficheros del manifiesto: {', '.join(missing[:5])}")
    return man


def _json(path: Path, kinds):
    if path.stat().st_size > MAX_JSON:
        raise Invalid(f"{path.name} es demasiado grande")
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise Invalid(f"{path.name} no es JSON válido") from None
    if not isinstance(v, kinds):
        raise Invalid(f"{path.name} no tiene la forma esperada")
    return v


def _lines(path: Path):
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                v = json.loads(line)
            except ValueError:
                raise Invalid(f"{path.name}, línea {i}: no es JSON válido") from None
            if not isinstance(v, dict):
                raise Invalid(f"{path.name}, línea {i}: no tiene la forma esperada")
            yield v


def _value_ok(v) -> bool:
    if v is None or isinstance(v, (str, int, float, bool)):
        return True
    return isinstance(v, list) and all(x is None or isinstance(x, (str, int, float, bool)) for x in v)


def _vectors_ok(vec, dim: int) -> bool:
    return isinstance(vec, dict) and all(k in VECTORS and isinstance(v, list) and len(v) == dim and all(isinstance(x, (int, float)) for x in v)
                                         for k, v in vec.items())


def _comparable(key: str) -> bool:
    """Property names compared between the dump and the JSON copy: not the vectors, which the JSON only carries on request."""
    return not (key.endswith("_embedding") or "_embedding_" in key)


def _digest(uuids) -> str:
    return hashlib.sha256("\n".join(sorted(uuids)).encode()).hexdigest()


def _shape(g) -> dict:
    """What a restored graph holds, in the same terms as the shape `_check` takes from the JSON copy."""
    labels = Counter({r[0]: r[1] for r in g.query("MATCH (n) UNWIND labels(n) AS l RETURN l, count(*)").result_set})
    types = Counter({r[0]: r[1] for r in g.query("MATCH ()-[r]->() RETURN type(r), count(*)").result_set})
    props = {r[0] for r in g.query("MATCH (n) UNWIND keys(n) AS k RETURN DISTINCT k").result_set}
    props |= {r[0] for r in g.query("MATCH ()-[r]->() UNWIND keys(r) AS k RETURN DISTINCT k").result_set}
    uuids = [f"n:{r[0] or ''}" for r in g.query("MATCH (n) RETURN n.uuid").result_set]
    uuids += [f"e:{r[0] or ''}" for r in g.query("MATCH ()-[r]->() RETURN r.uuid").result_set]
    return {"labels": labels, "types": types, "props": {k for k in props if _comparable(k)}, "uuids": _digest(uuids)}


def _differences(want: dict, got: dict) -> list[str]:
    out = []
    for what in ("labels", "types"):
        for k in sorted(set(want[what]) | set(got[what])):
            if want[what][k] != got[what][k]:
                out.append(f"{k}: {got[what][k]} en el volcado, {want[what][k]} en la copia JSON")
    if extra := sorted(got["props"] - want["props"]):
        out.append("propiedades que solo están en el volcado: " + ", ".join(extra[:10]))
    if missing := sorted(want["props"] - got["props"]):
        out.append("propiedades que faltan en el volcado: " + ", ".join(missing[:10]))
    if not out and want["uuids"] != got["uuids"]:
        out.append("los uuid de los nodos o las aristas no coinciden")
    return out


def _check(stage: Path, man: dict, mode: str, dim: int | None) -> dict | None:
    """Reads the whole package once before anything is written. `dim`: the dimension of reused vectors, or None if they are not.
    Returns the graph's shape (labels and relation types with their counts, property names, uuids), to check a restored dump."""
    _json(stage / "brain.json", dict)
    _json(stage / "ontology.json", (dict, type(None)))
    vocab = _json(stage / "vocabulary.json", dict)
    refs = _json(stage / "ref_queries.json", dict)
    for v in (vocab.get("aliases"), vocab.get("ops"), vocab.get("retype"), refs.get("queries")):
        if v is not None and not (isinstance(v, list) and all(isinstance(x, dict) for x in v)):
            raise Invalid("el vocabulario o las consultas de referencia no tienen la forma esperada")
    if mode == "structure":
        return None
    nodes, edges = set(), set()
    shape: dict = {"labels": Counter(), "types": Counter(), "props": set(), "uuids": []}
    for n in _lines(stage / "graph" / "nodes.jsonl"):
        labels, props = n.get("labels"), n.get("props")
        if not _int(n.get("id")) or n["id"] in nodes:
            raise Invalid("un nodo del grafo no tiene un id válido o está repetido")
        if not isinstance(labels, list) or len(labels) > 16 or not all(isinstance(x, str) and NAME.match(x) for x in labels):
            raise Invalid(f"etiqueta de nodo no admitida: {str(labels)[:200]}")
        if not isinstance(props, dict) or not all(isinstance(k, str) and _value_ok(v) for k, v in props.items()):
            raise Invalid("las propiedades de un nodo no tienen la forma esperada")
        if dim and "vectors" in n and not _vectors_ok(n["vectors"], dim):
            raise Invalid("los vectores de un nodo no tienen la dimensión del modelo")
        nodes.add(n["id"])
        shape["labels"].update(labels)
        shape["props"] |= {k for k in props if _comparable(k)}
        shape["uuids"].append(f"n:{props.get('uuid') or ''}")
    for e in _lines(stage / "graph" / "edges.jsonl"):
        if not _int(e.get("id")) or e["id"] in edges:
            raise Invalid("una arista del grafo no tiene un id válido o está repetida")
        if not isinstance(e.get("type"), str) or not NAME.match(e["type"]):
            raise Invalid(f"tipo de relación no admitido: {str(e.get('type'))[:200]}")
        if e.get("source") not in nodes or e.get("target") not in nodes:
            raise Invalid("una arista apunta a un nodo que no está en el paquete")
        props = e.get("props")
        if not isinstance(props, dict) or not all(isinstance(k, str) and _value_ok(v) for k, v in props.items()):
            raise Invalid("las propiedades de una arista no tienen la forma esperada")
        if dim and "vectors" in e and not _vectors_ok(e["vectors"], dim):
            raise Invalid("los vectores de una arista no tienen la dimensión del modelo")
        edges.add(e["id"])
        shape["types"][e["type"]] += 1
        shape["props"] |= {k for k in props if _comparable(k)}
        shape["uuids"].append(f"e:{props.get('uuid') or ''}")
    if len(nodes) != man["graph"]["nodes"] or len(edges) != man["graph"]["edges"]:
        raise Invalid(f"el grafo no tiene los elementos que dice el manifiesto ({len(nodes)} nodos y {len(edges)} aristas, "
                      f"frente a {man['graph']['nodes']} y {man['graph']['edges']})")
    for _ in _lines(stage / "proposals.jsonl"):
        pass
    sources = _json(stage / "documents" / "sources.json", list)
    sids = [s.get("id") for s in sources if isinstance(s, dict)]
    if len(sids) != len(sources) or not all(_int(i) for i in sids) or len(set(sids)) != len(sids):
        raise Invalid("las fuentes de documentos no tienen la forma esperada")
    docs = set()
    for d in _lines(stage / "documents" / "documents.jsonl"):
        if not _int(d.get("id")) or d["id"] in docs or d.get("source_id") not in sids:
            raise Invalid("un documento no tiene un id válido o su fuente no está en el paquete")
        for k in ("text", "original"):
            p = d.get(k)
            if p is None:
                continue
            m = DOC_FILE.match(p) if isinstance(p, str) else None
            if not m or int(m.group(1)) != d["id"] or (k == "text") != (m.group(2) == "text.txt") or not (stage / p).is_file():
                raise Invalid(f"el documento {d['id']} apunta a un fichero que no es suyo o no está en el paquete")
        docs.add(d["id"])
    shape["uuids"] = _digest(shape["uuids"])
    for c in _lines(stage / "vectors" / "doc_chunks.jsonl"):
        if c.get("document_id") not in docs or not _int(c.get("chunk_idx")) or not isinstance(c.get("text"), str):
            raise Invalid("un trozo de documento no tiene la forma esperada o su documento no está en el paquete")
        if dim and not (isinstance(c.get("embedding"), list) and len(c["embedding"]) == dim):
            raise Invalid("los vectores de los documentos no tienen la dimensión del modelo")
    for c in _lines(stage / "vectors" / "episode_chunks.jsonl"):
        if not isinstance(c.get("episode_uuid"), str) or not _int(c.get("chunk_idx")) or not isinstance(c.get("text"), str):
            raise Invalid("un trozo de episodio no tiene la forma esperada")
        if dim and not (isinstance(c.get("embedding"), list) and len(c["embedding"]) == dim):
            raise Invalid("los vectores de los episodios no tienen la dimensión del modelo")
    return shape


def _same_model(man: dict, emb: dict) -> bool:
    theirs = man.get("embedding") or {}
    return bool(theirs.get("model")) and theirs.get("model") == emb["model"] and theirs.get("dim") == emb["dim"]


# --- what the import writes, and how it is undone ------------------------------------------------------

def _target_error(db: Session, slug: str) -> str | None:
    if not SLUG.match(slug or "") or not GRAPH.match(slug):
        return "slug inválido (minúsculas, números y guiones, 2-41 caracteres)"
    if db.scalar(select(Brain.id).where(Brain.slug == slug)):
        return "ya existe un brain con ese slug"
    if db.scalar(select(Brain.id).where(Brain.graph_name == slug)) or slug in client().list_graphs():
        return f"ya existe un grafo llamado «{slug}»"
    return None


def _mark(work: Path, made: dict) -> None:
    """What the import has created so far, so that a restart in the middle can undo it."""
    (work / "created.json").write_text(json.dumps(made), encoding="utf-8")


def _drop_graph(name: str | None) -> None:
    if name and name in client().list_graphs():
        client().select_graph(name).delete()


def undo(made: dict) -> None:
    """Removes what an import created: its graph (and the original-name copy of a dump), its rows and its files."""
    for g in (made.get("graph"), made.get("restored")):
        try:
            _drop_graph(g)
        except Exception:  # noqa: BLE001
            log.exception("no se pudo borrar el grafo %s de una importación deshecha", g)
    bid = made.get("brain_id")
    if not bid:
        return
    with _factory()() as db:
        b = db.get(Brain, bid)
        if not b or b.slug != made.get("slug"):
            return
        if index.enabled():
            db.execute(text("DELETE FROM episode_chunks WHERE brain_id = :b"), {"b": bid})
            db.execute(text("DELETE FROM doc_chunks WHERE brain_id = :b"), {"b": bid})
        for t in reversed(Base.metadata.sorted_tables):
            if t.name not in KEEP and t.name != "brains" and "brain_id" in t.c:
                db.execute(t.delete().where(t.c.brain_id == bid))
        db.execute(Brain.__table__.delete().where(Brain.id == bid))
        db.commit()
    docstore.remove_brain(bid)


def _busy(db: Session, uid: str) -> bool:
    return any((j.params or {}).get("upload_id") == uid
               for j in db.scalars(select(Job).where(Job.kind == KIND, Job.status.in_(("queued", "running")))))


def purge() -> int:
    """Uploads nobody imported within a day, and what an import cut by a restart left behind (its brain and graph)."""
    base = docstore.root() / "_imports"
    if not base.exists():
        return 0
    with _factory()() as db:
        busy = {(j.params or {}).get("upload_id") for j in db.scalars(select(Job).where(Job.kind == KIND, Job.status.in_(("queued", "running"))))}
    n = 0
    for d in base.iterdir():
        if d.name in busy or not d.is_dir():
            continue
        try:
            marker = d / "created.json"
            if marker.exists():
                undo(json.loads(marker.read_text(encoding="utf-8")))
            elif time.time() - d.stat().st_mtime < docstore.UPLOAD_TTL:
                continue
        except Exception:  # noqa: BLE001
            log.exception("no se pudo deshacer la importación a medias de %s", d.name)
            continue
        shutil.rmtree(d, ignore_errors=True)
        n += 1
    return n


def _dt(v):
    if not isinstance(v, str):
        return v
    d = datetime.fromisoformat(v)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _cols(model, d: dict, skip=frozenset()) -> dict:
    """The package's fields that are columns of `model`, without ids or users of the other instance."""
    out = {}
    for c in model.__table__.columns:
        if c.key in ("id", "brain_id") or c.key in skip or c.key not in d:
            continue
        out[c.key] = _dt(d[c.key]) if isinstance(c.type, DateTime) else d[c.key]
    return out


def _curation(db: Session, stage: Path, bid: int, full: bool) -> dict:
    onto = _json(stage / "ontology.json", (dict, type(None)))
    if onto:
        db.add(BrainOntology(brain_id=bid, data=onto))
    vocab = _json(stage / "vocabulary.json", dict)
    for a in vocab.get("aliases") or []:
        db.add(VocabAlias(brain_id=bid, **_cols(VocabAlias, a, {"created_by"})))
    out = {"ontology": bool(onto), "aliases": len(vocab.get("aliases") or [])}
    if full:
        for o in vocab.get("ops") or []:
            db.add(VocabOp(brain_id=bid, **_cols(VocabOp, o, {"user_id"})))
        for r in vocab.get("retype") or []:
            db.add(RetypeSuggestion(brain_id=bid, **_cols(RetypeSuggestion, r)))
        queries = _json(stage / "ref_queries.json", dict).get("queries") or []
        for q in queries:
            db.add(RefQuery(brain_id=bid, **_cols(RefQuery, q, {"created_by"})))
        out.update(vocab_ops=len(vocab.get("ops") or []), retype=len(vocab.get("retype") or []), ref_queries=len(queries))
    db.commit()
    return out


def _graph(job: jobs.JobCtx, stage: Path, man: dict, slug: str, reuse: bool, made: dict, work: Path, use_dump: bool, shape: dict) -> dict:
    """The JSON copy, which was validated; the dump only on request, when it can be restored here and holds what the JSON copy
    holds. Returns how the graph went in and why."""
    g, c = man["graph"], client()
    orig = g.get("name") if isinstance(g.get("name"), str) else ""
    dump = stage / "graph" / "graph.dump"
    here = _falkor_version().get("graph_module")
    reason, mismatch = None, None
    if not use_dump:
        reason = "not_requested"
    elif not dump.exists():
        reason = g.get("dump_omitted") or "no_dump"
    elif not here or here != (man.get("falkordb") or {}).get("graph_module"):
        reason = "falkordb_version"
    elif not GRAPH.match(orig) or (orig != slug and orig in c.list_graphs()):
        reason = "name_taken"  # the payload carries its name: it is restored under it and then copied
    else:
        made["restored"] = orig if orig != slug else None
        made["graph"] = slug
        _mark(work, made)
        try:
            c.connection.restore(orig, 0, dump.read_bytes())
            if orig != slug:
                c.select_graph(orig).copy(slug)
                _drop_graph(orig)
                made["restored"] = None
                _mark(work, made)
            dst = c.select_graph(slug)
            dst.query("MATCH (n) WHERE n.group_id IS NOT NULL SET n.group_id = $g", {"g": slug})  # the payload's own is not trusted
            dst.query("MATCH ()-[r]->() WHERE r.group_id IS NOT NULL SET r.group_id = $g", {"g": slug})
            mismatch = _differences(shape, _shape(dst))
            if not mismatch:
                return {"method": "dump", "fallback_reason": None}
            job.note("el volcado no coincide con la copia JSON (" + "; ".join(mismatch[:5]) + "): se descarta y se usa la copia JSON")
            _drop_graph(slug)
            reason = "dump_mismatch"
        except Exception as e:  # noqa: BLE001  (another build of the module, a corrupt payload…: the JSON copy still works)
            job.note(f"no se pudo restaurar el volcado ({e.__class__.__name__}); se usa la copia JSON")
            _drop_graph(slug)
            _drop_graph(made.get("restored"))
            made["restored"] = None
            reason = "restore_failed"
    made["graph"] = slug
    _mark(work, made)
    _graph_json(job, stage, slug, reuse)
    return {"method": "json", "fallback_reason": reason, **({"dump_mismatch": mismatch[:20]} if mismatch else {})}


def _graph_json(job: jobs.JobCtx, stage: Path, slug: str, reuse: bool) -> None:
    g, ids = client().select_graph(slug), {}

    def node_batch(key, batch):
        labels, vecs = key
        sets = "".join(f", n.{v} = vecf32(r.v.{v})" for v in vecs)
        q = f"UNWIND $rows AS r CREATE (n{''.join(':' + x for x in labels)}) SET n += r.p{sets} RETURN r.i, id(n)"
        for i, nid in g.query(q, {"rows": batch}).result_set:
            ids[i] = nid

    def edge_batch(key, batch):
        typ, vecs = key
        sets = "".join(f", e.{v} = vecf32(r.v.{v})" for v in vecs)
        q = (f"UNWIND $rows AS r MATCH (a) WHERE id(a) = r.s MATCH (b) WHERE id(b) = r.t "
             f"CREATE (a)-[e:{typ}]->(b) SET e += r.p{sets} RETURN count(e)")
        if g.query(q, {"rows": batch}).result_set[0][0] != len(batch):
            raise RuntimeError("no se pudieron crear todas las aristas del grafo")

    def load(path, make_key, make_row, write, what):
        key, batch, n = None, [], 0
        for item in _lines(path):
            vec = (item.get("vectors") or {}) if reuse else {}
            k = make_key(item, tuple(sorted(vec)))
            if batch and (k != key or len(batch) >= BATCH):
                write(key, batch)
                n += len(batch)
                batch = []
                job.check()
                job.progress(3, None, f"grafo: {what} {n}")
            key = k
            props = dict(item["props"])
            if "group_id" in props:  # Graphiti's partition is the graph's name
                props["group_id"] = slug
            batch.append({**make_row(item), "p": props, "v": vec})
        if batch:
            write(key, batch)

    load(stage / "graph" / "nodes.jsonl", lambda n, v: (tuple(n["labels"]), v), lambda n: {"i": n["id"]}, node_batch, "nodos")
    load(stage / "graph" / "edges.jsonl", lambda e, v: (e["type"], v), lambda e: {"s": ids[e["source"]], "t": ids[e["target"]]}, edge_batch, "aristas")
    if ids:
        _indices(slug)


def _indices(name: str) -> None:
    """Graphiti's range and full-text indices, which the dump carries but the JSON copy does not."""
    from graphiti_core.driver.falkordb_driver import FalkorDriver

    async def go():
        d = FalkorDriver(host=settings.falkor_host, port=settings.falkor_port, database=name)
        try:
            await d.build_indices_and_constraints()
        finally:
            await d.close()
    asyncio.run(go())


def _embed_graph(job: jobs.JobCtx, name: str, everything: bool) -> int:
    """Graphiti's vectors with the embedding model in use: all of them, or only the ones the package did not bring."""
    from .embed import gate, get_embedder, resolve_embedding
    from .reembed import ITEMS, _embed, _match
    g, emb, dim, n = client().select_graph(name), get_embedder(), resolve_embedding()["dim"], 0
    with gate.writing():
        for kind, label, txt, vec in ITEMS:
            cond = f"x.uuid IS NOT NULL AND x.{txt} IS NOT NULL AND x.{txt} <> ''" + ("" if everything else f" AND x.{vec} IS NULL")
            todo = [r[0] for r in g.query(f"MATCH {_match(kind, label)} WHERE {cond} RETURN x.uuid").result_set]
            for i in range(0, len(todo), EMBED_BATCH):
                job.check()
                found = rows(g.query(f"UNWIND $u AS u MATCH {_match(kind, label, True)} RETURN x.uuid AS u, x.{txt} AS t", {"u": todo[i:i + EMBED_BATCH]}))
                vecs = _embed(emb, [str(b["t"]).replace("\n", " ") for b in found], dim, job.note)
                g.query(f"UNWIND $rows AS r WITH r, r.u AS u MATCH {_match(kind, label, True)} SET x.{vec} = vecf32(r.v)",
                        {"rows": [{"u": b["u"], "v": v} for b, v in zip(found, vecs)]})
                n += len(found)
                job.progress(4, None, f"vectores del grafo: {n}")
    return n


def _proposals(db: Session, stage: Path, bid: int, user_id: int) -> int:
    n = 0
    for d in _lines(stage / "proposals.jsonl"):
        row = _cols(Proposal, d, {"author_id", "reviewer_id", "token_id"})
        if row.get("status") in ("approved", "ingesting"):  # it never got into the exported graph: a curator decides again
            row["status"] = "pending"
        report = row.get("ingest_report") if isinstance(row.get("ingest_report"), dict) else {}
        row["ingest_report"] = {**report, "imported": {"author": d.get("author", ""), "reviewer": d.get("reviewer", "")}}
        db.add(Proposal(brain_id=bid, author_id=user_id, **row))
        n += 1
    db.commit()
    return n


def _documents(job: jobs.JobCtx, db: Session, stage: Path, bid: int, user_id: int) -> tuple[dict, dict[int, int], dict[int, str]]:
    """Sources, documents and their files. Returns the counts, the old id → new id map and the text of each document that has one."""
    smap, disabled = {}, 0
    for s in _json(stage / "documents" / "sources.json", list):
        row = _cols(DocSource, s, {"created_by", "status", "last_error", "last_sync_at", "enabled", "config"})
        upload = row.get("kind") == "upload"
        src = DocSource(brain_id=bid, **row, config=s.get("config") if isinstance(s.get("config"), dict) else {}, enabled=upload, status="idle",
                        last_error="" if upload else "importada desactivada: revisa su configuración y sus credenciales antes de sincronizarla",
                        created_by=user_id)
        disabled += not upload
        db.add(src)
        db.flush()
        smap[s["id"]] = src
    dmap, texts, kept = {}, {}, {"originals": 0, "texts": 0}
    docs = list(_lines(stage / "documents" / "documents.jsonl"))
    for i, d in enumerate(docs):
        job.check()
        src = smap[d["source_id"]]
        doc = Document(brain_id=bid, source_id=src.id, created_by=user_id,
                       **_cols(Document, d, {"created_by", "storage_ref", "text_ref", "source_id", "chunks"}), chunks=0)
        db.add(doc)
        db.flush()
        dmap[d["id"]] = doc.id
        dest = docstore.doc_dir(bid, src.id, doc.id)
        dest.mkdir(parents=True, exist_ok=True)
        if d.get("original"):
            p = dest / Path(d["original"]).name
            shutil.move(str(stage / d["original"]), p)
            doc.storage_ref = docstore.rel(p)
            kept["originals"] += 1
        if d.get("text"):
            p = dest / "text.norm.txt"
            shutil.move(str(stage / d["text"]), p)
            doc.text_ref = docstore.rel(p)
            texts[doc.id] = p.read_text(encoding="utf-8", errors="replace")
            kept["texts"] += 1
        elif doc.status != "duplicate":
            doc.status = "error"
            doc.error = "importado sin su texto: vuelve a indexarlo" if d.get("original") else "importado sin su texto ni su original"
        job.progress(5, None, f"documentos: {i + 1}/{len(docs)}")
    for doc in db.scalars(select(Document).where(Document.brain_id == bid, Document.status == "duplicate")):
        meta = dict(doc.meta or {})
        if meta.get("duplicate_of") in dmap:
            meta["duplicate_of"] = dmap[meta["duplicate_of"]]
        else:  # its original stayed out: it has to be indexed on its own
            meta.pop("duplicate_of", None)
            doc.status, doc.error = "error", "importado como duplicado de un documento que no está: vuelve a indexarlo"
        doc.meta = meta
    db.commit()
    return {"sources": len(smap), "sources_disabled": disabled, "documents": len(docs), **kept}, dmap, texts


def _doc_chunks(job: jobs.JobCtx, db: Session, stage: Path, bid: int, dmap: dict[int, int], texts: dict[int, str], reuse: bool) -> dict:
    """The documents' search index: their chunks with the package's vectors, or chunked and computed again."""
    from .docextract import chunk
    from .embed import gate, get_embedder, resolve_embedding
    from .reembed import _embed
    out = {"copied": 0, "computed": 0}
    docs = {d.id: d for d in db.scalars(select(Document).where(Document.brain_id == bid))}
    done: set[int] = set()
    if reuse:
        by_doc: dict[int, list[dict]] = {}
        for c in _lines(stage / "vectors" / "doc_chunks.jsonl"):
            new = dmap[c["document_id"]]
            if new in texts and docs[new].status != "duplicate":
                by_doc.setdefault(new, []).append({"idx": c["chunk_idx"], "heading_path": c.get("heading_path") or "", "char_start": c.get("char_start") or 0,
                                                    "char_end": c.get("char_end") or 0, "page": c.get("page"), "text": c["text"], "vec": c["embedding"]})
        for did, chunks in by_doc.items():
            docindex.replace_chunks(bid, did, chunks, [c["vec"] for c in chunks], docs[did].sha256)
            docs[did].chunks, docs[did].status = len(chunks), "active"
            done.add(did)
            out["copied"] += len(chunks)
    todo = [d for d in docs.values() if d.id in texts and d.id not in done and d.status != "duplicate"]
    if todo:
        emb, dim = get_embedder(), resolve_embedding()["dim"]
        with gate.writing():
            for i, d in enumerate(todo):
                job.check()
                chunks = chunk(texts[d.id])
                vecs = []
                for j in range(0, len(chunks), EMBED_BATCH):
                    vecs += _embed(emb, [f"{d.title}\n{c['heading_path']}\n{c['text']}" for c in chunks[j:j + EMBED_BATCH]], dim, job.note)
                docindex.replace_chunks(bid, d.id, chunks, vecs, d.sha256)
                d.chunks, d.status, d.error = len(chunks), "active" if chunks else "error", "" if chunks else "el documento no tiene contenido"
                out["computed"] += len(chunks)
                job.progress(6, None, f"índice de documentos: {i + 1}/{len(todo)}")
    db.commit()
    return out


def _episode_chunks(stage: Path, bid: int, slug: str, reuse: bool) -> dict:
    """The episodes' search index: the package's chunks when they can be reused, and then the usual sync, which only computes what is
    missing or changed."""
    out = {"copied": 0}
    if reuse:
        from .store import engine
        batch = []
        with engine().begin() as c:
            for r in _lines(stage / "vectors" / "episode_chunks.jsonl"):
                batch.append({"b": bid, "u": r["episode_uuid"], "i": r["chunk_idx"], "n": r.get("name") or "", "t": r["text"], "v": r.get("valid_at"),
                              "h": r.get("content_hash") or "", "e": str(r["embedding"])})
                if len(batch) >= BATCH:
                    c.execute(text("INSERT INTO episode_chunks (brain_id, episode_uuid, chunk_idx, name, text, valid_at, content_hash, embedding) "
                                   "VALUES (:b,:u,:i,:n,:t,:v,:h,CAST(:e AS vector))"), batch)
                    out["copied"] += len(batch)
                    batch = []
            if batch:
                c.execute(text("INSERT INTO episode_chunks (brain_id, episode_uuid, chunk_idx, name, text, valid_at, content_hash, embedding) "
                               "VALUES (:b,:u,:i,:n,:t,:v,:h,CAST(:e AS vector))"), batch)
                out["copied"] += len(batch)
    s = index.sync_brain(bid, slug)
    out["computed"] = s.get("chunks_written", 0)
    return out


def _import(job: jobs.JobCtx, work: Path, p: dict, password: str | None) -> dict:
    from .embed import resolve_embedding
    pkg = work / "package"
    if p.get("encrypted"):
        job.progress(0, None, "descifrando")
        tar = work / "package.tar.gz"
        try:
            packcrypt.decrypt_file(pkg, tar, password)
        except packcrypt.BadPassword:
            tar.unlink(missing_ok=True)
            raise WrongPassword("contraseña incorrecta, o el paquete se ha modificado o está incompleto") from None
        except ValueError as e:
            raise Invalid(str(e)) from None
        pkg.unlink()
    else:
        tar = pkg
    stage = work / "stage"
    shutil.rmtree(stage, ignore_errors=True)
    man = _unpack(job, tar, stage)
    tar.unlink()
    emb, full = resolve_embedding(), p["mode"] == "full"
    reuse = _same_model(man, emb)
    shape = _check(stage, man, p["mode"], emb["dim"] if reuse else None)
    slug, user_id = p["slug"], p["user_id"]
    with _factory()() as db:
        if err := _target_error(db, slug):
            raise RuntimeError(err)
    total = 8
    job.progress(1, total, "paquete comprobado")
    made: dict = {"slug": slug, "brain_id": None, "graph": None, "restored": None}
    try:
        info = _json(stage / "brain.json", dict)
        with _factory()() as db:
            mode = info.get("secret_mode") if info.get("secret_mode") in secretguard.MODES else "mask"
            b = Brain(slug=slug, name=p["name"], description=p["description"] if p.get("description") is not None else str(info.get("description") or ""),
                      graph_name=slug, created_by=user_id, secret_mode=mode, secret_allow=str(info.get("secret_allow") or ""))
            db.add(b)
            db.flush()
            made["brain_id"] = bid = b.id
            _mark(work, made)
            db.add(Membership(user_id=user_id, brain_id=bid, role="owner"))
            db.commit()
            job.progress(2, total, "curación")
            counts = {"curation": _curation(db, stage, bid, full)}
            result = {"brain": slug, "mode": p["mode"], "counts": counts, "source": _summary(man)}
            if not full:
                audit(db, db.get(User, user_id), "brain.import.done", db.get(Brain, bid), mode=p["mode"], **counts["curation"])
                return result
            job.progress(3, total, "grafo")
            graph = _graph(job, stage, man, slug, reuse, made, work, bool(p.get("dump")), shape)
            job.progress(4, total, "vectores del grafo")
            computed = _embed_graph(job, slug, everything=graph["method"] == "dump" and not reuse) if man["graph"]["nodes"] else 0
            graph.update(zip(("nodes", "edges"), _count(client().select_graph(slug)) if man["graph"]["nodes"] else (0, 0)))
            if (graph["nodes"], graph["edges"]) != (man["graph"]["nodes"], man["graph"]["edges"]):
                raise RuntimeError(f"el grafo importado no tiene los elementos del paquete ({graph['nodes']} nodos y {graph['edges']} aristas)")
            counts["proposals"] = _proposals(db, stage, bid, user_id)
            job.progress(5, total, "documentos")
            docs, dmap, texts = _documents(job, db, stage, bid, user_id)
            counts["documents"] = docs
            vectors = {"reused": reuse, "graph_computed": computed}
            if index.enabled():
                job.progress(6, total, "índice de documentos")
                vectors["doc_chunks"] = _doc_chunks(job, db, stage, bid, dmap, texts, reuse)
                job.progress(7, total, "índice de episodios")
                vectors["episode_chunks"] = _episode_chunks(stage, bid, slug, reuse) if man["graph"]["nodes"] else {"copied": 0, "computed": 0}
            result.update(graph=graph, vectors=vectors)
            refs = _json(stage / "ref_queries.json", dict)
            result["ref_before"] = (refs.get("last_run") or {}).get("summary") if isinstance(refs.get("last_run"), dict) else None
            b = db.get(Brain, bid)
            audit(db, db.get(User, user_id), "brain.import.done", b, mode=p["mode"], graph=graph["method"], nodes=graph["nodes"],
                  edges=graph["edges"], proposals=counts["proposals"], documents=docs["documents"], vectors_reused=reuse)
        if counts["curation"].get("ref_queries"):
            from .refqueries import submit_run
            result["ref_run"] = submit_run(bid, {}, "brain.imported", user_id)
        return result
    except BaseException:
        undo(made)
        raise


@jobs.register(KIND, "Importación de un brain", limit=1,
               interrupted="interrumpida por un reinicio del servicio: lo que había creado se elimina al arrancar; vuelve a subir el paquete")
def _run(job: jobs.JobCtx, params: dict) -> dict:
    password = _PASSWORDS.pop(params.get("key") or "", None)
    work = _base() / params["upload_id"]
    keep = False
    try:
        if params.get("encrypted") and not password:
            raise RuntimeError("la contraseña del paquete ya no está en memoria (el servicio se ha reiniciado); vuelve a importarlo")
        if not (work / "package").is_file():
            raise RuntimeError("el paquete ya no está: vuelve a subirlo")
        return _import(job, work, params, password)
    except WrongPassword:
        keep = True  # the same upload can be imported again with the right password
        raise
    except Invalid as e:
        raise RuntimeError(f"paquete rechazado: {e}") from None
    finally:
        if keep:
            shutil.rmtree(work / "stage", ignore_errors=True)
        else:
            shutil.rmtree(work, ignore_errors=True)


class ImportIn(BaseModel):
    upload_id: str = Field(max_length=64)
    slug: str = Field(max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(None, max_length=10000)
    mode: str = "full"
    password: str | None = Field(None, max_length=1024)
    dump: bool = Field(False, description="fast restore with the package's dump, only for packages one exported oneself; checked against the JSON copy")


@router.post("", status_code=202)
def start(body: ImportIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Starts the import of an uploaded package as a job. The password, if any, is only kept in memory until the job starts."""
    d, m = _meta(body.upload_id, user)
    if not m.get("complete") or not (d / "package").is_file():
        raise HTTPException(409, "la subida no está completa")
    if body.mode not in MODES:
        raise HTTPException(400, "modo de importación inválido (full o structure)")
    if not body.name.strip():
        raise HTTPException(400, "el nombre no puede estar vacío")
    if err := _target_error(db, body.slug):
        raise HTTPException(409 if err.startswith("ya existe") else 400, err)
    if _busy(db, body.upload_id) or db.scalar(select(Job.id).where(Job.kind == KIND, Job.status.in_(("queued", "running")))):
        raise HTTPException(409, "ya hay una importación en marcha")
    encrypted = packcrypt.is_encrypted(d / "package")
    if encrypted and not body.password:
        raise HTTPException(400, "el paquete está cifrado: hace falta su contraseña")
    key = ""
    if encrypted:
        key = secrets.token_urlsafe(16)
        _PASSWORDS[key] = body.password
    audit(db, user, "brain.import", None, slug=body.slug, mode=body.mode, dump=body.dump, encrypted=encrypted, size=m["size"], file=m["filename"])
    jid = jobs.submit(KIND, None, {"upload_id": body.upload_id, "slug": body.slug, "name": body.name.strip(), "description": body.description,
                                   "mode": body.mode, "encrypted": encrypted, "key": key, "user_id": user.id, "dump": body.dump},
                      f"Importación de {body.slug}", user.id)
    return {"id": jid}


@router.get("")
def list_imports(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    found = db.scalars(select(Job).where(Job.kind == KIND).order_by(Job.id.desc()).limit(20)).all()
    names = {u.id: (u.display_name or u.name) for u in db.scalars(select(User).where(User.id.in_({j.created_by for j in found if j.created_by})))}
    out = []
    for j in found:
        p, r = j.params or {}, j.result or {}
        out.append({"id": j.id, "state": j.status, "done": j.progress_done, "total": j.progress_total, "message": j.message, "error": j.error,
                    "user": names.get(j.created_by, ""), "created_at": j.created_at, "finished_at": j.finished_at, "slug": p.get("slug"),
                    "mode": p.get("mode"), "encrypted": bool(p.get("encrypted")), "dump": bool(p.get("dump")), "upload_id": p.get("upload_id"),
                    "retry_password": j.status == "failed" and (_base() / str(p.get("upload_id"))).joinpath("package").is_file(),
                    **{k: r.get(k) for k in ("brain", "source", "graph", "counts", "vectors", "ref_run", "ref_before")}})
    return {"items": out}
