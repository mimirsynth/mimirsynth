"""Administración de brains, miembros, usuarios y auditoría."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import userlib
from .db import client
from .deps import BrainCtx, admin_of_brain, audit, current_user, owner_of_brain, require_admin
from .models import Audit, Brain, Membership, User
from .roles import ROLES, rank
from .store import get_db

router = APIRouter(prefix="/api")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
GRAPH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$")


def _brain_out(b: Brain, role: str) -> dict:
    return {"slug": b.slug, "name": b.name, "description": b.description, "graph_name": b.graph_name, "role": role}


@router.get("/brains")
def list_brains(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.is_admin:
        return [_brain_out(b, "owner") for b in db.scalars(select(Brain).order_by(Brain.name))]
    rows = db.execute(select(Brain, Membership.role).join(Membership).where(Membership.user_id == user.id).order_by(Brain.name))
    return [_brain_out(b, r) for b, r in rows]


class BrainIn(BaseModel):
    slug: str
    name: str
    description: str = ""
    graph_name: str | None = None


@router.post("/brains", status_code=201)
def create_brain(body: BrainIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if not SLUG.match(body.slug):
        raise HTTPException(400, "slug inválido (minúsculas, números y guiones, 2-41 caracteres)")
    if db.scalar(select(Brain).where(Brain.slug == body.slug)):
        raise HTTPException(409, "ya existe un brain con ese slug")
    b = Brain(slug=body.slug, name=body.name, description=body.description, graph_name=body.graph_name or body.slug, created_by=user.id)
    db.add(b); db.commit()
    audit(db, user, "brain.create", b, slug=b.slug, graph=b.graph_name)
    return _brain_out(b, "owner")


class BrainPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    slug: str | None = None
    graph_name: str | None = None


def _count(g) -> tuple[int, int]:
    n = g.query("MATCH (n) RETURN count(n)").result_set[0][0]
    e = g.query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
    return n, e


def _move_graph(old: str, new: str) -> dict:
    """Copia el grafo, reescribe group_id (Graphiti lo guarda en cada nodo y arista) y verifica los conteos.
    El grafo original no se borra: queda como copia de seguridad."""
    c = client()
    existing = set(c.list_graphs())
    if old not in existing:
        raise HTTPException(409, f"el grafo origen '{old}' no existe")
    if new in existing:
        raise HTTPException(409, f"ya existe un grafo llamado '{new}'")
    src = c.select_graph(old)
    before = _count(src)
    src.copy(new)
    dst = c.select_graph(new)
    try:
        dst.query("MATCH (n) SET n.group_id = $g", {"g": new})
        dst.query("MATCH ()-[r]->() SET r.group_id = $g", {"g": new})
        if _count(dst) != before:
            raise RuntimeError(f"conteos distintos tras la copia: {before} vs {_count(dst)}")
    except Exception as e:  # noqa: BLE001
        dst.delete()
        raise HTTPException(500, f"migración abortada, no se ha cambiado nada: {e}")
    return {"nodes": before[0], "edges": before[1]}


@router.patch("/brains/{slug}")
def update_brain(body: BrainPatch, ctx: BrainCtx = Depends(admin_of_brain)):
    """Cambia nombre, descripción, slug o grafo de un brain.
    Slug: solo Postgres (membresías, tokens e índice cuelgan del id). Grafo: copia + reescritura de group_id (solo administrador de la instancia)."""
    db, b, changes = ctx.db, ctx.brain, {}
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(400, "el nombre no puede estar vacío")
        changes["name"] = [b.name, body.name.strip()]
    if body.description is not None:
        changes["description"] = [b.description, body.description]
    if body.slug is not None and body.slug != b.slug:
        if not SLUG.match(body.slug):
            raise HTTPException(400, "slug inválido (minúsculas, números y guiones, 2-41 caracteres)")
        if db.scalar(select(Brain).where(Brain.slug == body.slug)):
            raise HTTPException(409, "ya existe un brain con ese slug")
        changes["slug"] = [b.slug, body.slug]
    moved = None
    if body.graph_name is not None and body.graph_name != b.graph_name:
        if not ctx.user.is_admin:
            raise HTTPException(403, "solo el administrador de la instancia puede cambiar el grafo")
        if not GRAPH.match(body.graph_name):
            raise HTTPException(400, "nombre de grafo inválido (letras, números, guiones y _, 2-64 caracteres)")
        if db.scalar(select(Brain).where(Brain.graph_name == body.graph_name)):
            raise HTTPException(409, "otro brain ya usa ese grafo")
        moved = _move_graph(b.graph_name, body.graph_name)
        changes["graph_name"] = [b.graph_name, body.graph_name]
    old_graph = b.graph_name
    for k, (_, new) in changes.items():
        setattr(b, k, new)
    db.commit()
    audit(db, ctx.user, "brain.update", b, **{k: {"from": v[0], "to": v[1]} for k, v in changes.items()}, **({"moved": moved} if moved else {}))
    out = _brain_out(b, ctx.role)
    if moved:
        out["old_graph_kept"] = old_graph
    return out


class DeleteIn(BaseModel):
    confirm: str  # el slug, escrito de nuevo
    delete_graph: bool = False


@router.post("/brains/{slug}/delete")
def delete_brain(body: DeleteIn, ctx: BrainCtx = Depends(owner_of_brain)):
    """Borra un brain y todo lo que cuelga de él en Postgres (miembros, tokens, propuestas, ontología, correcciones de tipos, índice de texto).
    El grafo de FalkorDB solo se borra si se pide expresamente; por defecto se conserva y deja de estar asociado a ningún brain."""
    from sqlalchemy import delete, text

    from .index import enabled as index_enabled
    from .models import ApiToken, BrainGrant, BrainOntology, Proposal, RetypeSuggestion
    b, db = ctx.brain, ctx.db
    if body.confirm != b.slug:
        raise HTTPException(400, "la confirmación no coincide con el slug del brain")
    graph = b.graph_name
    if body.delete_graph and db.scalar(select(Brain).where(Brain.graph_name == graph, Brain.id != b.id)):
        raise HTTPException(409, "otro brain usa el mismo grafo; no se puede borrar")
    for model in (ApiToken, Proposal, BrainOntology, RetypeSuggestion, Membership):
        db.execute(delete(model).where(model.brain_id == b.id))
    db.execute(delete(BrainGrant).where((BrainGrant.source_brain_id == b.id) | (BrainGrant.target_brain_id == b.id)))  # las concesiones, de ida y de vuelta
    if index_enabled():
        db.execute(text("DELETE FROM episode_chunks WHERE brain_id = :b"), {"b": b.id})
        db.execute(text("DELETE FROM doc_chunks WHERE brain_id = :b"), {"b": b.id})
    slug, name, bid = b.slug, b.name, b.id
    db.delete(b); db.commit()
    from . import docstore
    docstore.remove_brain(bid)  # originales y texto normalizado de la memoria documental
    graph_deleted = False
    if body.delete_graph:
        try:
            client().select_graph(graph).delete(); graph_deleted = True
        except Exception as e:  # noqa: BLE001
            audit(db, ctx.user, "brain.delete.graph_failed", None, slug=slug, graph=graph, error=str(e)[:200])
    audit(db, ctx.user, "brain.delete", None, slug=slug, name=name, graph=graph, graph_deleted=graph_deleted)
    return {"deleted": slug, "graph": graph, "graph_deleted": graph_deleted}


@router.get("/brains/{slug}/members")
def list_members(ctx: BrainCtx = Depends(admin_of_brain)):
    ms = ctx.db.scalars(select(Membership).where(Membership.brain_id == ctx.brain.id)).all()
    out = [{"user_id": m.user_id, "email": m.user.email, "name": m.user.name, "role": m.role, "implicit": False} for m in ms]
    have = {m.user_id for m in ms}
    for u in ctx.db.scalars(select(User).where(User.is_admin.is_(True))):
        if u.id not in have:  # administradores de la instancia: propietarios implícitos de todos los brains
            out.insert(0, {"user_id": u.id, "email": u.email, "name": u.name, "role": "owner", "implicit": True})
    return out


class MemberIn(BaseModel):
    email: str
    role: str


def _check_assignable(ctx: BrainCtx, role: str) -> None:
    if role not in ROLES:
        raise HTTPException(400, f"rol inválido: {role}")
    if rank(role) > rank(ctx.role):
        raise HTTPException(403, "no puedes asignar un rol superior al tuyo")


@router.put("/brains/{slug}/members")
def set_member(body: MemberIn, ctx: BrainCtx = Depends(admin_of_brain)):
    _check_assignable(ctx, body.role)
    db = ctx.db
    email = body.email.strip().lower()
    u = db.scalar(select(User).where(User.email == email))
    if not u:  # invitación: usuario sin sub, se vincula en su primer login
        u = User(email=email, name=email, status="invited")
        db.add(u); db.commit()
    m = db.scalar(select(Membership).where(Membership.user_id == u.id, Membership.brain_id == ctx.brain.id))
    if m and rank(m.role) > rank(ctx.role):
        raise HTTPException(403, "no puedes modificar a un miembro con rol superior al tuyo")
    userlib.forget_grants(db, u.id, ctx.brain.id)
    if m:
        m.role = body.role
    else:
        db.add(Membership(user_id=u.id, brain_id=ctx.brain.id, role=body.role))
    db.commit()
    audit(db, ctx.user, "member.set", ctx.brain, email=email, role=body.role)
    return {"user_id": u.id, "email": email, "role": body.role}


@router.delete("/brains/{slug}/members/{user_id}")
def remove_member(user_id: int, ctx: BrainCtx = Depends(admin_of_brain)):
    m = ctx.db.scalar(select(Membership).where(Membership.user_id == user_id, Membership.brain_id == ctx.brain.id))
    if not m:
        raise HTTPException(404, "miembro no encontrado")
    if rank(m.role) > rank(ctx.role):
        raise HTTPException(403, "no puedes quitar a un miembro con rol superior al tuyo")
    userlib.forget_grants(ctx.db, user_id, ctx.brain.id)
    ctx.db.delete(m); ctx.db.commit()
    audit(ctx.db, ctx.user, "member.remove", ctx.brain, user_id=user_id)
    return {"ok": True}


@router.get("/users")
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [{"id": u.id, "email": u.email, "name": u.name, "is_admin": u.is_admin, "last_login": u.last_login} for u in db.scalars(select(User).where(User.status != "deleted", User.sub.is_distinct_from("local-admin")).order_by(User.email))]


@router.get("/audit")
def audit_log(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(Audit).order_by(Audit.id.desc()).limit(200)).all()
    return [{"ts": a.ts, "user_id": a.user_id, "brain_id": a.brain_id, "action": a.action, "detail": a.detail} for a in rows]
