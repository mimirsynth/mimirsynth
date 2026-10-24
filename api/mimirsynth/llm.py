"""Administración de motores LLM (solo administrador de la instancia). Las claves nunca se devuelven por la API."""
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .deps import audit, require_admin
from .models import LlmEngine, User
from .secretbox import seal, unseal
from .store import get_db

router = APIRouter(prefix="/api/llm-engines")


class EngineIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=8, max_length=500, pattern="^https?://")
    model: str = Field(min_length=1, max_length=255)
    small_model: str = ""
    api_key: str | None = None  # None o vacío al editar = conservar la actual
    enabled: bool = True


def _out(e: LlmEngine) -> dict:
    return {"id": e.id, "name": e.name, "base_url": e.base_url, "model": e.model, "small_model": e.small_model,
            "has_key": bool(e.api_key_enc), "enabled": e.enabled, "is_default": e.is_default}


def default_engine(db: Session) -> LlmEngine | None:
    return db.scalar(select(LlmEngine).where(LlmEngine.is_default.is_(True), LlmEngine.enabled.is_(True)))


def resolve(db: Session) -> dict | None:
    e = default_engine(db)
    return {"base_url": e.base_url, "api_key": unseal(e.api_key_enc), "model": e.model, "small_model": e.small_model or e.model} if e else None


class ModelsIn(BaseModel):
    base_url: str = Field(pattern="^https?://")
    api_key: str | None = None
    engine_id: int | None = None  # al editar: si no se escribe clave, se usa la guardada


@router.post("/models")
def list_models(body: ModelsIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Pide al proveedor su lista de modelos (GET {base_url}/models) para rellenar el formulario."""
    key = body.api_key or (unseal(db.get(LlmEngine, body.engine_id).api_key_enc) if body.engine_id and db.get(LlmEngine, body.engine_id) else "")
    try:
        r = httpx.get(f"{body.base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {key}"} if key else {}, timeout=20)
        if r.status_code != 200:
            return {"models": [], "error": f"HTTP {r.status_code}: {r.text[:160]}"}
        ids = sorted({m.get("id") for m in r.json().get("data", []) if m.get("id")})
        return {"models": ids, "error": None if ids else "el proveedor no devolvió modelos (escribe el nombre a mano)"}
    except Exception as ex:  # noqa: BLE001
        return {"models": [], "error": str(ex)[:160]}


@router.get("")
def list_engines(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_out(e) for e in db.scalars(select(LlmEngine).order_by(LlmEngine.id))]


@router.post("", status_code=201)
def create_engine(body: EngineIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(LlmEngine).where(LlmEngine.name == body.name)):
        raise HTTPException(409, "ya existe un motor con ese nombre")
    first = db.scalar(select(LlmEngine.id).limit(1)) is None
    e = LlmEngine(name=body.name, base_url=body.base_url.rstrip("/"), model=body.model, small_model=body.small_model,
                  api_key_enc=seal(body.api_key or ""), enabled=body.enabled, is_default=first)
    db.add(e); db.commit()
    audit(db, user, "llm.create", None, name=e.name, model=e.model)
    return _out(e)


def _get(db: Session, eid: int) -> LlmEngine:
    e = db.get(LlmEngine, eid)
    if not e:
        raise HTTPException(404, "motor no encontrado")
    return e


@router.patch("/{eid}")
def update_engine(eid: int, body: EngineIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    e = _get(db, eid)
    other = db.scalar(select(LlmEngine).where(LlmEngine.name == body.name, LlmEngine.id != eid))
    if other:
        raise HTTPException(409, "ya existe un motor con ese nombre")
    e.name, e.base_url, e.model, e.small_model, e.enabled = body.name, body.base_url.rstrip("/"), body.model, body.small_model, body.enabled
    if body.api_key:
        e.api_key_enc = seal(body.api_key)
    if not e.enabled and e.is_default:
        e.is_default = False
    db.commit()
    audit(db, user, "llm.update", None, name=e.name, key_changed=bool(body.api_key))
    return _out(e)


@router.post("/{eid}/default")
def make_default(eid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    e = _get(db, eid)
    if not e.enabled:
        raise HTTPException(409, "el motor está desactivado")
    for o in db.scalars(select(LlmEngine)):
        o.is_default = o.id == eid
    db.commit()
    audit(db, user, "llm.default", None, name=e.name)
    return _out(e)


@router.delete("/{eid}")
def delete_engine(eid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    e = _get(db, eid)
    db.delete(e); db.commit()
    audit(db, user, "llm.delete", None, name=e.name)
    return {"ok": True}


@router.post("/{eid}/test")
def test_engine(eid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Una petición mínima de chat para comprobar URL, clave y modelo."""
    e = _get(db, eid)
    headers = {"Authorization": f"Bearer {unseal(e.api_key_enc)}"} if e.api_key_enc else {}
    t0 = time.time()
    try:
        r = httpx.post(f"{e.base_url}/chat/completions", headers=headers, timeout=45,
                       json={"model": e.model, "messages": [{"role": "user", "content": "Responde solo: ok"}], "max_tokens": 16})
        ms = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            return {"ok": False, "ms": ms, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        msg = (r.json().get("choices") or [{}])[0].get("message", {})
        return {"ok": True, "ms": ms, "reply": (msg.get("content") or msg.get("reasoning_content") or "")[:80]}
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": str(ex)[:200]}
