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


ALIASES = {"generic": "general"}  # nombre del paquete de base anterior (retirado en la 0.6)


def presets() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in sorted(PRESETS_DIR.glob("*.json"))}


def preset_info() -> list[dict]:
    return [{"name": n, "title": p.get("title", n), "description": p.get("description", ""), "version": p.get("version", 1), "standards": p.get("standards", []),
             "entity_types": len(p["entity_types"]), "edge_types": len(p["edge_types"])} for n, p in presets().items()]


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
    preset: dict | None = None  # {"name", "version"} del paquete aplicado: permite avisar de actualizaciones


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
    info = preset_info()
    applied = data.get("preset")
    update = next(({"name": i["name"], "installed": applied["version"], "available": i["version"]} for i in info
                   if applied and i["name"] == applied.get("name") and i["version"] > applied.get("version", 0)), None)
    return {"ontology": data, "configured": bool(data.get("entity_types") or data.get("edge_types")), "presets": [i["name"] for i in info], "presets_info": info, "preset_update": update}


@router.put("/brains/{slug}/ontology")
def write_ontology(body: OntologyIn, ctx: BrainCtx = Depends(admin_of_brain)):
    validate_ontology(body)
    data = body.model_dump()
    row = ctx.db.get(BrainOntology, ctx.brain.id)
    if body.preset is None and row and row.data.get("preset"):
        data["preset"] = row.data["preset"]  # editar a mano no borra de dónde viene la ontología
    if row:
        row.data = data
    else:
        ctx.db.add(BrainOntology(brain_id=ctx.brain.id, data=data))
    ctx.db.commit()
    audit(ctx.db, ctx.user, "ontology.update", ctx.brain, entity_types=len(data["entity_types"]), edge_types=len(data["edge_types"]))
    return {"ok": True}


def _merge(current: dict, pack: dict) -> dict:
    """Añade lo que le falta al brain según el paquete (tipos, relaciones, reglas) sin tocar nada de lo que ya existe, y fija la versión instalada."""
    out = {k: list(current.get(k, [])) for k in ("entity_types", "edge_types", "edge_type_map")}
    for key in ("entity_types", "edge_types"):
        have = {t["name"] for t in out[key]}
        out[key] += [t for t in pack[key] if t["name"] not in have]
    rules = {(m["source"], m["target"]): m for m in out["edge_type_map"]}
    for m in pack["edge_type_map"]:
        if (m["source"], m["target"]) in rules:
            have = rules[(m["source"], m["target"])]["edge_types"]
            rules[(m["source"], m["target"])] = {**rules[(m["source"], m["target"])], "edge_types": have + [e for e in m["edge_types"] if e not in have]}
        else:
            rules[(m["source"], m["target"])] = m
    out["edge_type_map"] = list(rules.values())
    out["instructions"] = current.get("instructions") or pack.get("instructions", "")
    return out


@router.post("/brains/{slug}/ontology/preset/{name}")
def apply_preset(name: str, mode: str = "replace", ctx: BrainCtx = Depends(admin_of_brain)):
    """mode=replace sustituye la ontología entera por el paquete; mode=merge solo añade lo que falta (actualizar sin perder los cambios a mano)."""
    name = ALIASES.get(name, name)
    p = presets().get(name)
    if not p:
        raise HTTPException(404, "paquete de ontología no encontrado")
    if mode not in ("replace", "merge"):
        raise HTTPException(422, "modo no válido (replace o merge)")
    ref = {"name": name, "version": p.get("version", 1)}
    if mode == "merge":
        row = ctx.db.get(BrainOntology, ctx.brain.id)
        data = _merge(row.data if row else {}, p)
    else:
        data = {k: p.get(k, [] if k != "instructions" else "") for k in ("entity_types", "edge_types", "edge_type_map", "instructions")}
    return write_ontology(OntologyIn(**data, preset=ref), ctx)
