"""Puentes entre la memoria documental y el grafo: qué entidades menciona un documento, qué documentos mencionan una entidad,
y «promover a memoria» (convertir un pasaje en una propuesta en cuarentena para extraer hechos con Graphiti).
El documento sigue siendo la fuente de verdad: enlazar es solo señalar, no escribe nada en el grafo."""
import re
import time
from datetime import timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import docindex, docstore, index
from .db import graph, rows
from .deps import BrainCtx, contributor_of_brain, reader
from .models import Document, Proposal
from .proposals import ProposalIn, _out, create

router = APIRouter(prefix="/api/brains/{slug}/docs")
_CACHE: dict[str, tuple[float, list[dict]]] = {}
TTL = 60.0
MAX_TEXT = 2 * 1024 * 1024


def entities(graph_name: str) -> list[dict]:
    """Entidades vivas del grafo (sin las fusionadas) con sus alias; se guarda un minuto para no consultar en cada documento."""
    hit = _CACHE.get(graph_name)
    if hit and time.monotonic() - hit[0] < TTL:
        return hit[1]
    res = rows(graph(graph_name).query("MATCH (n:Entity) RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels, n.aliases AS aliases"))
    out = [{"uuid": r["uuid"], "name": r["name"] or "", "type": next((x for x in r["labels"] if x not in ("Entity", "Entity_")), ""),
            "aliases": [a for a in (r["aliases"] or []) if isinstance(a, str)]} for r in res]
    _CACHE[graph_name] = (time.monotonic(), out)
    return out


def _usable(name: str) -> bool:
    """Un nombre es buscable en texto si no es demasiado corto ni numérico (las siglas en mayúsculas de 3 letras, como PBS, sí valen)."""
    n = name.strip()
    return bool(n) and not n.replace(".", "").isdigit() and (len(n) >= 4 or (len(n) == 3 and n.isupper()))


def find_mentions(text: str, ents: list[dict]) -> list[dict]:
    """Entidades cuyo nombre o alias aparece en el texto (palabra completa, sin distinguir mayúsculas). No usa LLM."""
    by_form: dict[str, dict] = {}
    for e in ents:
        for form in [e["name"], *e["aliases"]]:
            if _usable(form):
                by_form.setdefault(form.strip().lower(), e)
    if not by_form or not text:
        return []
    forms = sorted(by_form, key=len, reverse=True)
    out: dict[str, dict] = {}
    for i in range(0, len(forms), 400):  # grupos: una alternancia enorme de regex sería lenta
        rx = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(f) for f in forms[i:i + 400]) + r")(?![\w])", re.I)
        for m in rx.finditer(text):
            e = by_form[m.group(0).lower()]
            o = out.setdefault(e["uuid"], {"uuid": e["uuid"], "name": e["name"], "type": e["type"], "count": 0})
            o["count"] += 1
    return sorted(out.values(), key=lambda x: (-x["count"], x["name"]))


def _doc(ctx: BrainCtx, doc_id: int) -> Document:
    d = ctx.db.get(Document, doc_id)
    if not d or d.brain_id != ctx.brain.id:
        raise HTTPException(404, "documento no encontrado")
    return d


@router.get("/{doc_id:int}/entities")
def doc_entities(doc_id: int, limit: int = Query(40, ge=1, le=200), ctx: BrainCtx = Depends(reader)):
    """Entidades del grafo que el documento menciona, de más a menos citadas."""
    d = _doc(ctx, doc_id)
    if not d.text_ref:
        return {"entities": []}
    p = docstore.resolve(d.text_ref)
    text = p.read_text(encoding="utf-8")[:MAX_TEXT] if p.is_file() else ""
    return {"entities": find_mentions(text, entities(ctx.brain.graph_name))[:limit]}


@router.get("/mentions")
def entity_mentions(entity: str = Query(min_length=1, max_length=64), limit: int = Query(15, ge=1, le=50), ctx: BrainCtx = Depends(reader)):
    """Documentos que mencionan una entidad (por su nombre y alias)."""
    ent = next((e for e in entities(ctx.brain.graph_name) if e["uuid"] == entity), None)
    if not ent:
        raise HTTPException(404, "entidad no encontrada")
    if not index.enabled():
        return {"entity": ent["name"], "documents": []}
    names = [n for n in [ent["name"], *ent["aliases"]] if _usable(n)]
    hits = docindex.mentions(ctx.brain.id, names, limit)
    return {"entity": ent["name"], "documents": [{"document_id": h["document_id"], "title": h["title"], "url": h["url"], "chunk": h["chunk"],
                                                  "heading_path": h["heading_path"], "chunks": h["chunks"], "snippet": h["snippet"]} for h in hits]}


class PromoteIn(BaseModel):
    chunk: int = Field(ge=0)
    text: str | None = Field(None, max_length=20000)  # el pasaje, ya recortado o editado por quien promueve; vacío = el trozo tal cual
    name: str | None = Field(None, max_length=255)


@router.post("/{doc_id:int}/promote", status_code=201)
def promote(doc_id: int, body: PromoteIn, request: Request, bg: BackgroundTasks, ctx: BrainCtx = Depends(contributor_of_brain)):
    """Convierte un pasaje en una propuesta de memoria con su procedencia. Un colaborador la deja en cuarentena; un curador la aprueba y se ingiere."""
    d = _doc(ctx, doc_id)
    near = docindex.neighbors(d.id, body.chunk, 0)
    chunk = next((n for n in near if n["chunk_idx"] == body.chunk), None)
    if not chunk or not d.text_ref:
        raise HTTPException(404, "pasaje no encontrado")
    txt = (body.text or "").strip()
    if not txt:
        full = docstore.resolve(d.text_ref).read_text(encoding="utf-8")
        txt = full[chunk["char_start"]:chunk["char_end"]].strip()
    key = f"documento {d.id} · trozo {body.chunk}"
    dup = ctx.db.scalar(select(Proposal).where(Proposal.brain_id == ctx.brain.id, Proposal.source_description.like(f"{key}%"), Proposal.status.in_(("pending", "approved", "ingested", "failed"))))
    if dup:
        raise HTTPException(409, f"este pasaje ya se promovió (propuesta #{dup.id}, {dup.status})")
    heading = (chunk.get("heading_path") or "").strip()
    src = f"Fuente: «{d.title}»" + (f", sección {heading}" if heading else "") + (f" ({d.url})" if d.url else "")
    ref = d.source_updated_at.replace(tzinfo=d.source_updated_at.tzinfo or timezone.utc) if d.source_updated_at else None
    p = create(ctx, request, bg, ProposalIn(name=(body.name or (f"{d.title} › {heading}" if heading else d.title))[:255], body=f"{txt}\n\n{src}", source="text",
                                            source_description=f"{key}: «{d.title}»"[:255], reference_time=ref, confidence=0.7))
    return _out(p)
