"""Contraseñas: hash argon2id y política mínima."""
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from . import appsettings

_ph = PasswordHasher()
_DUMMY = _ph.hash("dummy-password-for-timing")
_COMMON = {"password", "contraseña", "contrasena", "123456789012", "qwertyuiopas", "mimirsynth", "administrador", "letmein", "welcome"}


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(hashed: str, pw: str) -> bool:
    """Comprueba la contraseña; si no hay hash, gasta el mismo tiempo para no delatar qué cuentas existen."""
    try:
        return _ph.verify(hashed or _DUMMY, pw) and bool(hashed)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


def check_policy(pw: str, email: str = "", name: str = "") -> str | None:
    """Devuelve el motivo por el que la contraseña no vale, o None."""
    n = int(appsettings.get("password_min_length"))
    if len(pw) < n:
        return f"debe tener al menos {n} caracteres"
    low = pw.lower()
    if low in _COMMON or re.fullmatch(r"(.)\1+", pw):
        return "es demasiado común"
    local = email.split("@")[0].lower() if email else ""
    if (local and len(local) >= 4 and local in low) or (name and len(name) >= 4 and name.lower() in low):
        return "no debe contener tu email ni tu nombre"
    if _is_sequence(low):
        return "es una secuencia (abcdef, 123456…)"
    if len(set(pw)) < 5:
        return "es demasiado simple: usa más caracteres distintos"
    return None


def _is_sequence(low: str) -> bool:
    """Toda la contraseña es una escalera de caracteres consecutivos (abcdefghijkl, 987654321098)."""
    if len(low) < 6:
        return False
    d = {ord(low[i + 1]) - ord(low[i]) for i in range(len(low) - 1)}
    return d <= {1} or d <= {-1}
