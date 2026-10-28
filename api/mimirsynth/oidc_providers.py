"""Administración → Identidad: proveedores OIDC (solo administrador de la instancia). El secreto se guarda sellado y nunca se devuelve."""
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import appsettings
from .deps import audit, require_admin
from .models import Brain, Identity, OidcProvider, User
from .secretbox import seal
from .settings_admin import discover
from .store import get_db

router = APIRouter(prefix="/api/oidc-providers")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
LEGACY = "oidc"  # el proveedor importado de la configuración anterior conserva su URL de retorno


def redirect_uri(slug: str, base: str) -> str:
    base = base.rstrip("/")
    return f"{base}/api/auth/callback" if slug == LEGACY else f"{base}/api/auth/callback/{slug}"


class ProviderIn(BaseModel):
    slug: str | None = None  # solo al crear: no se cambia después
    name: str = Field(min_length=1, max_length=80)
    issuer: str
    client_id: str = Field(min_length=1)
    client_secret: str | None = None  # None o vacío al editar = conservar el guardado
    scopes: str = "openid profile email"
    enabled: bool = True
    trust_unverified_email: bool = False
    auto_provision: bool = False
    allowed_domains: str = ""
    groups_claim: str = "groups"
    admin_group: str = ""
    group_roles: str = ""
    default_roles: str = ""


DEFAULT_ROLES = ("reader", "contributor")  # el acceso inicial lo recibe cualquiera del dominio sin revisión: nunca puede aprobar ni administrar


def parse_default_roles(value: str) -> list[tuple[str, str, str]]:
    """«brain:rol, brain:rol» -> [(entrada, slug, rol)], sin validar contra los brains."""
    out = []
    for item in (x.strip() for x in value.split(",")):
        if item:
            slug, _, role = item.partition(":")
            out.append((item, slug.strip(), role.strip()))
    return out


def _check_default_roles(db: Session, value: str) -> str:
    """Valida el acceso inicial al guardar el proveedor y lo devuelve normalizado."""
    for item, slug, role in parse_default_roles(value):
        if not slug or not role:
            raise HTTPException(422, f"acceso inicial: «{item}» no tiene el formato brain:rol")
        if role not in DEFAULT_ROLES:
            raise HTTPException(422, f"acceso inicial: el rol de «{item}» debe ser reader o contributor")
        if not db.scalar(select(Brain.id).where(Brain.slug == slug)):
            raise HTTPException(422, f"acceso inicial: no hay ningún brain «{slug}»")
    return ", ".join(f"{slug}:{role}" for _, slug, role in parse_default_roles(value))


def _view(p: OidcProvider, base: str) -> dict:
    return {"slug": p.slug, "name": p.name, "issuer": p.issuer, "client_id": p.client_id, "secret_set": bool(p.client_secret), "scopes": p.scopes, "enabled": p.enabled,
            "trust_unverified_email": p.trust_unverified_email, "auto_provision": p.auto_provision, "allowed_domains": p.allowed_domains, "groups_claim": p.groups_claim,
            "admin_group": p.admin_group, "group_roles": p.group_roles, "default_roles": p.default_roles, "redirect_uri": redirect_uri(p.slug, base)}


def _base(request) -> str:
    return appsettings.get("public_url").rstrip("/") or str(request.base_url).rstrip("/")


def _apply(db: Session, p: OidcProvider, body: ProviderIn) -> None:
    issuer = body.issuer.strip()
    if not issuer.startswith(("http://", "https://")):
        raise HTTPException(422, "el emisor debe empezar por http:// o https://")
    default_roles = _check_default_roles(db, body.default_roles)
    if issuer != p.issuer:
        discover(issuer)  # un emisor que no responde dejaría sin entrada a quien lo use
    p.name, p.issuer, p.client_id, p.scopes, p.enabled = body.name.strip(), issuer, body.client_id.strip(), body.scopes.strip() or "openid profile email", body.enabled
    p.trust_unverified_email, p.auto_provision = body.trust_unverified_email, body.auto_provision
    p.allowed_domains, p.groups_claim, p.admin_group, p.group_roles = body.allowed_domains.strip(), body.groups_claim.strip() or "groups", body.admin_group.strip(), body.group_roles.strip()
    p.default_roles = default_roles
    if body.client_secret:
        p.client_secret = seal(body.client_secret)


@router.get("")
def list_providers(request: Request, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_view(p, _base(request)) for p in db.scalars(select(OidcProvider).order_by(OidcProvider.position, OidcProvider.id))]


@router.post("", status_code=201)
def create_provider(body: ProviderIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    slug = (body.slug or "").strip().lower()
    if not SLUG.match(slug):
        raise HTTPException(422, "el identificador debe tener 2-31 caracteres: minúsculas, números y guiones")
    if db.scalar(select(OidcProvider).where(OidcProvider.slug == slug)):
        raise HTTPException(409, "ya hay un proveedor con ese identificador")
    if not body.client_secret:
        raise HTTPException(422, "indica el client secret")
    p = OidcProvider(slug=slug, position=(db.scalar(select(func.max(OidcProvider.position))) or 0) + 1)
    _apply(db, p, body)
    db.add(p); db.commit()
    audit(db, user, "oidc.create", slug=slug)
    return _view(p, _base(request))


def _get(db: Session, slug: str) -> OidcProvider:
    p = db.scalar(select(OidcProvider).where(OidcProvider.slug == slug))
    if not p:
        raise HTTPException(404, "proveedor desconocido")
    return p


@router.put("/{slug}")
def update_provider(slug: str, body: ProviderIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = _get(db, slug)
    _apply(db, p, body)
    db.commit()
    audit(db, user, "oidc.update", slug=slug)  # nunca se registra el secreto
    return _view(p, _base(request))


def _stranded(db: Session, slug: str) -> list[str]:
    """Emails de quienes se quedarían sin ninguna forma de entrar si desaparece este proveedor (sin contraseña y sin otra identidad)."""
    out = []
    for u in db.scalars(select(User).join(Identity, Identity.user_id == User.id).where(Identity.provider == slug, User.status == "active", User.password_hash == "")):
        others = db.scalar(select(func.count()).select_from(Identity).where(Identity.user_id == u.id, Identity.provider != slug))
        if not others:
            out.append(u.email or u.name)
    return out


@router.delete("/{slug}")
def delete_provider(slug: str, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = _get(db, slug)
    stranded = _stranded(db, slug)
    if stranded:
        raise HTTPException(409, f"no se puede borrar: {len(stranded)} persona(s) solo entran por este proveedor y se quedarían sin acceso ({', '.join(stranded[:5])}). Dales una contraseña o vincula otro proveedor antes.")
    db.query(Identity).filter(Identity.provider == slug).delete()
    db.delete(p); db.commit()
    audit(db, user, "oidc.delete", slug=slug)
    return {"ok": True}


@router.post("/{slug}/test")
def test_provider(slug: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    meta = discover(_get(db, slug).issuer)
    return {"ok": True, "issuer": meta.get("issuer"), "authorization_endpoint": meta["authorization_endpoint"], "pkce": "S256" in (meta.get("code_challenge_methods_supported") or ["S256"])}
