"""Inicio de sesión: cuenta propia (email + contraseña) y, opcionalmente, OIDC. Sesión en cookie firmada.
Con MIMIRSYNTH_AUTH_MODE=off (solo desarrollo) no hay login y todo el mundo es administrador local."""
import hmac
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import appsettings, passwords, ratelimit, userlib
from .config import settings
from .deps import audit, current_user, needs_2fa_setup
from .models import Identity, User, now
from .store import get_db

router = APIRouter(prefix="/api")
log = logging.getLogger("mimirsynth.auth")
_client = None
_client_key: tuple = ()
_SETUP_TOKEN = ""  # primer arranque sin administradores: se imprime en el log y hay que pegarlo en el asistente


# --- primer arranque -----------------------------------------------------------------------------

def setup_required(db: Session) -> bool:
    return settings.auth_mode != "off" and userlib.admin_count(db) == 0


def ensure_setup_token(db: Session) -> None:
    global _SETUP_TOKEN
    if setup_required(db):
        _SETUP_TOKEN = secrets.token_urlsafe(12)
        log.warning("=" * 70 + "\nPRIMER ARRANQUE: no hay administradores. Código para el asistente de instalación:\n\n    %s\n" + "=" * 70, _SETUP_TOKEN)
    else:
        _SETUP_TOKEN = ""


def oidc_enabled() -> bool:
    return bool(appsettings.get("oidc_issuer") and appsettings.get("oidc_client_id"))


def _ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?"))


@router.get("/auth/options")
def auth_options(db: Session = Depends(get_db)):
    return {"local": True, "oidc": oidc_enabled(), "setup": setup_required(db), "password_min_length": int(appsettings.get("password_min_length"))}


class SetupIn(BaseModel):
    code: str
    email: str = Field(min_length=3, max_length=255)
    name: str = Field(min_length=1, max_length=120)
    password: str


@router.post("/auth/setup")
def setup(body: SetupIn, request: Request, db: Session = Depends(get_db)):
    if not setup_required(db):
        raise HTTPException(409, "la instancia ya tiene un administrador")
    if not ratelimit.allow(f"setup:{_ip(request)}", 10, 600):
        raise HTTPException(429, "demasiados intentos")
    if not _SETUP_TOKEN or not hmac.compare_digest(body.code.strip(), _SETUP_TOKEN):
        raise HTTPException(403, "código de instalación incorrecto (míralo en el log del servicio)")
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "email no válido")
    bad = passwords.check_policy(body.password, email, body.name)
    if bad:
        raise HTTPException(422, f"contraseña no válida: {bad}")
    u = db.scalar(select(User).where(User.email == email)) or User(email=email)
    u.name, u.is_admin, u.status, u.password_hash, u.last_login = body.name.strip(), True, "active", passwords.hash_password(body.password), now()
    db.add(u); db.commit()
    audit(db, u, "setup")
    userlib.start_session(request, u)
    ensure_setup_token(db)
    return {"ok": True}


# --- contraseña ----------------------------------------------------------------------------------

class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login_local(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    if settings.auth_mode == "off":
        return {"ok": True}
    email = body.email.strip().lower()
    if not ratelimit.allow(f"login-ip:{_ip(request)}", 60, 600) or not ratelimit.allow(f"login:{email}", 20, 600):
        raise HTTPException(429, "demasiados intentos; espera unos minutos")
    u = db.scalar(select(User).where(User.email == email))
    generic = HTTPException(401, "email o contraseña incorrectos, o cuenta bloqueada temporalmente")
    locked = bool(u and u.locked_until and (u.locked_until if u.locked_until.tzinfo else u.locked_until.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc))
    ok = passwords.verify_password(u.password_hash if u else "", body.password)  # gasta el mismo tiempo exista o no la cuenta
    if not u or u.status != "active" or locked:
        raise generic
    if not ok:
        u.failed_attempts += 1
        if u.failed_attempts >= int(appsettings.get("login_max_attempts")):
            u.locked_until, u.failed_attempts = now() + timedelta(minutes=int(appsettings.get("lockout_minutes"))), 0
            audit(db, u, "login.locked")
        db.commit()
        raise generic
    if passwords.needs_rehash(u.password_hash):
        u.password_hash = passwords.hash_password(body.password)
    if u.totp_enabled:  # segundo paso: la sesión aún no existe, solo un permiso de 5 minutos para enviar el código
        db.commit()
        request.session.clear()
        request.session["mfa"] = {"uid": u.id, "ep": u.session_epoch, "exp": time.time() + 300}
        return {"ok": True, "mfa": True}
    u.failed_attempts, u.locked_until, u.last_login = 0, None, now()
    db.commit()
    audit(db, u, "login", method="password")
    userlib.start_session(request, u)
    return {"ok": True, "must_change_password": u.must_change_password}


class MfaIn(BaseModel):
    code: str


@router.post("/auth/mfa")
def login_mfa(body: MfaIn, request: Request, db: Session = Depends(get_db)):
    """Segundo paso del inicio de sesión: código de la app de autenticación o uno de recuperación."""
    from . import mfa
    pend = request.session.get("mfa")
    if not pend or pend.get("exp", 0) < time.time():
        request.session.clear()
        raise HTTPException(401, "la verificación ha caducado; vuelve a introducir tu contraseña")
    if not ratelimit.allow(f"mfa-ip:{_ip(request)}", 60, 600) or not ratelimit.allow(f"mfa:{pend['uid']}", 20, 600):
        raise HTTPException(429, "demasiados intentos; espera unos minutos")
    u = db.get(User, pend["uid"])
    if not u or u.status != "active" or u.session_epoch != pend["ep"] or not u.totp_enabled:
        request.session.clear()
        raise HTTPException(401, "la verificación ha caducado; vuelve a introducir tu contraseña")
    if u.locked_until and (u.locked_until if u.locked_until.tzinfo else u.locked_until.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc):
        raise HTTPException(401, "cuenta bloqueada temporalmente")
    if not mfa.check_second_factor(db, u, body.code):
        u.failed_attempts += 1  # los fallos del segundo factor cuentan para el bloqueo igual que los de la contraseña
        if u.failed_attempts >= int(appsettings.get("login_max_attempts")):
            u.locked_until, u.failed_attempts = now() + timedelta(minutes=int(appsettings.get("lockout_minutes"))), 0
            audit(db, u, "login.locked")
            request.session.clear()
        db.commit()
        raise HTTPException(401, "código incorrecto")
    u.failed_attempts, u.locked_until, u.last_login = 0, None, now()
    db.commit()
    audit(db, u, "login", method="password+2fa")
    userlib.start_session(request, u, "mfa")
    return {"ok": True, "must_change_password": u.must_change_password}


@router.get("/auth/token/{raw}")
def token_info(raw: str, db: Session = Depends(get_db)):
    found = userlib.find_token(db, raw)
    if not found:
        raise HTTPException(404, "el enlace no es válido o ha caducado")
    t, u = found
    return {"purpose": t.purpose, "email": u.email, "name": u.name}


class AcceptIn(BaseModel):
    token: str
    password: str
    name: str | None = None


@router.post("/auth/accept")
def accept(body: AcceptIn, request: Request, db: Session = Depends(get_db)):
    """Acepta una invitación o un restablecimiento: fija la contraseña, activa la cuenta y abre sesión."""
    if not ratelimit.allow(f"accept:{_ip(request)}", 20, 600):
        raise HTTPException(429, "demasiados intentos")
    found = userlib.find_token(db, body.token)
    if not found:
        raise HTTPException(404, "el enlace no es válido o ha caducado")
    t, u = found
    name = (body.name or u.name or "").strip()
    bad = passwords.check_policy(body.password, u.email or "", name)
    if bad:
        raise HTTPException(422, f"contraseña no válida: {bad}")
    u.password_hash, u.status, u.must_change_password, u.failed_attempts, u.locked_until = passwords.hash_password(body.password), "active", False, 0, None
    if name:
        u.name = name
    u.session_epoch += 1  # cierra las sesiones anteriores
    t.used_at, u.last_login = now(), now()
    db.commit()
    audit(db, u, "password.set", via=t.purpose)
    userlib.start_session(request, u)
    return {"ok": True}


class ForgotIn(BaseModel):
    email: str


@router.post("/auth/forgot")
def forgot(body: ForgotIn, request: Request, db: Session = Depends(get_db)):
    """Pide un enlace de recuperación. Responde siempre igual para no revelar qué cuentas existen."""
    from . import mail
    email = body.email.strip().lower()
    if ratelimit.allow(f"forgot-ip:{_ip(request)}", 10, 3600) and ratelimit.allow(f"forgot:{email}", 3, 3600) and mail.configured():
        u = db.scalar(select(User).where(User.email == email))
        if u and u.status in ("active", "invited"):
            raw = userlib.new_token(db, u, "invite" if u.status == "invited" else "reset", None)
            userlib.email_invite(email, u.name, userlib.link(request, raw), "invite" if u.status == "invited" else "reset", u)
            audit(db, u, "password.forgot")
    return {"ok": True}


class PasswordIn(BaseModel):
    current: str = ""
    new: str


@router.post("/me/password")
def change_password(body: PasswordIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.password_hash and not passwords.verify_password(user.password_hash, body.current):
        raise HTTPException(403, "la contraseña actual no es correcta")
    bad = passwords.check_policy(body.new, user.email or "", user.name)
    if bad:
        raise HTTPException(422, f"contraseña no válida: {bad}")
    user.password_hash, user.must_change_password = passwords.hash_password(body.new), False
    user.session_epoch += 1  # cierra el resto de sesiones
    db.commit()
    audit(db, user, "password.change")
    request.session["ep"] = user.session_epoch
    return {"ok": True}


# --- OIDC ----------------------------------------------------------------------------------------

def _oidc():
    """Cliente OIDC con la configuración vigente (la de Administración → Ajustes o, en su defecto, la del entorno); se recrea si cambia."""
    global _client, _client_key
    cfg = (appsettings.get("oidc_issuer"), appsettings.get("oidc_client_id"), appsettings.get_secret("oidc_client_secret"), appsettings.get("oidc_scopes"))
    if _client is None or cfg != _client_key:
        from authlib.integrations.starlette_client import OAuth

        if not (cfg[0] and cfg[1]):
            raise HTTPException(404, "el inicio de sesión con OIDC no está configurado")
        o = OAuth()
        o.register(
            name="oidc",
            server_metadata_url=cfg[0].rstrip("/") + "/.well-known/openid-configuration",
            client_id=cfg[1],
            client_secret=cfg[2],
            client_kwargs={"scope": cfg[3], "code_challenge_method": "S256"},
        )
        _client, _client_key = o.oidc, cfg
    return _client


def _redirect_uri(request: Request) -> str:
    return (appsettings.get("public_url").rstrip("/") or str(request.base_url).rstrip("/")) + "/api/auth/callback"


@router.get("/auth/login")
async def login(request: Request):
    if settings.auth_mode == "off":
        return RedirectResponse("/")
    return await _oidc().authorize_redirect(request, _redirect_uri(request))


def _csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def apply_groups(db: Session, user: User, info: dict) -> None:
    """Concede (nunca retira ni rebaja) el rol de instancia y los roles de brain que correspondan a los grupos que trae el proveedor."""
    from .models import Brain, Membership
    from .roles import ROLES, rank
    claim = info.get(appsettings.get("oidc_groups_claim") or "groups") or []
    groups = {str(g) for g in (claim if isinstance(claim, list) else [claim])}
    admin_group = appsettings.get("oidc_admin_group").strip()
    if admin_group and admin_group in groups and not user.is_admin:
        user.is_admin = True
        audit(db, user, "user.role", via="oidc-group", is_admin=True)
    for rule in _csv(appsettings.get("oidc_group_roles")):
        group, _, target = rule.partition("=")
        slug, _, role = target.strip().partition(":")
        if group.strip() not in groups or role.strip() not in ROLES[:4]:  # por grupo nunca se concede «owner»
            continue
        brain = db.scalar(select(Brain).where(Brain.slug == slug.strip()))
        if not brain:
            continue
        m = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.brain_id == brain.id))
        if not m:
            db.add(Membership(user_id=user.id, brain_id=brain.id, role=role.strip()))
            audit(db, user, "member.set", brain, via="oidc-group", role=role.strip())
        elif rank(role.strip()) > rank(m.role):
            m.role = role.strip()
            audit(db, user, "member.set", brain, via="oidc-group", role=role.strip())
    db.commit()


def resolve_oidc_user(db: Session, info: dict) -> tuple[User | None, str]:
    """Persona a la que corresponde la identidad del proveedor, o (None, motivo). Entra quien ya está vinculado, quien fue invitado con el mismo
    email verificado, un administrador declarado en Ajustes o, si se activó, quien tenga un email verificado de un dominio permitido."""
    sub = info["sub"]
    email = (info.get("email") or info.get("preferred_username") or "").lower() or None
    verified = info.get("email_verified") is True or appsettings.get("oidc_trust_unverified_email") == "yes"
    ident = db.scalar(select(Identity).where(Identity.provider == "oidc", Identity.sub == sub))
    user = db.get(User, ident.user_id) if ident else None
    if not user and email and verified:
        user = db.scalar(select(User).where(User.email == email))
        if user and user.status in ("invited", "active"):
            db.add(Identity(user_id=user.id, provider="oidc", sub=sub, email=email))
            if user.status == "invited":
                user.status = "active"
        elif not user and email in {e.lower() for e in _csv(appsettings.get("admin_emails"))}:
            user = User(email=email, name=info.get("name") or email, is_admin=True, status="active")  # administrador declarado en Ajustes
            db.add(user); db.flush()
            db.add(Identity(user_id=user.id, provider="oidc", sub=sub, email=email))
        elif not user and info.get("email_verified") is True and appsettings.get("oidc_auto_provision") == "yes" and email.rpartition("@")[2] in {d.lower().lstrip("@") for d in _csv(appsettings.get("oidc_allowed_domains"))}:
            user = User(email=email, name=info.get("name") or email, is_admin=False, status="active")
            db.add(user); db.flush()
            db.add(Identity(user_id=user.id, provider="oidc", sub=sub, email=email))
            audit(db, user, "user.autoprovision", email=email)
        else:
            user = None
    if not user:
        return None, "not_invited"
    if user.status != "active":
        return None, "disabled"
    return user, ""


@router.get("/auth/callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    """Inicio de sesión por el proveedor de identidad (ver resolve_oidc_user para quién puede entrar)."""
    if settings.auth_mode == "off":
        return RedirectResponse("/")
    token = await _oidc().authorize_access_token(request)
    info = token.get("userinfo") or await _oidc().userinfo(token=token)
    user, why = resolve_oidc_user(db, info)
    if not user:
        return RedirectResponse(f"/?auth_error={why}")
    user.last_login = now()
    user.picture_url = str(info.get("picture") or "")[:2000]
    if not user.name:
        user.name = info.get("name") or user.email or info["sub"]
    db.commit()
    apply_groups(db, user, info)
    audit(db, user, "login", method="oidc")
    userlib.start_session(request, user, "oidc")
    return RedirectResponse("/")


@router.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(request: Request, user: User = Depends(current_user)):
    from .account import avatar_url
    return {"id": user.id, "name": user.display_name or user.name, "email": user.email, "is_admin": user.is_admin, "auth_mode": settings.auth_mode,
            "avatar": avatar_url(user), "account_url": appsettings.get("account_url"), "has_password": bool(user.password_hash), "locale": user.locale, "must_change_password": user.must_change_password,
            "totp_enabled": user.totp_enabled, "must_setup_2fa": settings.auth_mode != "off" and needs_2fa_setup(request, user)}
