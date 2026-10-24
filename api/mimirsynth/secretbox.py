"""Cifrado simétrico de secretos guardados en la base de datos (clave derivada de MIMIRSYNTH_SESSION_SECRET)."""
import base64
import hashlib

from cryptography.fernet import Fernet

from .config import settings


def _f() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("mimirsynth-secretbox:" + settings.session_secret).encode()).digest()))


def seal(value: str) -> str:
    return _f().encrypt(value.encode()).decode() if value else ""


def unseal(token: str) -> str:
    return _f().decrypt(token.encode()).decode() if token else ""
