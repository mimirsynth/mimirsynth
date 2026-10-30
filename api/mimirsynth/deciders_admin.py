"""Administración de decisores (solo administrador de la instancia) y su uso en el triaje de propuestas."""
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import decider
from .deps import audit, require_admin
from .models import DecisionEngine, User
from .secretbox import seal, unseal
from .store import get_db

log = logging.getLogger("mimirsynth.decider")
router = APIRouter(prefix="/api/decision-engines")


class DecIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=8, max_length=500, pattern="^https?://")
    model: str = Field(min_length=1, max_length=255)
    api_key: str | None = None
    threshold: float = Field(0.8, ge=0.5, le=0.99)
    enabled: bool = True


def _out(e: DecisionEngine) -> dict:
    return {"id": e.id, "name": e.name, "base_url": e.base_url, "model": e.model, "has_key": bool(e.api_key_enc),
            "threshold": e.threshold, "enabled": e.enabled, "is_default": e.is_default}


def default_decider(db: Session) -> DecisionEngine | None:
    return db.scalar(select(DecisionEngine).where(DecisionEngine.is_default.is_(True), DecisionEngine.enabled.is_(True)))


def _get(db: Session, eid: int) -> DecisionEngine:
    e = db.get(DecisionEngine, eid)
    if not e:
        raise HTTPException(404, "decisor no encontrado")
    return e


@router.get("")
def list_engines(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_out(e) for e in db.scalars(select(DecisionEngine).order_by(DecisionEngine.id))]


@router.post("", status_code=201)
def create_engine(body: DecIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(DecisionEngine).where(DecisionEngine.name == body.name)):
        raise HTTPException(409, "ya existe un decisor con ese nombre")
    first = db.scalar(select(DecisionEngine.id).limit(1)) is None
    e = DecisionEngine(name=body.name, base_url=body.base_url.rstrip("/"), model=body.model, api_key_enc=seal(body.api_key or ""),
                       threshold=body.threshold, enabled=body.enabled, is_default=first)
    db.add(e); db.commit()
    audit(db, user, "decider.create", None, name=e.name, model=e.model, threshold=e.threshold)
    return _out(e)


@router.patch("/{eid}")
def update_engine(eid: int, body: DecIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    e = _get(db, eid)
    if db.scalar(select(DecisionEngine).where(DecisionEngine.name == body.name, DecisionEngine.id != eid)):
        raise HTTPException(409, "ya existe un decisor con ese nombre")
    e.name, e.base_url, e.model, e.threshold, e.enabled = body.name, body.base_url.rstrip("/"), body.model, body.threshold, body.enabled
    if body.api_key:
        e.api_key_enc = seal(body.api_key)
    if not e.enabled and e.is_default:
        e.is_default = False
    db.commit()
    audit(db, user, "decider.update", None, name=e.name, threshold=e.threshold, key_changed=bool(body.api_key))
    return _out(e)


@router.post("/{eid}/default")
def make_default(eid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    e = _get(db, eid)
    if not e.enabled:
        raise HTTPException(409, "el decisor está desactivado")
    for o in db.scalars(select(DecisionEngine)):
        o.is_default = o.id == eid
    db.commit()
    audit(db, user, "decider.default", None, name=e.name)
    return _out(e)


@router.delete("/{eid}")
def delete_engine(eid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    e = _get(db, eid)
    db.delete(e); db.commit()
    audit(db, user, "decider.delete", None, name=e.name)
    return {"ok": True}


@router.post("/{eid}/test")
def test_engine(eid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Una decisión de ejemplo: comprueba conexión, logprobs y formato de respuesta."""
    e = _get(db, eid)
    t0 = time.time()
    try:
        r = decider.decide(e.base_url, e.model, unseal(e.api_key_enc), "Entidad: 'Nextcloud'", "¿Qué tipo de entidad es?",
                           ["Persona", "Servicio de software", "Dispositivo físico", "Ubicación"])
        return {"ok": True, "ms": int((time.time() - t0) * 1000), "reply": f"{r['letter']} ({r['prob']}) {r['probs']}"}
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": str(ex)[:200]}


def triage_proposal(pid: int) -> None:
    """Triaje en segundo plano de una propuesta pendiente. Sin decisor configurado no hace nada."""
    from . import ingest, secretguard
    from .deps import audit as _audit
    from .models import Brain, Proposal
    from .ontology import get_ontology
    from .store import _factory
    from datetime import datetime, timezone
    with _factory()() as db:
        d, p = default_decider(db), db.get(Proposal, pid)
        if not d or not p or p.status != "pending" or secretguard.flagged(p.secret_findings) or p.kind == "correction":
            return  # a flagged possible secret is decided by a person (#116); a correction, always (#109)
        brain = db.get(Brain, p.brain_id)
        try:
            context = decider.scope(brain.name, brain.description, get_ontology(db, brain.id))  # el decisor no supone ningún dominio
            res = decider.triage(d.base_url, d.model, unseal(d.api_key_enc), p.name, p.body, p.confidence, d.threshold, context=context)
        except Exception as e:  # noqa: BLE001
            log.exception("triaje fallido de la propuesta %s", pid)
            p.decision = {"engine": d.name, "error": str(e)[:200]}; db.commit()
            return
        p.decision = {"engine": d.name, "model": d.model, "threshold": d.threshold, "verdict": res["verdict"], "note": res["note"],
                      "factual": res["factual"], "action": res["action"]}
        p.review_kind = "decider"
        if res["verdict"] == "approve":
            p.status, p.reviewed_at = "approved", datetime.now(timezone.utc)
        db.commit()
        _audit(db, None, f"proposal.triage.{res['verdict']}", brain, id=p.id, note=res["note"])
        approved = res["verdict"] == "approve"
    if approved and ingest.enabled():
        ingest.submit_ingest(pid, brain.id, p.name)
