"""Raíces de fuentes de documentos: las carpetas del servidor que un administrador de brain puede usar como fuente.
Solo el administrador de la instancia las gestiona, y solo pueden estar bajo MIMIRSYNTH_DOC_ROOTS_BASE (el bind de solo lectura del contenedor)."""
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import docstore
from .deps import audit, require_admin
from .models import DocRoot, DocSource, User
from .store import get_db

router = APIRouter(prefix="/api/doc-roots")
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


class RootIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    path: str = Field(min_length=1, max_length=500)
    description: str = Field("", max_length=200)


def _info(db: Session, r: DocRoot) -> dict:
    p = Path(r.path)
    n = db.scalar(select(func.count()).select_from(DocSource).where(DocSource.kind == "directory", DocSource.config["root"].as_string() == r.name))
    return {"id": r.id, "name": r.name, "path": r.path, "description": r.description, "available": p.is_dir(), "sources": n or 0}


@router.get("")
def list_roots(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(DocRoot).order_by(DocRoot.name)).all()
    base = docstore.roots_base()
    used = {Path(r.path).resolve() for r in rows}
    try:
        free = sorted(str(p) for p in base.iterdir() if p.is_dir() and not p.name.startswith(".") and p.resolve() not in used)
    except OSError:
        free = []
    return {"base": str(base), "base_available": base.is_dir(), "roots": [_info(db, r) for r in rows], "suggestions": free}


@router.post("", status_code=201)
def add_root(body: RootIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    name = body.name.strip().lower()
    if not NAME.match(name):
        raise HTTPException(400, "el nombre solo admite minúsculas, dígitos, «-» y «_» (hasta 40)")
    base = docstore.roots_base()
    p = Path(os.path.realpath(body.path.strip()))
    if p == base or base not in p.parents:
        raise HTTPException(400, f"la ruta debe estar dentro de {base} (es la carpeta montada en el contenedor)")
    if not p.is_dir():
        raise HTTPException(400, f"la carpeta no existe o no es accesible: {p}")
    if not os.access(p, os.R_OK | os.X_OK):
        raise HTTPException(400, "la carpeta no se puede leer con el usuario de la aplicación")
    if db.scalar(select(DocRoot).where(DocRoot.name == name)):
        raise HTTPException(409, "ya hay una raíz con ese nombre")
    if db.scalar(select(DocRoot).where(DocRoot.path == str(p))):
        raise HTTPException(409, "esa carpeta ya está registrada")
    r = DocRoot(name=name, path=str(p), description=body.description.strip(), created_by=user.id)
    db.add(r)
    db.commit()
    audit(db, user, "docroot.create", None, name=name, path=str(p))
    return _info(db, r)


@router.delete("/{rid:int}")
def delete_root(rid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    r = db.get(DocRoot, rid)
    if not r:
        raise HTTPException(404, "raíz no encontrada")
    n = _info(db, r)["sources"]
    if n:
        raise HTTPException(409, f"{n} fuente(s) de brains usan esta raíz: quítalas antes")
    db.delete(r)
    db.commit()
    audit(db, user, "docroot.delete", None, name=r.name)
    return {"ok": True}
