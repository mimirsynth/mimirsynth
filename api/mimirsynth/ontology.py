"""Ontología por brain: tipos de entidad y de relación (con su mapa de permitidos) que guían la extracción de Graphiti al escribir."""
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .deps import BrainCtx, admin_of_brain, audit, reader
from .models import BrainOntology

router = APIRouter(prefix="/api")
PRESETS_DIR = Path(__file__).parent / "presets"
NAME = re.compile(r"^[A-Z][A-Za-z0-9]{1,40}$")


def presets() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in sorted(PRESETS_DIR.glob("*.json"))}


class TypeDef(BaseModel):
    name: str
    description: str = Field(min_length=3, max_length=1500)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not NAME.match(v):
            raise ValueError("nombre inválido: PascalCase sin espacios (p. ej. HostedOn)")
        return v


class MapDef(BaseModel):
    source: str
    target: str
    edge_types: list[str]


class OntologyIn(BaseModel):
    entity_types: list[TypeDef] = []
    edge_types: list[TypeDef] = []
    edge_type_map: list[MapDef] = []
    instructions: str = Field("", max_length=4000)  # guía libre para la extracción (custom_extraction_instructions)


def validate_ontology(o: OntologyIn) -> None:
    ents = {t.name for t in o.entity_types} | {"Entity"}
    edges = {t.name for t in o.edge_types}
    if len(ents) - 1 != len(o.entity_types) or len(edges) != len(o.edge_types):
        raise HTTPException(400, "hay nombres de tipo repetidos")
    for m in o.edge_type_map:
        if m.source not in ents or m.target not in ents:
            raise HTTPException(400, f"el mapa usa un tipo de entidad que no existe: {m.source} → {m.target}")
        bad = [e for e in m.edge_types if e not in edges]
        if bad:
            raise HTTPException(400, f"el mapa usa tipos de relación que no existen: {', '.join(bad)}")


def get_ontology(db: Session, brain_id: int) -> dict | None:
    row = db.get(BrainOntology, brain_id)
    return row.data if row and (row.data.get("entity_types") or row.data.get("edge_types")) else None


def canon(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).upper()).strip("_")


def to_graphiti(o: dict) -> dict:
    """Convierte la ontología guardada en los argumentos de `add_episode` (modelos Pydantic cuya docstring es la descripción)."""
    from pydantic import create_model

    def mk(t):
        return create_model(t["name"], __doc__=t["description"], __base__=BaseModel)
    return {"entity_types": {t["name"]: mk(t) for t in o.get("entity_types", [])} or None,
            "edge_types": {t["name"]: mk(t) for t in o.get("edge_types", [])} or None,
            "edge_type_map": {(m["source"], m["target"]): m["edge_types"] for m in o.get("edge_type_map", [])} or None,
            "custom_extraction_instructions": o.get("instructions") or None}


@router.get("/brains/{slug}/ontology")
def read_ontology(ctx: BrainCtx = Depends(reader)):
    row = ctx.db.get(BrainOntology, ctx.brain.id)
    data = row.data if row else {"entity_types": [], "edge_types": [], "edge_type_map": [], "instructions": ""}
    return {"ontology": data, "configured": bool(data.get("entity_types") or data.get("edge_types")), "presets": sorted(presets())}


@router.put("/brains/{slug}/ontology")
def write_ontology(body: OntologyIn, ctx: BrainCtx = Depends(admin_of_brain)):
    validate_ontology(body)
    data = body.model_dump()
    row = ctx.db.get(BrainOntology, ctx.brain.id)
    if row:
        row.data = data
    else:
        ctx.db.add(BrainOntology(brain_id=ctx.brain.id, data=data))
    ctx.db.commit()
    audit(ctx.db, ctx.user, "ontology.update", ctx.brain, entity_types=len(data["entity_types"]), edge_types=len(data["edge_types"]))
    return {"ok": True}


@router.post("/brains/{slug}/ontology/preset/{name}")
def apply_preset(name: str, ctx: BrainCtx = Depends(admin_of_brain)):
    p = presets().get(name)
    if not p:
        raise HTTPException(404, "paquete de ontología no encontrado")
    return write_ontology(OntologyIn(**p), ctx)
