"""Piezas comunes de la gestión de usuarios: enlaces de un solo uso, comprobaciones de administrador y sesión."""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import appsettings, brand, mail
from .deps import hash_token
from .models import Identity, User, UserToken, now


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def new_token(db: Session, user: User, purpose: str, by: User | None) -> str:
    """Crea un enlace de un solo uso (anula los anteriores del mismo tipo) y devuelve el valor en claro: solo se ve ahora."""
    db.execute(delete(UserToken).where(UserToken.user_id == user.id, UserToken.purpose == purpose, UserToken.used_at.is_(None)))
    raw = secrets.token_urlsafe(32)
    db.add(UserToken(user_id=user.id, purpose=purpose, token_hash=hash_token(raw), expires_at=now() + timedelta(days=int(appsettings.get("invite_days"))), created_by=by.id if by else None))
    db.commit()
    return raw


def link(request: Request, raw: str) -> str:
    base = (appsettings.get("public_url") or str(request.base_url)).rstrip("/")
    return f"{base}/acceso/{raw}"


def find_token(db: Session, raw: str) -> tuple[UserToken, User] | None:
    t = db.scalar(select(UserToken).where(UserToken.token_hash == hash_token(raw)))
    if not t or t.used_at or _aware(t.expires_at) < datetime.now(timezone.utc):
        return None
    u = db.get(User, t.user_id)
    if not u or u.status in ("disabled", "deleted"):
        return None
    return t, u


def admin_count(db: Session, excluding: int | None = None) -> int:
    q = select(func.count()).select_from(User).where(User.is_admin.is_(True), User.status == "active", User.sub.is_distinct_from("local-admin"))
    if excluding is not None:
        q = q.where(User.id != excluding)
    return db.scalar(q) or 0


def start_session(request: Request, user: User, method: str = "pw") -> None:
    """method: pw (contraseña sin segundo factor) | mfa (contraseña + segundo factor) | oidc (el proveedor responde de la identidad)."""
    request.session.clear()
    request.session["uid"], request.session["ep"], request.session["m"] = user.id, user.session_epoch, method


def identities(db: Session, user: User) -> list[str]:
    return [i.provider for i in db.scalars(select(Identity).where(Identity.user_id == user.id))]


def email_invite(to: str, name: str, url: str, purpose: str) -> bool:
    days = appsettings.get("invite_days")
    if purpose == "invite":
        subject, body = f"Te han invitado a {brand.NAME}", f"Hola {name or to},\n\nTe han creado una cuenta en {brand.NAME}. Para elegir tu contraseña abre este enlace (válido {days} días, un solo uso):\n\n{url}\n"
    else:
        subject, body = f"Restablece tu contraseña de {brand.NAME}", f"Hola {name or to},\n\nPara elegir una contraseña nueva abre este enlace (válido {days} días, un solo uso):\n\n{url}\n\nSi no lo has pedido tú, ignora este mensaje.\n"
    return mail.try_send(to, subject, body)


def require_not_last_admin(db: Session, target: User) -> None:
    if target.is_admin and target.status == "active" and admin_count(db, excluding=target.id) == 0:
        raise HTTPException(409, "es el último administrador activo de la instancia")
