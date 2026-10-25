"""Mi cuenta: perfil (nombre visible, avatar), tokens personales y cierre de sesiones. La contraseña, las llaves de acceso y el doble
factor los gestiona el proveedor de identidad (OIDC); aquí solo se enlaza a él (MIMIRSYNTH_ACCOUNT_URL)."""
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import appsettings, docstore
from .config import settings
from .deps import audit, current_user
from .models import ApiToken, Audit, Brain, Membership, User
from .store import get_db

router = APIRouter(prefix="/api")
AVATAR_MAX = 1024 * 1024
_MAGIC = [(b"\x89PNG\r\n\x1a\n", ".png", "image/png"), (b"\xff\xd8\xff", ".jpg", "image/jpeg")]


def _sniff(raw: bytes) -> tuple[str, str] | None:
    for magic, ext, mime in _MAGIC:
        if raw.startswith(magic):
            return ext, mime
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp", "image/webp"
    return None


def avatar_url(u: User) -> str:
    if u.avatar_ref:
        return f"/api/users/{u.id}/avatar?v={int(u.avatar_at.timestamp()) if u.avatar_at else 0}"
    return u.picture_url or ""


def _avatar_dir() -> Path:
    d = docstore.root() / "_avatars"
    d.mkdir(parents=True, exist_ok=True)
    return d


class ProfileIn(BaseModel):
    display_name: str | None = Field(None, max_length=80)
    locale: str | None = Field(None, pattern="^(es|en)?$")


@router.get("/me/profile")
def profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    brains = []
    for b in db.scalars(select(Brain).order_by(Brain.name)):
        from .deps import effective_role
        role = effective_role(db, user, b)
        if role:
            brains.append({"slug": b.slug, "name": b.name, "role": role})
    return {"id": user.id, "name": user.display_name or user.name, "idp_name": user.name, "display_name": user.display_name, "email": user.email,
            "is_admin": user.is_admin, "auth_mode": settings.auth_mode, "has_password": bool(user.password_hash), "locale": user.locale, "avatar": avatar_url(user), "has_custom_avatar": bool(user.avatar_ref),
            "account_url": appsettings.get("account_url"), "created_at": user.created_at, "last_login": user.last_login, "brains": brains}


@router.patch("/me/profile")
def update_profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.display_name is not None:
        user.display_name = " ".join(body.display_name.split())
    if body.locale is not None:
        user.locale = body.locale
    db.commit()
    audit(db, user, "account.profile")
    return {"ok": True, "name": user.display_name or user.name}


@router.post("/me/avatar")
async def upload_avatar(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if getattr(request.state, "token", None) is not None:
        raise HTTPException(403, "un token de API no puede cambiar el perfil")
    raw = b""
    async for blk in request.stream():
        raw += blk
        if len(raw) > AVATAR_MAX:
            raise HTTPException(413, "el avatar supera 1 MB")
    kind = _sniff(raw)
    if not kind:
        raise HTTPException(415, "formato no admitido: usa PNG, JPEG o WebP")
    ext, _ = kind
    d = _avatar_dir()
    for old in d.glob(f"{user.id}.*"):
        old.unlink(missing_ok=True)
    (d / f"{user.id}{ext}").write_bytes(raw)
    user.avatar_ref, user.avatar_at = docstore.rel(d / f"{user.id}{ext}"), datetime.now(timezone.utc)
    db.commit()
    audit(db, user, "account.avatar")
    return {"ok": True, "avatar": avatar_url(user)}


@router.delete("/me/avatar")
def delete_avatar(user: User = Depends(current_user), db: Session = Depends(get_db)):
    for old in _avatar_dir().glob(f"{user.id}.*"):
        old.unlink(missing_ok=True)
    user.avatar_ref, user.avatar_at = "", None
    db.commit()
    return {"ok": True, "avatar": avatar_url(user)}


@router.get("/users/{uid}/avatar")
def get_avatar(uid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u or not u.avatar_ref:
        raise HTTPException(404, "sin avatar")
    p = docstore.resolve(u.avatar_ref)
    kind = _sniff(p.read_bytes()[:16]) if p.is_file() else None
    if not kind:
        raise HTTPException(404, "sin avatar")
    return FileResponse(p, media_type=kind[1], headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


@router.get("/me/tokens")
def my_tokens(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(ApiToken, Brain).join(Brain, Brain.id == ApiToken.brain_id).where(ApiToken.user_id == user.id, ApiToken.revoked.is_(False)).order_by(ApiToken.id.desc())
    return [{"id": t.id, "name": t.name, "role": t.role, "prefix": t.prefix, "brain": b.name, "brain_slug": b.slug, "created_at": t.created_at, "last_used_at": t.last_used_at}
            for t, b in db.execute(q).all()]


@router.get("/me/activity")
def my_activity(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Audit).where(Audit.user_id == user.id).order_by(Audit.id.desc()).limit(20))
    return [{"ts": a.ts, "action": a.action, "detail": a.detail} for a in rows]


@router.post("/me/sessions/revoke-others")
def revoke_other_sessions(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Cierra la sesión en todos los demás dispositivos: sube el contador y esta sesión adopta el nuevo."""
    user.session_epoch += 1
    db.commit()
    if settings.auth_mode != "off" and getattr(request.state, "token", None) is None:
        request.session["ep"] = user.session_epoch
    audit(db, user, "account.sessions.revoke")
    return {"ok": True}
