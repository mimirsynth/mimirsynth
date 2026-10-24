"""Doble factor (TOTP) de la cuenta propia: alta, baja y códigos de recuperación. El segundo paso del inicio de sesión vive en auth.py."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import appsettings, brand, passwords, ratelimit, secretbox, totp
from .deps import audit, current_user
from .models import RecoveryCode, User, now
from .store import get_db

router = APIRouter(prefix="/api/me/2fa")


def required() -> bool:
    return appsettings.get("require_2fa") == "yes"


def recovery_left(db: Session, u: User) -> int:
    return db.scalar(select(func.count()).select_from(RecoveryCode).where(RecoveryCode.user_id == u.id, RecoveryCode.used_at.is_(None))) or 0


def check_second_factor(db: Session, u: User, code: str) -> bool:
    """Acepta un código TOTP vigente (una sola vez) o uno de recuperación (que se consume)."""
    code = code.strip()
    if u.totp_enabled and u.totp_secret:
        step = totp.verify(secretbox.unseal(u.totp_secret), code, u.totp_last_step)
        if step is not None:
            u.totp_last_step = step
            db.commit()
            return True
    rc = db.scalar(select(RecoveryCode).where(RecoveryCode.user_id == u.id, RecoveryCode.code_hash == totp.hash_recovery(code), RecoveryCode.used_at.is_(None)))
    if rc and len(code.replace("-", "").replace(" ", "")) == 10:
        rc.used_at = now()
        db.commit()
        return True
    return False


def clear(db: Session, u: User) -> None:
    u.totp_secret, u.totp_enabled, u.totp_last_step = "", False, 0
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == u.id))


def _issue_codes(db: Session, u: User) -> list[str]:
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == u.id))
    codes = totp.new_recovery_codes()
    db.add_all(RecoveryCode(user_id=u.id, code_hash=totp.hash_recovery(c)) for c in codes)
    return codes


def _guard(u: User, request: Request, attempt: str) -> None:
    if not ratelimit.allow(f"mfa-me:{u.id}:{attempt}", 10, 600):
        raise HTTPException(429, "demasiados intentos; espera unos minutos")


def _confirm_password(u: User, password: str) -> None:
    if not passwords.verify_password(u.password_hash, password):
        raise HTTPException(403, "la contraseña no es correcta")


@router.get("")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"enabled": user.totp_enabled, "recovery_left": recovery_left(db, user) if user.totp_enabled else 0, "required": required(), "has_password": bool(user.password_hash)}


class BeginIn(BaseModel):
    password: str


@router.post("/begin")
def begin(body: BeginIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Genera un secreto nuevo (aún sin activar). Hace falta la contraseña: sin ella no hay segundo factor que proteger."""
    if not user.password_hash:
        raise HTTPException(409, "define primero una contraseña propia en «Mi cuenta»: el doble factor protege el acceso con contraseña")
    if user.totp_enabled:
        raise HTTPException(409, "el doble factor ya está activado")
    _guard(user, request, "begin")
    _confirm_password(user, body.password)
    secret = totp.new_secret()
    user.totp_secret = secretbox.seal(secret)
    db.commit()
    u = totp.uri(secret, user.email or user.name, brand.NAME)
    return {"secret": secret, "uri": u, "svg": totp.qr_svg(u)}


class CodeIn(BaseModel):
    code: str


@router.post("/enable")
def enable(body: CodeIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.totp_enabled or not user.totp_secret:
        raise HTTPException(409, "empieza de nuevo el alta del doble factor")
    _guard(user, request, "enable")
    step = totp.verify(secretbox.unseal(user.totp_secret), body.code)
    if step is None:
        raise HTTPException(422, "el código no es correcto; comprueba la hora del móvil e inténtalo de nuevo")
    user.totp_enabled, user.totp_last_step = True, step
    codes = _issue_codes(db, user)
    db.commit()
    audit(db, user, "2fa.enable")
    request.session["m"] = "mfa"
    return {"recovery_codes": codes}


class ConfirmIn(BaseModel):
    password: str
    code: str


@router.post("/disable")
def disable(body: ConfirmIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.totp_enabled:
        raise HTTPException(409, "el doble factor no está activado")
    if required():
        raise HTTPException(409, "el administrador exige el doble factor en esta instancia")
    _guard(user, request, "disable")
    _confirm_password(user, body.password)
    if not check_second_factor(db, user, body.code):
        raise HTTPException(422, "el código no es correcto")
    clear(db, user)
    db.commit()
    audit(db, user, "2fa.disable")
    return {"ok": True}


@router.post("/recovery")
def regenerate(body: ConfirmIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Genera 10 códigos de recuperación nuevos; los anteriores dejan de valer."""
    if not user.totp_enabled:
        raise HTTPException(409, "el doble factor no está activado")
    _guard(user, request, "recovery")
    _confirm_password(user, body.password)
    if not check_second_factor(db, user, body.code):
        raise HTTPException(422, "el código no es correcto")
    codes = _issue_codes(db, user)
    db.commit()
    audit(db, user, "2fa.recovery")
    return {"recovery_codes": codes}
