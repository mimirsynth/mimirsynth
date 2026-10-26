"""Llaves de acceso (WebAuthn / passkeys): alta y baja en «Mi cuenta», entrada sin contraseña y segundo factor tras la contraseña.

Una llave de acceso exige verificación de usuario (huella, rostro o PIN del dispositivo): por sí sola ya son dos factores, así que entrar con ella
cuenta como doble factor cumplido. Tras la contraseña puede usarse también como segundo factor, igual que el TOTP.
Solo se guarda la clave pública y un contador; la privada no sale del autenticador. El reto va en la sesión firmada, de un solo uso y con caducidad."""
import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from webauthn import (base64url_to_bytes, generate_authentication_options, generate_registration_options, options_to_json,
                      verify_authentication_response, verify_registration_response)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor, ResidentKeyRequirement, UserVerificationRequirement)

from . import appsettings, brand, passwords, ratelimit, userlib
from .config import settings
from .deps import audit, current_user
from .models import Identity, Passkey, User, now
from .store import get_db

router = APIRouter(prefix="/api")
log = logging.getLogger("mimirsynth.passkeys")
CHALLENGE_TTL = 300  # segundos para completar el gesto en el dispositivo


def _base(request: Request) -> str:
    return appsettings.get("public_url").rstrip("/") or str(request.base_url).rstrip("/")


def _rp(request: Request) -> tuple[str, str]:
    """(RP ID, origen). El RP ID es el dominio público; una llave creada en un dominio no vale en otro."""
    u = urlparse(_base(request))
    return u.hostname or "localhost", f"{u.scheme}://{u.netloc}"


def _put_challenge(request: Request, purpose: str, challenge: bytes, **extra) -> None:
    request.session["pk"] = {"p": purpose, "c": bytes_to_base64url(challenge), "exp": time.time() + CHALLENGE_TTL, **extra}


def _take_challenge(request: Request, purpose: str) -> dict:
    pend = request.session.pop("pk", None)  # de un solo uso: un intento fallido obliga a pedir otro reto
    if not pend or pend.get("p") != purpose or pend.get("exp", 0) < time.time():
        raise HTTPException(400, "la verificación ha caducado; inténtalo de nuevo")
    return pend


def _descriptors(items: list[Passkey]) -> list[PublicKeyCredentialDescriptor]:
    return [PublicKeyCredentialDescriptor(id=base64url_to_bytes(p.credential_id)) for p in items]


def count(db: Session, u: User) -> int:
    return db.scalar(select(func.count()).select_from(Passkey).where(Passkey.user_id == u.id)) or 0


def _out(p: Passkey) -> dict:
    return {"id": p.id, "name": p.name, "created_at": p.created_at, "last_used_at": p.last_used_at, "backed_up": p.backed_up, "transports": p.transports}


def _guard(u: User, what: str) -> None:
    if not ratelimit.allow(f"passkey-me:{u.id}:{what}", 20, 600):
        raise HTTPException(429, "demasiados intentos; espera unos minutos")


# ---- gestión en «Mi cuenta» ----
@router.get("/me/passkeys")
def list_passkeys(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_out(p) for p in db.scalars(select(Passkey).where(Passkey.user_id == user.id).order_by(Passkey.id))]


class BeginIn(BaseModel):
    password: str = ""


def _confirm_password(u: User, password: str) -> None:
    if u.password_hash and not passwords.verify_password(u.password_hash, password):
        raise HTTPException(403, "la contraseña no es correcta")


@router.post("/me/passkeys/begin")
def begin_registration(body: BeginIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Opciones para crear una llave. Con contraseña propia, hay que escribirla: una sesión abierta y desatendida no basta para añadir un acceso."""
    _guard(user, "begin")
    _confirm_password(user, body.password)
    rp_id, _ = _rp(request)
    existing = list(db.scalars(select(Passkey).where(Passkey.user_id == user.id)))
    opts = generate_registration_options(
        rp_id=rp_id, rp_name=brand.NAME, user_id=f"ms-{user.id}".encode(), user_name=user.email or user.name or f"user-{user.id}", user_display_name=user.display_name or user.name or user.email or "",
        exclude_credentials=_descriptors(existing),
        authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.PREFERRED, user_verification=UserVerificationRequirement.REQUIRED))
    _put_challenge(request, "reg", opts.challenge, uid=user.id)
    return json.loads(options_to_json(opts))


class FinishIn(BaseModel):
    credential: dict
    name: str = Field("", max_length=80)


@router.post("/me/passkeys/finish", status_code=201)
def finish_registration(body: FinishIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    pend = _take_challenge(request, "reg")
    if pend.get("uid") != user.id:
        raise HTTPException(400, "la verificación ha caducado; inténtalo de nuevo")
    rp_id, origin = _rp(request)
    try:
        v = verify_registration_response(credential=body.credential, expected_challenge=base64url_to_bytes(pend["c"]), expected_rp_id=rp_id, expected_origin=origin, require_user_verification=True)
    except Exception as e:  # noqa: BLE001
        log.info("alta de llave rechazada: %s", e)
        raise HTTPException(422, "no se pudo verificar la llave; inténtalo de nuevo") from e
    cid = bytes_to_base64url(v.credential_id)
    if db.scalar(select(Passkey).where(Passkey.credential_id == cid)):
        raise HTTPException(409, "esa llave ya está registrada")
    transports = [t for t in (body.credential.get("response", {}).get("transports") or []) if isinstance(t, str)][:6]
    p = Passkey(user_id=user.id, credential_id=cid, public_key=bytes_to_base64url(v.credential_public_key), sign_count=v.sign_count,
                name=(body.name.strip() or "Llave de acceso"), transports=transports, backed_up=bool(v.credential_backed_up))
    db.add(p); db.commit()
    audit(db, user, "passkey.add", name=p.name)
    request.session["m"] = "mfa" if request.session.get("m") != "oidc" else "oidc"  # añadir una llave cumple el doble factor exigido
    return _out(p)


class RemoveIn(BaseModel):
    password: str = ""


@router.post("/me/passkeys/{pid}/delete")
def remove_passkey(pid: int, body: RemoveIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(Passkey, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "llave no encontrada")
    _guard(user, "remove")
    _confirm_password(user, body.password)
    others = count(db, user) - 1
    has_identity = bool(db.scalar(select(func.count()).select_from(Identity).where(Identity.user_id == user.id)))
    if others == 0 and not user.password_hash and not has_identity:
        raise HTTPException(409, "es tu única forma de entrar: añade antes una contraseña o vincula un proveedor de identidad")
    db.delete(p); db.commit()
    if others == 0 and not user.totp_enabled and request.session.get("m") == "mfa":
        request.session["m"] = "pw"  # sin llaves ni TOTP, esta sesión ya no cumple el doble factor exigido
    audit(db, user, "passkey.remove", name=p.name)
    return {"ok": True}


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.patch("/me/passkeys/{pid}")
def rename_passkey(pid: int, body: RenameIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(Passkey, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "llave no encontrada")
    p.name = body.name.strip() or p.name
    db.commit()
    return _out(p)


# ---- inicio de sesión ----
def _ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?")


def _locked(u: User) -> bool:
    lu = u.locked_until
    return bool(lu and (lu if lu.tzinfo else lu.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc))


def _verify(request: Request, db: Session, credential: dict, pend: dict, u_hint: User | None = None) -> tuple[User, Passkey]:
    """Comprueba la firma contra la llave guardada. Sin pista de usuario (entrada sin contraseña) la llave identifica a la cuenta."""
    cid = credential.get("id") if isinstance(credential, dict) else None
    pk = db.scalar(select(Passkey).where(Passkey.credential_id == cid)) if isinstance(cid, str) else None
    u = db.get(User, pk.user_id) if pk else None
    generic = HTTPException(401, "no se pudo verificar la llave de acceso")
    if not pk or not u or u.status != "active" or _locked(u) or (u_hint is not None and u.id != u_hint.id):
        raise generic
    rp_id, origin = _rp(request)
    try:
        v = verify_authentication_response(credential=credential, expected_challenge=base64url_to_bytes(pend["c"]), expected_rp_id=rp_id, expected_origin=origin,
                                           credential_public_key=base64url_to_bytes(pk.public_key), credential_current_sign_count=pk.sign_count, require_user_verification=True)
    except Exception as e:  # noqa: BLE001
        log.info("verificación de llave rechazada: %s", e)
        raise generic from e
    pk.sign_count, pk.last_used_at = v.new_sign_count, now()
    return u, pk


@router.post("/auth/passkey/options")
def login_options(request: Request):
    """Reto para entrar sin contraseña: no dice qué cuentas existen (la llave identifica a su dueño)."""
    if settings.auth_mode == "off":
        raise HTTPException(404, "no disponible")
    if not ratelimit.allow(f"passkey-ip:{_ip(request)}", 60, 600):
        raise HTTPException(429, "demasiados intentos; espera unos minutos")
    rp_id, _ = _rp(request)
    opts = generate_authentication_options(rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED)
    request.session.pop("mfa", None)
    _put_challenge(request, "login", opts.challenge)
    return json.loads(options_to_json(opts))


class AssertIn(BaseModel):
    credential: dict


@router.post("/auth/passkey/login")
def login(body: AssertIn, request: Request, db: Session = Depends(get_db)):
    if settings.auth_mode == "off":
        raise HTTPException(404, "no disponible")
    if not ratelimit.allow(f"passkey-ip:{_ip(request)}", 60, 600):
        raise HTTPException(429, "demasiados intentos; espera unos minutos")
    pend = _take_challenge(request, "login")
    u, pk = _verify(request, db, body.credential, pend)
    u.failed_attempts, u.locked_until, u.last_login = 0, None, now()
    db.commit()
    audit(db, u, "login", method="passkey", passkey=pk.name)
    userlib.start_session(request, u, "passkey")
    return {"ok": True, "must_change_password": u.must_change_password}


# ---- segundo factor tras la contraseña ----
def _pending_user(request: Request, db: Session) -> User:
    pend = request.session.get("mfa")
    if not pend or pend.get("exp", 0) < time.time():
        request.session.clear()
        raise HTTPException(401, "la verificación ha caducado; vuelve a introducir tu contraseña")
    u = db.get(User, pend["uid"])
    if not u or u.status != "active" or u.session_epoch != pend["ep"] or _locked(u):
        request.session.clear()
        raise HTTPException(401, "la verificación ha caducado; vuelve a introducir tu contraseña")
    if not ratelimit.allow(f"passkey-mfa:{u.id}", 20, 600) or not ratelimit.allow(f"passkey-ip:{_ip(request)}", 60, 600):
        raise HTTPException(429, "demasiados intentos; espera unos minutos")
    return u


@router.post("/auth/passkey/mfa/options")
def mfa_options(request: Request, db: Session = Depends(get_db)):
    u = _pending_user(request, db)
    items = list(db.scalars(select(Passkey).where(Passkey.user_id == u.id)))
    if not items:
        raise HTTPException(409, "esta cuenta no tiene llaves de acceso")
    rp_id, _ = _rp(request)
    opts = generate_authentication_options(rp_id=rp_id, allow_credentials=_descriptors(items), user_verification=UserVerificationRequirement.REQUIRED)
    _put_challenge(request, "mfa", opts.challenge, uid=u.id)
    return json.loads(options_to_json(opts))


@router.post("/auth/passkey/mfa")
def mfa_verify(body: AssertIn, request: Request, db: Session = Depends(get_db)):
    u = _pending_user(request, db)
    pend = _take_challenge(request, "mfa")
    if pend.get("uid") != u.id:
        raise HTTPException(400, "la verificación ha caducado; inténtalo de nuevo")
    _verify(request, db, body.credential, pend, u_hint=u)
    u.failed_attempts, u.locked_until, u.last_login = 0, None, now()
    db.commit()
    audit(db, u, "login", method="password+passkey")
    userlib.start_session(request, u, "mfa")
    return {"ok": True, "must_change_password": u.must_change_password}
