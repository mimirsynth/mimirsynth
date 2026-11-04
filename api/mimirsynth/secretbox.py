"""Cifrado simétrico de secretos guardados en la base de datos (clave derivada de MIMIRSYNTH_SESSION_SECRET)."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import settings


class SealedSecretError(Exception):
    """A sealed value cannot be read: the instance runs with another MIMIRSYNTH_SESSION_SECRET than the one that sealed it (#193).
    The app answers it with a clear 503 (main.py); the message never carries the value or its ciphertext."""

    def __init__(self) -> None:
        super().__init__("a stored secret cannot be read: MIMIRSYNTH_SESSION_SECRET is not the one that sealed it")


def _f() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("mimirsynth-secretbox:" + settings.session_secret).encode()).digest()))


def seal(value: str) -> str:
    return _f().encrypt(value.encode()).decode() if value else ""


def unseal(token: str) -> str:
    if not token:
        return ""
    try:
        return _f().decrypt(token.encode()).decode()
    except InvalidToken:
        raise SealedSecretError() from None
