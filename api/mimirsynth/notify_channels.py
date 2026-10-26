"""Canales de salida de las notificaciones: email, ntfy, Gotify, webhook y Telegram.

Cada canal es una función `send(cfg, secret, msg)` que lanza si falla. Las URL las pone el administrador de la instancia; aun así se comprueban:
solo http(s), nunca la dirección de metadatos de la nube (169.254.0.0/16) y, si el ajuste «Prohibir redes privadas» está activo, tampoco redes privadas ni locales.
Los mensajes llevan metadatos (qué ha fallado, dónde, cuántas veces), nunca el contenido de las memorias."""
import base64
import hashlib
import hmac
import ipaddress
import json
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from . import appsettings, mail

SEVERITIES = ("info", "warning", "critical")
KINDS = ("email", "ntfy", "gotify", "webhook", "telegram")


@dataclass
class Message:
    event: str
    severity: str
    title: str
    body: str
    kind: str = "alert"  # alert | recovery
    brain: str = ""
    count: int = 1
    instance: str = ""
    ts: str = ""

    def text(self) -> str:
        head = ("✅ " if self.kind == "recovery" else {"critical": "🔴 ", "warning": "🟠 ", "info": "ℹ️ "}.get(self.severity, "")) + self.title
        parts = [head, self.body.strip()]
        if self.brain:
            parts.append(f"Brain: {self.brain}")
        if self.count > 1:
            parts.append(f"Repetido {self.count} veces")
        if self.instance:
            parts.append(self.instance)
        return "\n".join(p for p in parts if p)


def _client() -> httpx.Client:
    return httpx.Client(timeout=15, follow_redirects=False)


def check_url(url: str) -> str:
    """Devuelve la URL limpia o lanza ValueError si no se puede usar."""
    u = urlparse((url or "").strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("la URL debe empezar por http:// o https://")
    block_private = appsettings.get("notify_block_private") == "yes"
    try:
        infos = {i[4][0] for i in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except OSError as e:
        raise ValueError(f"no se resuelve {u.hostname}") from e
    for a in infos:
        ip = ipaddress.ip_address(a.split("%")[0])
        if ip.is_link_local:
            raise ValueError("no se permiten direcciones link-local (metadatos de la nube)")
        if block_private and (ip.is_private or ip.is_loopback or ip.is_reserved):
            raise ValueError("el administrador ha prohibido los canales hacia redes privadas")
    return url.strip().rstrip("/")


def _ok(r: httpx.Response) -> None:
    if r.status_code >= 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")


def send_email(cfg: dict, secret: str, m: Message) -> None:
    to = [x.strip() for x in str(cfg.get("to", "")).replace(";", ",").split(",") if x.strip()]
    if not to:
        raise RuntimeError("sin destinatarios")
    if not mail.configured():
        raise RuntimeError("el correo (SMTP) no está configurado en Administración")
    mail.send(", ".join(to), m.title, m.text())


def _hdr(v: str) -> str:
    """Las cabeceras HTTP son ASCII: ntfy acepta el título con codificación MIME (RFC 2047) cuando lleva acentos o emojis."""
    return v if v.isascii() else "=?UTF-8?B?" + base64.b64encode(v.encode()).decode() + "?="


def send_ntfy(cfg: dict, secret: str, m: Message) -> None:
    base, topic = check_url(cfg.get("url") or "https://ntfy.sh"), str(cfg.get("topic", "")).strip().strip("/")
    if not topic:
        raise RuntimeError("falta el tema")
    prio = {"critical": "5", "warning": "4", "info": "3"}.get(m.severity, "3")
    headers = {"Title": _hdr(m.title), "Priority": prio,
               "Tags": "white_check_mark" if m.kind == "recovery" else {"critical": "rotating_light", "warning": "warning"}.get(m.severity, "information_source")}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    with _client() as c:
        _ok(c.post(f"{base}/{topic}", content=m.text().encode(), headers=headers))


def send_gotify(cfg: dict, secret: str, m: Message) -> None:
    base = check_url(cfg.get("url", ""))
    if not secret:
        raise RuntimeError("falta el token de la aplicación")
    prio = {"critical": 8, "warning": 5, "info": 2}.get(m.severity, 5)
    with _client() as c:
        _ok(c.post(f"{base}/message", headers={"X-Gotify-Key": secret}, json={"title": m.title, "message": m.text(), "priority": prio}))


def payload(m: Message) -> dict:
    return {"event": m.event, "kind": m.kind, "severity": m.severity, "title": m.title, "body": m.body, "brain": m.brain or None, "count": m.count, "instance": m.instance, "ts": m.ts}


def send_webhook(cfg: dict, secret: str, m: Message) -> None:
    url = check_url(cfg.get("url", ""))
    data = json.dumps(payload(m), ensure_ascii=False, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "MimirSynth"}
    if secret:  # el receptor comprueba que viene de esta instancia recalculando el HMAC-SHA256 del cuerpo
        headers["X-MimirSynth-Signature"] = "sha256=" + hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()
    with _client() as c:
        _ok(c.post(url, content=data, headers=headers))


def send_telegram(cfg: dict, secret: str, m: Message) -> None:
    if not secret or not str(cfg.get("chat_id", "")).strip():
        raise RuntimeError("faltan el token del bot o el chat")
    api = check_url(cfg.get("api_url") or "https://api.telegram.org")
    body: dict = {"chat_id": str(cfg["chat_id"]).strip(), "text": m.text()[:4000], "disable_web_page_preview": True}
    if str(cfg.get("thread_id", "")).strip():  # tema de un grupo con temas
        body["message_thread_id"] = int(cfg["thread_id"])
    with _client() as c:
        r = c.post(f"{api}/bot{secret}/sendMessage", json=body)
        if r.status_code >= 300:
            raise RuntimeError(f"Telegram HTTP {r.status_code}: {r.json().get('description', '') if r.headers.get('content-type', '').startswith('application/json') else r.text[:120]}")


SENDERS = {"email": send_email, "ntfy": send_ntfy, "gotify": send_gotify, "webhook": send_webhook, "telegram": send_telegram}

# Campos de cada tipo, para el formulario (config) y para validar. `secret`: el token o la clave, que se guarda sellado y no se devuelve.
FIELDS = {
    "email": {"config": ["to"], "secret": None},
    "ntfy": {"config": ["url", "topic"], "secret": "token (opcional)"},
    "gotify": {"config": ["url"], "secret": "token de la aplicación"},
    "webhook": {"config": ["url"], "secret": "clave de firma HMAC (opcional)"},
    "telegram": {"config": ["chat_id", "thread_id", "api_url"], "secret": "token del bot"},
}
