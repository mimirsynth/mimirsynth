"""Administración de motores de embeddings (solo administrador de la instancia).

Los vectores ya guardados (hechos en FalkorDB, fragmentos en pgvector) dependen del modelo y la dimensión: por eso estos son
inmutables y solo se puede cambiar el motor por defecto a otro con el mismo modelo y dimensión (p. ej. otro host con el mismo modelo).
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .deps import audit, require_admin
from .models import EmbeddingEngine, User
from .secretbox import seal, unseal
from .store import get_db

router = APIRouter(prefix="/api/embedding-engines")


class EmbIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=8, max_length=500, pattern="^https?://")
    model: str = Field(min_length=1, max_length=255)
    api_key: str | None = None
    enabled: bool = True


def _out(e: EmbeddingEngine) -> dict:
    return {"id": e.id, "name": e.name, "base_url": e.base_url, "model": e.model, "dim": e.dim,
            "has_key": bool(e.api_key_enc), "enabled": e.enabled, "is_default": e.is_default}


def default_embedding(db: Session) -> EmbeddingEngine | None:
    return db.scalar(select(EmbeddingEngine).where(EmbeddingEngine.is_default.is_(True), EmbeddingEngine.enabled.is_(True)))


def _probe(base_url: str, model: str, key: str) -> int:
    """Una petición de embedding real: comprueba URL, clave y modelo, y devuelve la dimensión."""
    try:
        r = httpx.post(f"{base_url.rstrip('/')}/embeddings", json={"model": model, "input": ["prueba"]},
                       headers={"Authorization": f"Bearer {key}"} if key else {}, timeout=40)
    except Exception as ex:  # noqa: BLE001
        raise HTTPException(400, f"no se pudo contactar con el endpoint: {str(ex)[:150]}")
    if r.status_code != 200:
        raise HTTPException(400, f"el endpoint respondió HTTP {r.status_code}: {r.text[:150]}")
    return len(r.json()["data"][0]["embedding"])


def _get(db: Session, eid: int) -> EmbeddingEngine:
    e = db.get(EmbeddingEngine, eid)
    if not e:
        raise HTTPException(404, "motor no encontrado")
    return e


def _check_default_ok(db: Session, e: EmbeddingEngine) -> None:
    cur = default_embedding(db)
    if cur and cur.id != e.id and (cur.model, cur.dim) != (e.model, e.dim):
        raise HTTPException(409, f"no se puede cambiar de «{cur.model}» ({cur.dim}d) a «{e.model}» ({e.dim}d): los vectores guardados "
                                 "dejarían de ser comparables. Cambiar de modelo requiere reindexar todo (aún no soportado).")
    if not cur and e.dim != settings.embedding_dim:
        raise HTTPException(409, f"el índice de texto es de {settings.embedding_dim} dimensiones y este modelo da {e.dim}")


@router.get("")
def list_engines(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_out(e) for e in db.scalars(select(EmbeddingEngine).order_by(EmbeddingEngine.id))]


@router.post("", status_code=201)
def create_engine(body: EmbIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(EmbeddingEngine).where(EmbeddingEngine.name == body.name)):
        raise HTTPException(409, "ya existe un motor con ese nombre")
    dim = _probe(body.base_url, body.model, body.api_key or "")
    e = EmbeddingEngine(name=body.name, base_url=body.base_url.rstrip("/"), model=body.model, dim=dim, api_key_enc=seal(body.api_key or ""), enabled=body.enabled)
    if db.scalar(select(EmbeddingEngine.id).where(EmbeddingEngine.is_default.is_(True))) is None and dim == settings.embedding_dim:
        e.is_default = True
    db.add(e); db.commit()
    audit(db, user, "embedding.create", None, name=e.name, model=e.model, dim=dim)
    return _out(e)


@router.patch("/{eid}")
def update_engine(eid: int, body: EmbIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    e = _get(db, eid)
    if body.model != e.model:
        raise HTTPException(409, "el modelo no se puede cambiar; crea otro motor")
    if db.scalar(select(EmbeddingEngine).where(EmbeddingEngine.name == body.name, EmbeddingEngine.id != eid)):
        raise HTTPException(409, "ya existe un motor con ese nombre")
    key = body.api_key or unseal(e.api_key_enc)
    if _probe(body.base_url, e.model, key) != e.dim:
        raise HTTPException(409, "el endpoint devuelve otra dimensión para ese modelo")
    e.name, e.base_url, e.enabled = body.name, body.base_url.rstrip("/"), body.enabled
    if body.api_key:
        e.api_key_enc = seal(body.api_key)
    if not e.enabled and e.is_default:
        e.is_default = False
    db.commit()
    audit(db, user, "embedding.update", None, name=e.name, key_changed=bool(body.api_key))
    return _out(e)


@router.post("/{eid}/default")
def make_default(eid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    e = _get(db, eid)
    if not e.enabled:
        raise HTTPException(409, "el motor está desactivado")
    _check_default_ok(db, e)
    for o in db.scalars(select(EmbeddingEngine)):
        o.is_default = o.id == eid
    db.commit()
    audit(db, user, "embedding.default", None, name=e.name)
    return _out(e)


@router.delete("/{eid}")
def delete_engine(eid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    e = _get(db, eid)
    if e.is_default:
        raise HTTPException(409, "es el motor por defecto; elige otro antes de borrarlo")
    db.delete(e); db.commit()
    audit(db, user, "embedding.delete", None, name=e.name)
    return {"ok": True}


@router.post("/{eid}/test")
def test_engine(eid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    import time
    e = _get(db, eid)
    t0 = time.time()
    try:
        dim = _probe(e.base_url, e.model, unseal(e.api_key_enc))
        return {"ok": dim == e.dim, "ms": int((time.time() - t0) * 1000), "reply": f"{dim} dimensiones", "error": None if dim == e.dim else f"dimensión {dim}, esperada {e.dim}"}
    except HTTPException as ex:
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": ex.detail}
