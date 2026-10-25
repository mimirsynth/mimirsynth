"""Administración de usuarios (solo administrador de la instancia): crear, invitar, cambiar rol, deshabilitar, restablecer y eliminar."""
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import mail, passwords, userlib
from .deps import audit, require_admin
from .models import ApiToken, Brain, Identity, Membership, User, UserToken, now
from .roles import ROLES
from .store import get_db

router = APIRouter(prefix="/api/admin/users")


def _out(db: Session, u: User) -> dict:
    ms = db.scalar(select(func.count()).select_from(Membership).where(Membership.user_id == u.id)) or 0
    locked = bool(u.locked_until and (u.locked_until if u.locked_until.tzinfo else u.locked_until.replace(tzinfo=timezone.utc)) > now())
    return {"id": u.id, "email": u.email, "name": u.display_name or u.name, "status": u.status, "is_admin": u.is_admin, "has_password": bool(u.password_hash),
            "identities": userlib.identities(db, u), "last_login": u.last_login, "created_at": u.created_at, "brains": ms, "locked": locked, "must_change_password": u.must_change_password, "totp_enabled": u.totp_enabled}


def _get(db: Session, uid: int) -> User:
    u = db.get(User, uid)
    if not u or u.status == "deleted" or u.sub == "local-admin":
        raise HTTPException(404, "usuario no encontrado")
    return u


@router.get("")
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.status != "deleted", User.sub.is_distinct_from("local-admin")).order_by(User.email))
    return {"smtp": mail.configured(), "items": [_out(db, u) for u in rows]}


@router.get("/{uid}")
def detail(uid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = _get(db, uid)
    ms = db.execute(select(Membership, Brain).join(Brain, Brain.id == Membership.brain_id).where(Membership.user_id == uid).order_by(Brain.name)).all()
    return {**_out(db, u), "memberships": [{"slug": b.slug, "name": b.name, "role": m.role} for m, b in ms]}


class CreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str = Field(default="", max_length=120)
    is_admin: bool = False
    mode: str = "invite"  # invite: enlace de un solo uso (y correo si hay SMTP) | password: contraseña temporal que se cambia al entrar
    password: str = ""


@router.post("", status_code=201)
def create(body: CreateIn, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email or " " in email:
        raise HTTPException(422, "email no válido")
    existing = db.scalar(select(User).where(User.email == email))
    if existing and existing.status != "deleted":
        raise HTTPException(409, "ya existe un usuario con ese email")
    if body.mode not in ("invite", "password"):
        raise HTTPException(422, "modo no válido")
    u = existing or User(email=email)  # un usuario eliminado puede volver a invitarse: se reutiliza su fila
    u.name, u.is_admin, u.invited_by = body.name.strip() or email, body.is_admin, admin.id
    u.password_hash, u.sub, u.avatar_ref, u.picture_url = "", None, "", ""
    out: dict = {}
    if body.mode == "password":
        bad = passwords.check_policy(body.password, email, u.name)
        if bad:
            raise HTTPException(422, f"contraseña no válida: {bad}")
        u.password_hash, u.status, u.must_change_password = passwords.hash_password(body.password), "active", True
    else:
        u.status, u.must_change_password = "invited", False
    db.add(u); db.commit()
    if body.mode == "invite":
        url = userlib.link(request, userlib.new_token(db, u, "invite", admin))
        out = {"link": url, "emailed": userlib.email_invite(email, u.name, url, "invite", u) if mail.configured() else False}
    audit(db, admin, "user.create", email=email, mode=body.mode, is_admin=body.is_admin)
    return {**_out(db, u), **out}


class PatchIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    is_admin: bool | None = None
    status: str | None = None  # active | disabled


@router.patch("/{uid}")
def patch(uid: int, body: PatchIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = _get(db, uid)
    if body.status is not None:
        if body.status not in ("active", "disabled") or u.status == "invited":
            raise HTTPException(422, "estado no válido")
        if body.status == "disabled":
            if u.id == admin.id:
                raise HTTPException(409, "no puedes deshabilitar tu propia cuenta")
            userlib.require_not_last_admin(db, u)
            u.session_epoch += 1
        u.status = body.status
        audit(db, admin, "user.status", user_id=u.id, email=u.email, status=body.status)
    if body.is_admin is not None and body.is_admin != u.is_admin:
        if not body.is_admin:
            if u.id == admin.id:
                raise HTTPException(409, "no puedes quitarte a ti mismo el rol de administrador")
            userlib.require_not_last_admin(db, u)
        u.is_admin = body.is_admin
        audit(db, admin, "user.role", user_id=u.id, email=u.email, is_admin=body.is_admin)
    if body.name is not None:
        u.name = body.name.strip() or u.name
    db.commit()
    return _out(db, u)


@router.post("/{uid}/link")
def new_link(uid: int, request: Request, send_email: bool = True, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Enlace nuevo: de invitación si la cuenta aún no se ha aceptado, de restablecimiento de contraseña si ya está activa."""
    u = _get(db, uid)
    if u.status not in ("invited", "active"):
        raise HTTPException(409, "la cuenta está deshabilitada")
    purpose = "invite" if u.status == "invited" else "reset"
    url = userlib.link(request, userlib.new_token(db, u, purpose, admin))
    emailed = bool(send_email and u.email and mail.configured() and userlib.email_invite(u.email, u.name, url, purpose, u))
    audit(db, admin, "user.link", user_id=u.id, email=u.email, purpose=purpose, emailed=emailed)
    return {"link": url, "purpose": purpose, "emailed": emailed}


@router.post("/{uid}/logout")
def force_logout(uid: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = _get(db, uid)
    u.session_epoch += 1
    db.commit()
    audit(db, admin, "user.logout", user_id=u.id, email=u.email)
    return {"ok": True}


@router.post("/{uid}/unlock")
def unlock(uid: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = _get(db, uid)
    u.failed_attempts, u.locked_until = 0, None
    db.commit()
    audit(db, admin, "user.unlock", user_id=u.id, email=u.email)
    return {"ok": True}


@router.post("/{uid}/mfa/reset")
def reset_mfa(uid: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Quita el doble factor de una cuenta (perdió el móvil y los códigos). Cierra sus sesiones."""
    from . import mfa
    u = _get(db, uid)
    mfa.clear(db, u)
    u.session_epoch += 1
    db.commit()
    audit(db, admin, "user.mfa_reset", user_id=u.id, email=u.email)
    return {"ok": True}


class MemberIn(BaseModel):
    slug: str
    role: str | None = None  # None = quitar del brain


@router.put("/{uid}/memberships")
def set_membership(uid: int, body: MemberIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = _get(db, uid)
    b = db.scalar(select(Brain).where(Brain.slug == body.slug))
    if not b:
        raise HTTPException(404, "brain no encontrado")
    m = db.scalar(select(Membership).where(Membership.user_id == uid, Membership.brain_id == b.id))
    if body.role is None:
        if m:
            db.delete(m)
    else:
        if body.role not in ROLES:
            raise HTTPException(422, f"rol inválido: {body.role}")
        if m:
            m.role = body.role
        else:
            db.add(Membership(user_id=uid, brain_id=b.id, role=body.role))
    db.commit()
    audit(db, admin, "member.set" if body.role else "member.remove", b, email=u.email, role=body.role)
    return {"ok": True}


@router.delete("/{uid}")
def remove_user(uid: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Elimina la cuenta: se anonimiza (sin email, nombre ni credenciales) y se conserva la fila para no romper la historia de propuestas y auditoría."""
    u = _get(db, uid)
    if u.id == admin.id:
        raise HTTPException(409, "no puedes eliminar tu propia cuenta")
    userlib.require_not_last_admin(db, u)
    email = u.email
    db.execute(delete(Membership).where(Membership.user_id == u.id))
    db.execute(delete(Identity).where(Identity.user_id == u.id))
    db.execute(delete(UserToken).where(UserToken.user_id == u.id))
    for t in db.scalars(select(ApiToken).where(ApiToken.user_id == u.id)):
        t.revoked = True
    u.email, u.sub, u.name, u.display_name, u.picture_url, u.avatar_ref = None, None, "Usuario eliminado", "", "", ""
    from . import mfa
    mfa.clear(db, u)
    u.password_hash, u.status, u.is_admin, u.session_epoch = "", "deleted", False, u.session_epoch + 1
    db.commit()
    audit(db, admin, "user.delete", user_id=u.id, email=email)
    return {"ok": True}
