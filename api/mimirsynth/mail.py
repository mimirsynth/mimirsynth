"""Envío de correo (SMTP) para invitaciones y recuperación de contraseña. Se configura en Administración → Ajustes."""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from . import appsettings

log = logging.getLogger("mimirsynth.mail")


def configured() -> bool:
    return bool(appsettings.get("smtp_host") and appsettings.get("smtp_from"))


def send(to: str, subject: str, body: str) -> None:
    """Envía un correo de texto. Lanza si falla (quien llama decide si es grave: las invitaciones siguen teniendo su enlace copiable)."""
    host, port, mode = appsettings.get("smtp_host"), int(appsettings.get("smtp_port")), appsettings.get("smtp_security")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = appsettings.get("smtp_from"), to, subject
    msg.set_content(body)
    user, pw = appsettings.get("smtp_user"), appsettings.get_secret("smtp_password")
    ctx = ssl.create_default_context()
    if mode == "ssl":
        s = smtplib.SMTP_SSL(host, port, timeout=15, context=ctx)
    else:
        s = smtplib.SMTP(host, port, timeout=15)
    try:
        if mode == "starttls":
            s.starttls(context=ctx)
        if user:
            s.login(user, pw)
        s.send_message(msg)
    finally:
        try:
            s.quit()
        except smtplib.SMTPException:
            pass


def try_send(to: str, subject: str, body: str) -> bool:
    try:
        send(to, subject, body)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("no se pudo enviar el correo a %s: %s", to, e)
        return False
