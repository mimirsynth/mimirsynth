"""Almacén de ficheros de la memoria documental: un volumen donde viven los originales y el texto normalizado.
Las rutas las genera siempre el servidor a partir de ids; el nombre que manda el usuario solo se guarda como metadato."""
import hashlib
import os
import re
import shutil
import time
from pathlib import Path

from .config import settings

TEXT_EXT = {".md", ".markdown", ".txt", ".rst", ".log"}
HTML_EXT = {".html", ".htm"}
PDF_EXT = {".pdf"}
ALLOWED_EXT = TEXT_EXT | HTML_EXT | PDF_EXT
UPLOAD_TTL = 24 * 3600


def root() -> Path:
    p = Path(settings.doc_store)
    p.mkdir(parents=True, exist_ok=True)
    return p


def roots_base() -> Path:
    return Path(settings.doc_roots_base).resolve()


def roots() -> dict[str, Path]:
    """Raíces autorizadas (se gestionan en Administración → Carpetas). Nunca se escribe en ellas."""
    from sqlalchemy import select

    from .models import DocRoot
    from .store import _factory
    with _factory()() as db:
        return {r.name: Path(r.path) for r in db.scalars(select(DocRoot))}


def source_base(config: dict) -> Path:
    """Carpeta de una fuente de directorio: raíz autorizada + subcarpeta, sin poder salir de la raíz."""
    base = roots().get(config.get("root", ""))
    if base is None:
        raise ValueError(f"la raíz «{config.get('root', '')}» no está autorizada (Administración → Carpetas)")
    base = base.resolve()
    p = (base / (config.get("subpath") or "").strip("/")).resolve()
    if p != base and base not in p.parents:
        raise ValueError("la subcarpeta sale de la raíz autorizada")
    return p


def source_file(config: dict, relpath: str) -> Path:
    base = source_base(config)
    p = (base / relpath).resolve()
    if base not in p.parents:
        raise ValueError("ruta fuera de la carpeta de la fuente")
    return p


def original_path(storage_ref: str, source_kind: str, source_config: dict, external_id: str) -> Path:
    """Dónde está el original: en el almacén (subidas) o en la carpeta externa (fuentes de directorio, sin copiar)."""
    if source_kind == "directory":
        return source_file(source_config, external_id)
    return resolve(storage_ref)


def ext_of(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def clean_name(filename: str) -> str:
    """Solo para mostrar: sin rutas ni caracteres de control."""
    name = os.path.basename((filename or "").replace("\\", "/"))
    return re.sub(r"[\x00-\x1f]", "", name)[:255] or "documento"


def doc_dir(brain_id: int, source_id: int, doc_id: int) -> Path:
    return root() / str(int(brain_id)) / str(int(source_id)) / str(int(doc_id))


def resolve(ref: str) -> Path:
    """Convierte una referencia relativa al almacén en ruta, garantizando que no sale de él."""
    base = root().resolve()
    p = (base / ref).resolve()
    if base != p and base not in p.parents:
        raise ValueError("referencia fuera del almacén")
    return p


def rel(p: Path) -> str:
    return str(p.resolve().relative_to(root().resolve()))


def uploads_dir() -> Path:
    d = root() / "_uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def remove_document(brain_id: int, source_id: int, doc_id: int) -> None:
    shutil.rmtree(doc_dir(brain_id, source_id, doc_id), ignore_errors=True)


def remove_brain(brain_id: int) -> None:
    shutil.rmtree(root() / str(int(brain_id)), ignore_errors=True)


def purge_stale_uploads() -> int:
    """Borra subidas a medias con más de 24 h."""
    n = 0
    for d in uploads_dir().iterdir():
        try:
            if d.is_dir() and time.time() - d.stat().st_mtime > UPLOAD_TTL:
                shutil.rmtree(d, ignore_errors=True); n += 1
        except OSError:
            pass
    return n
