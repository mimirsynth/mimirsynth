"""Ajustes de la instancia editables desde Administración → Ajustes.

Regla: en el entorno (`.env`) solo vive lo que hace falta para arrancar y conectar (base de datos, identidad, grafo, rutas montadas). Todo lo demás
se cambia desde la interfaz y se guarda en la base de datos. Cada ajuste tiene un valor por defecto (el de la variable de entorno si existe, si no
el de fábrica) y solo se guarda la diferencia: «Restaurar» borra la fila y vuelve al por defecto. Los cambios se aplican sin reiniciar.
"""
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from .config import settings
from .models import AppSetting
from .store import _factory


@dataclass(frozen=True)
class Def:
    key: str
    group: str
    label: str
    help: str
    type: str  # int | float | str | url
    unit: str = ""
    min: float | None = None
    max: float | None = None
    choices: tuple = ()  # type == "choice": (valor, etiqueta)


GROUPS = {
    "security": "Seguridad de cuentas",
    "mail": "Correo (SMTP)",
    "identity": "Identidad (OIDC)",
    "docs": "Documentos",
    "recall": "Recuerdo (recall)",
    "ingest": "Ingesta y trabajos",
}

REGISTRY: list[Def] = [
    Def("public_url", "identity", "URL pública", "Dirección con la que se accede a la aplicación; se usa para construir la URL de retorno del inicio de sesión (p. ej. https://mimirsynth.ejemplo.com).", "url"),
    Def("oidc_issuer", "identity", "Emisor OIDC (issuer)", "URL base del proveedor de identidad; debe publicar /.well-known/openid-configuration.", "url"),
    Def("oidc_client_id", "identity", "Client ID", "Identificador de la aplicación registrada en el proveedor.", "str"),
    Def("oidc_scopes", "identity", "Scopes", "Permisos que se piden al proveedor, separados por espacios.", "str"),
    Def("admin_emails", "identity", "Administradores de la instancia", "Emails (separados por comas) que son administradores al iniciar sesión.", "str"),
    Def("oidc_trust_unverified_email", "identity", "Aceptar emails sin verificar", "Si el proveedor no marca el email como verificado (algunos no lo envían), solo se aceptará con «Sí». Más cómodo, pero quien pueda registrar un email ajeno en el proveedor podría entrar como esa persona.", "choice", choices=(("no", "No (recomendado)"), ("yes", "Sí"))),
    Def("oidc_auto_provision", "identity", "Alta automática", "Con «Sí», quien entre por el proveedor con un email verificado de uno de los dominios permitidos se da de alta solo, sin invitación, con rol de usuario y sin acceso a ningún brain (salvo el que le den sus grupos). Con «No», solo entra quien ya tiene cuenta o invitación.", "choice", choices=(("no", "No (solo invitados)"), ("yes", "Sí, para los dominios permitidos"))),
    Def("oidc_allowed_domains", "identity", "Dominios permitidos", "Dominios de email (separados por comas, p. ej. example.com) a los que se aplica el alta automática. Vacío = ninguno.", "str"),
    Def("oidc_groups_claim", "identity", "Claim de grupos", "Nombre del campo con los grupos de la persona en la identidad del proveedor (suele ser «groups»; el proveedor debe incluirlo con el scope adecuado).", "str"),
    Def("oidc_admin_group", "identity", "Grupo de administradores", "Los miembros de este grupo son administradores de la instancia. Solo concede: quitar a alguien del grupo no le retira el rol; hazlo en Usuarios.", "str"),
    Def("oidc_group_roles", "identity", "Roles por grupo", "Una regla por grupo, separadas por comas, con el formato grupo=brain:rol (roles: reader, contributor, curator, admin). Al iniciar sesión se concede el rol si la persona no tiene ya uno igual o mayor; nunca se rebaja ni se retira. Ejemplo: curadores=docs:curator, lectores=docs:reader.", "str"),
    Def("account_url", "identity", "Gestión de la cuenta", "Página de tu proveedor donde se gestionan contraseña, llaves de acceso y doble factor; se enlaza desde «Mi cuenta».", "url"),
    Def("password_min_length", "security", "Longitud mínima de contraseña", "Se aplica al crear o cambiar contraseñas.", "int", "caracteres", 8, 64),
    Def("login_max_attempts", "security", "Intentos fallidos antes de bloquear", "Tras este número de contraseñas incorrectas seguidas la cuenta se bloquea temporalmente.", "int", "", 3, 20),
    Def("lockout_minutes", "security", "Duración del bloqueo", "Tiempo que una cuenta queda bloqueada tras demasiados intentos fallidos.", "int", "min", 1, 1440),
    Def("require_2fa", "security", "Exigir doble factor", "Quien entre con contraseña deberá activar el doble factor (app de autenticación) antes de usar la aplicación. No afecta a quien entra por el proveedor de identidad, que aplica sus propias reglas.", "choice", choices=(("no", "No"), ("yes", "Sí, a todos"))),
    Def("invite_days", "security", "Validez de invitaciones y enlaces de recuperación", "Pasado este plazo el enlace deja de funcionar y hay que generar otro.", "int", "días", 1, 30),
    Def("smtp_host", "mail", "Servidor SMTP", "Necesario para enviar invitaciones y enlaces de recuperación por correo. Sin él, los enlaces se copian desde Administración.", "str"),
    Def("smtp_port", "mail", "Puerto", "Habitual: 587 (STARTTLS), 465 (SSL) o 25.", "int", "", 1, 65535),
    Def("smtp_security", "mail", "Cifrado", "STARTTLS (587), SSL/TLS (465) o ninguno (solo redes de confianza).", "choice", choices=(("starttls", "STARTTLS"), ("ssl", "SSL/TLS"), ("none", "Ninguno"))),
    Def("smtp_user", "mail", "Usuario", "Vacío si el servidor no pide autenticación.", "str"),
    Def("smtp_from", "mail", "Remitente", "Dirección que aparece como remitente, p. ej. mimirsynth@ejemplo.com.", "str"),
    Def("doc_max_mb", "docs", "Tamaño máximo de un fichero", "Los ficheros más grandes se rechazan al subirlos o al escanear carpetas.", "int", "MB", 1, 20480),
    Def("doc_part_mb", "docs", "Tamaño de cada parte de una subida", "Las subidas se envían por partes de este tamaño (máximo 64).", "int", "MB", 1, 64),
    Def("doc_text_max_mb", "docs", "Texto máximo extraído por documento", "Un documento cuyo texto supere este tamaño no se indexa.", "int", "MB", 1, 2048),
    Def("doc_min_similarity", "recall", "Similitud mínima de un pasaje", "Coseno mínimo para que un pasaje documental entre en el recall. Depende del modelo de embeddings; con nomic-embed-text, 0,66.", "float", "", 0, 1),
    Def("doc_passages", "recall", "Pasajes documentales por recall", "Máximo de pasajes de documentos que acompañan a los hechos en cada recall.", "int", "", 0, 10),
    Def("doc_search_timeout", "recall", "Tiempo máximo de la búsqueda documental", "Si tarda más, el recall responde sin documentos.", "float", "s", 0.1, 10),
    Def("index_sync_minutes", "recall", "Sincronización del índice de texto", "Cada cuántos minutos se copia el texto de los episodios al índice. 0 = desactivada.", "int", "min", 0, 1440),
    Def("ingest_retries", "ingest", "Reintentos de la ingesta", "Intentos cuando el modelo responde con límite de tasa o un error transitorio.", "int", "", 1, 20),
    Def("jobs_keep_days", "ingest", "Conservar trabajos terminados", "Pasado este plazo se borran los trabajos terminados, fallidos y cancelados.", "int", "días", 1, 3650),
    Def("jobs_keep_scheduled_days", "ingest", "Conservar reescaneos programados", "Los reescaneos automáticos sin incidencias son ruido (uno cada pocos minutos): se borran antes.", "int", "días", 1, 365),
]
_BY_KEY = {d.key: d for d in REGISTRY}

_TTL = 5.0
_cache: tuple[float, dict] = (0.0, {})


def _overrides() -> dict:
    global _cache
    t, data = _cache
    if time.monotonic() - t < _TTL:
        return data
    try:
        with _factory()() as db:
            data = {r.key: r.value.get("v") for r in db.scalars(select(AppSetting))}
    except Exception:  # noqa: BLE001  (tabla aún sin crear: manda el valor por defecto)
        data = {}
    _cache = (time.monotonic(), data)
    return data


SECRET_KEYS = {"oidc_client_secret", "smtp_password"}


def get_secret(key: str) -> str:
    """Secreto guardado cifrado en la base de datos (o, sin él, el de la variable de entorno)."""
    from .secretbox import unseal
    v = _overrides().get(key)
    return unseal(v) if v else str(default(key) or "")


def set_secret(key: str, raw: str, user_id: int | None) -> None:
    from .secretbox import seal
    with _factory()() as db:
        row = db.get(AppSetting, key)
        if not raw:
            if row:
                db.delete(row)
        elif row:
            row.value, row.updated_at, row.updated_by = {"v": seal(raw)}, datetime.now(timezone.utc), user_id
        else:
            db.add(AppSetting(key=key, value={"v": seal(raw)}, updated_by=user_id))
        db.commit()
    invalidate()


def default(key: str):
    return getattr(settings, key)


def get(key: str):
    """Valor vigente: el cambiado desde la interfaz o, si no lo hay, el por defecto."""
    v = _overrides().get(key)
    return default(key) if v is None else v


def coerce(d: Def, raw):
    if d.type == "int":
        v = int(raw)
    elif d.type == "float":
        v = float(raw)
    else:
        v = str(raw).strip()
        if d.type == "choice" and v not in dict(d.choices):
            raise ValueError("opción no válida")
        if d.type == "url" and v and not v.startswith(("http://", "https://", "/")):
            raise ValueError("debe empezar por http:// o https://")
        return v
    if (d.min is not None and v < d.min) or (d.max is not None and v > d.max):
        raise ValueError(f"debe estar entre {d.min:g} y {d.max:g}")
    return v


def set_value(key: str, raw, user_id: int | None) -> object:
    d = _BY_KEY[key]
    v = coerce(d, raw)
    with _factory()() as db:
        if v == default(key) and not isinstance(default(key), bool):
            # igual que el valor por defecto: no hace falta guardar nada
            row = db.get(AppSetting, key)
            if row:
                db.delete(row)
        else:
            row = db.get(AppSetting, key)
            if row:
                row.value, row.updated_at, row.updated_by = {"v": v}, datetime.now(timezone.utc), user_id
            else:
                db.add(AppSetting(key=key, value={"v": v}, updated_by=user_id))
        db.commit()
    invalidate()
    return v


def reset(key: str) -> None:
    with _factory()() as db:
        row = db.get(AppSetting, key)
        if row:
            db.delete(row)
            db.commit()
    invalidate()


def invalidate() -> None:
    global _cache
    _cache = (0.0, {})


def listing() -> list[dict]:
    ov = _overrides()
    return [{"key": d.key, "group": d.group, "group_label": GROUPS[d.group], "label": d.label, "help": d.help, "type": d.type, "unit": d.unit, "min": d.min, "max": d.max, "choices": [{"value": a, "label": b} for a, b in d.choices],
             "value": get(d.key), "default": default(d.key), "changed": ov.get(d.key) is not None} for d in REGISTRY]


def secret_state() -> dict:
    return {k: {"set": bool(get_secret(k)), "changed": _overrides().get(k) is not None} for k in SECRET_KEYS}
