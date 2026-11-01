from dataclasses import dataclass
from datetime import timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import graph
import hashlib

from .models import ApiToken, Audit, Brain, Membership, User, now
from .roles import ROLES, allows, rank
from .store import get_db


def audit(db: Session, user: User | None, action: str, brain: Brain | None = None, **detail) -> None:
    db.add(Audit(user_id=user.id if user else None, brain_id=brain.id if brain else None, action=action, detail=detail))
    db.commit()


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


SCOPES = ("recall", "documents", "propose")  # what an API token may do, on top of its role (#133); a token without a list has all


def aware(d):
    """SQLite gives back dates without their zone; they are always stored in UTC."""
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def token_allows(tok: ApiToken | None, scope: str) -> bool:
    """Whether the request's token has this scope; a session (no token) always does."""
    return tok is None or tok.scopes is None or scope in tok.scopes


def token_expired(tok: ApiToken) -> bool:
    return tok.expires_at is not None and aware(tok.expires_at) <= now()


def _scope_of(request: Request, slug: str) -> str | None:
    """The scope a brain route needs from a token. MCP is decided tool by tool; curating and administering depend only on the role."""
    rest = request.url.path.split(f"/api/brains/{slug}", 1)[-1]
    if rest.startswith("/mcp"):
        return None
    if rest.startswith("/tokens"):
        return "tokens"
    if rest == "/docs" or rest.startswith("/docs/"):
        return "documents"
    if request.method == "POST" and rest in ("/proposals", "/proposals/corrections"):
        return "propose"
    if request.method in ("GET", "HEAD") or rest in ("/recall", "/query") or rest.startswith("/recall/"):
        return "recall"
    return None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    request.state.token = None
    request.state.locale = ""  # idioma de las respuestas (ver i18n.language)
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):  # agentes: token de API acotado a un brain
        tok = db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(auth[7:].strip()), ApiToken.revoked.is_(False)))
        if not tok:
            raise HTTPException(401, "token inválido")
        if tok.user.status != "active":  # una cuenta deshabilitada o eliminada deja también sin efecto sus tokens
            raise HTTPException(401, "token inválido")
        if token_expired(tok):  # a readable reason: agents and hooks show it as it comes
            day = aware(tok.expires_at).strftime("%Y-%m-%d")
            raise HTTPException(401, f"token caducado el {day}: crea uno nuevo, o rótalo antes de que caduque")
        tok.last_used_at = now(); db.commit()
        request.state.token = tok
        request.state.locale = tok.user.locale or ""
        return tok.user
    if settings.auth_mode == "off":  # prototipo: un administrador local implícito
        u = db.scalar(select(User).where(User.sub == "local-admin"))
        if not u:
            u = User(sub="local-admin", email=None, name="Administrador local", is_admin=True)
            db.add(u); db.commit()
        elif not u.is_admin:  # en modo prototipo el administrador local siempre es administrador
            u.is_admin = True; db.commit()
        request.state.locale = u.locale or ""
        return u
    uid = request.session.get("uid")
    u = db.get(User, uid) if uid else None
    if not u or request.session.get("ep", 0) != u.session_epoch:  # sesión cerrada desde «Mi cuenta» en otro dispositivo
        raise HTTPException(401, "no autenticado")
    request.state.locale = u.locale or ""
    if u.status != "active":
        raise HTTPException(401, "cuenta deshabilitada")
    if needs_2fa_setup(request, u) and not request.url.path.startswith(("/api/me/2fa", "/api/auth/")) and request.url.path not in ("/api/me", "/api/config"):
        raise HTTPException(403, "el administrador exige el doble factor: actívalo en «Mi cuenta» para continuar")
    return u


def needs_2fa_setup(request: Request, u: User) -> bool:
    """El administrador exige doble factor y esta sesión (entrada con contraseña) aún no lo tiene. Las entradas por OIDC se fían del proveedor; una llave de acceso ya es doble factor."""
    from . import appsettings
    return appsettings.get("require_2fa") == "yes" and not u.totp_enabled and request.session.get("m") not in ("oidc", "passkey", "mfa")


def require_admin(request: Request, user: User = Depends(current_user)) -> User:
    if getattr(request.state, "token", None) is not None or not user.is_admin:  # los tokens nunca administran la instancia
        raise HTTPException(403, "requiere administrador de la instancia")
    return user


def effective_role(db: Session, user: User, brain: Brain) -> str | None:
    if user.is_admin:
        return "owner"
    m = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.brain_id == brain.id))
    return m.role if m else None


@dataclass
class BrainCtx:
    brain: Brain
    user: User
    role: str
    db: Session

    @property
    def graph(self):
        return graph(self.brain.graph_name)


def brain_access(minimum: str):
    def dep(slug: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> BrainCtx:
        brain = db.scalar(select(Brain).where(Brain.slug == slug))
        role = effective_role(db, user, brain) if brain else None
        tok = getattr(request.state, "token", None)
        if tok is not None:  # el token solo vale para su brain y con su rol tope
            if not brain or tok.brain_id != brain.id:
                raise HTTPException(404, "brain no encontrado")
            if role is not None and rank(tok.role) < rank(role):
                role = tok.role
        if not brain or role is None:  # no revelar la existencia de brains ajenos
            raise HTTPException(404, "brain no encontrado")
        if tok is not None:
            need = _scope_of(request, slug)
            if need == "tokens":  # otherwise a token that expires could make another one that does not
                raise HTTPException(403, "los tokens de API se gestionan desde una sesión, no con otro token")
            if need and not token_allows(tok, need):
                raise HTTPException(403, f"este token no tiene el alcance «{need}»")
        if not allows(role, minimum):
            raise HTTPException(403, f"requiere rol {minimum} o superior")
        request.state.brain_id = brain.id  # a write that succeeds drops the «needs your attention» counters of the brain (attention.py)
        return BrainCtx(brain, user, role, db)

    return dep


reader = brain_access("reader")
contributor_of_brain = brain_access("contributor")
curator_of_brain = brain_access("curator")
admin_of_brain = brain_access("admin")
owner_of_brain = brain_access("owner")
