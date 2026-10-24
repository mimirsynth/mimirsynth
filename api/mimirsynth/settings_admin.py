"""Administración → Ajustes (solo administrador de la instancia)."""
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import appsettings, mail
from .deps import audit, require_admin
from .models import User
from .store import get_db

router = APIRouter(prefix="/api/settings")


class SettingIn(BaseModel):
    value: str | int | float


class SecretIn(BaseModel):
    value: str = ""


class OidcTest(BaseModel):
    issuer: str | None = None


def discover(issuer: str) -> dict:
    """Pide el documento de descubrimiento del proveedor: comprueba que el emisor es alcanzable y publica OIDC."""
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        r = httpx.get(url, timeout=6, follow_redirects=True)
        r.raise_for_status()
        meta = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise HTTPException(422, f"no se pudo leer {url}: {e}")
    for k in ("authorization_endpoint", "token_endpoint"):
        if k not in meta:
            raise HTTPException(422, f"el documento de descubrimiento no incluye {k}")
    return meta


@router.get("")
def list_settings(_: User = Depends(require_admin)):
    return {"groups": [{"key": k, "label": v} for k, v in appsettings.GROUPS.items()], "items": appsettings.listing(), "secrets": appsettings.secret_state()}


class MailTest(BaseModel):
    to: str


@router.post("/smtp/test")
def test_smtp(body: MailTest, user: User = Depends(require_admin)):
    if not mail.configured():
        raise HTTPException(422, "indica al menos el servidor SMTP y el remitente")
    try:
        mail.send(body.to.strip(), "Prueba de correo de MimirSynth", "Si lees esto, el envío de correo funciona.")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"no se pudo enviar: {e}")
    return {"ok": True}


@router.post("/oidc/test")
def test_oidc(body: OidcTest, _: User = Depends(require_admin)):
    meta = discover(body.issuer or appsettings.get("oidc_issuer"))
    return {"ok": True, "issuer": meta.get("issuer"), "authorization_endpoint": meta["authorization_endpoint"], "pkce": "S256" in (meta.get("code_challenge_methods_supported") or ["S256"])}


@router.put("/secret/{key}")
def put_secret(key: str, body: SecretIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if key not in appsettings.SECRET_KEYS:
        raise HTTPException(404, "ajuste desconocido")
    appsettings.set_secret(key, body.value, user.id)
    audit(db, user, "settings.secret", key=key, cleared=not body.value)  # nunca se registra el valor
    return {"ok": True}


@router.put("/{key}")
def put_setting(key: str, body: SettingIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if key not in appsettings._BY_KEY:
        raise HTTPException(404, "ajuste desconocido")
    try:
        v = appsettings.coerce(appsettings._BY_KEY[key], body.value)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e) or "valor no válido")
    if key == "oidc_issuer" and v:
        discover(str(v))  # un emisor que no responde dejaría a todos sin poder entrar
    appsettings.set_value(key, v, user.id)
    audit(db, user, "settings.set", key=key, value=v)
    return {"ok": True, "value": v}


@router.delete("/{key}")
def reset_setting(key: str, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if key not in appsettings._BY_KEY and key not in appsettings.SECRET_KEYS:
        raise HTTPException(404, "ajuste desconocido")
    appsettings.reset(key)
    audit(db, user, "settings.reset", key=key)
    return {"ok": True}
