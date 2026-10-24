"""Doble factor TOTP (RFC 6238: HMAC-SHA1, 6 dígitos, 30 s) y códigos de recuperación."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30
WINDOW = 1  # se acepta un intervalo antes y otro después por si los relojes no van a la par


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    o = mac[-1] & 15
    return f"{(struct.unpack('>I', mac[o:o + 4])[0] & 0x7FFFFFFF) % 10**6:06d}"


def verify(secret: str, code: str, last_step: int = 0, now: float | None = None) -> int | None:
    """Devuelve el intervalo del código si es válido y no se ha usado ya; None si no."""
    code = code.strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return None
    cur = int((now if now is not None else time.time()) // STEP)
    for step in range(cur - WINDOW, cur + WINDOW + 1):
        if step > last_step and hmac.compare_digest(_code(secret, step), code):
            return step
    return None


def uri(secret: str, account: str, issuer: str) -> str:
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period={STEP}"


def qr_svg(data: str) -> str:
    import io

    import segno
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=5, border=2, nl=False, xmldecl=False, svgns=True, dark="#000", light="#fff")
    return buf.getvalue().decode()


def new_recovery_codes(n: int = 10) -> list[str]:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return ["".join(secrets.choice(alphabet) for _ in range(5)) + "-" + "".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(n)]


def hash_recovery(code: str) -> str:
    return hashlib.sha256(code.strip().lower().replace(" ", "").replace("-", "").encode()).hexdigest()
