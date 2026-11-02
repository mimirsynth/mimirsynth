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
    "general": "General",
    "security": "Seguridad de cuentas",
    "mail": "Correo (SMTP)",
    "identity": "Identidad",
    "docs": "Documentos",
    "recall": "Recuerdo (recall)",
    "ingest": "Ingesta y trabajos",
    "notifications": "Notificaciones",
}

REGISTRY: list[Def] = [
    Def("default_language", "general", "Idioma por defecto", "Idioma de la interfaz y de los correos para quien no haya elegido uno propio en «Mi cuenta». Cada persona puede cambiarlo.", "choice", choices=(("es", "Español"), ("en", "English"))),
    Def("public_url", "identity", "URL pública", "Dirección con la que se accede a la aplicación; se usa para construir la URL de retorno del inicio de sesión (p. ej. https://mimirsynth.ejemplo.com).", "url"),
    Def("admin_emails", "identity", "Administradores de la instancia", "Emails (separados por comas) que entran como administradores la primera vez que inician sesión por OIDC, solo si el proveedor marca el email como verificado.", "str"),
    Def("account_url", "identity", "Gestión de la cuenta", "Página de tu proveedor donde se gestionan contraseña, llaves de acceso y doble factor; se enlaza desde «Mi cuenta».", "url"),
    Def("password_min_length", "security", "Longitud mínima de contraseña", "Se aplica al crear o cambiar contraseñas.", "int", "caracteres", 8, 64),
    Def("login_max_attempts", "security", "Intentos fallidos antes de bloquear", "Tras este número de contraseñas incorrectas seguidas la cuenta se bloquea temporalmente.", "int", "", 3, 20),
    Def("lockout_minutes", "security", "Duración del bloqueo", "Tiempo que una cuenta queda bloqueada tras demasiados intentos fallidos.", "int", "min", 1, 1440),
    Def("require_2fa", "security", "Exigir doble factor", "Quien entre con contraseña deberá activar el doble factor (app de autenticación) antes de usar la aplicación. No afecta a quien entra por el proveedor de identidad, que aplica sus propias reglas.", "choice", choices=(("no", "No"), ("yes", "Sí, a todos"))),
    Def("token_max_days", "security", "Caducidad máxima de los tokens de API", "Los tokens nuevos tienen que caducar en este plazo como mucho, también al rotarlos. 0: sin límite. Los que ya existen no cambian.", "int", "días", 0, 3650),
    Def("invite_days", "security", "Validez de invitaciones y enlaces de recuperación", "Pasado este plazo el enlace deja de funcionar y hay que generar otro.", "int", "días", 1, 30),
    Def("smtp_host", "mail", "Servidor SMTP", "Necesario para enviar invitaciones y enlaces de recuperación por correo. Sin él, los enlaces se copian desde Administración.", "str"),
    Def("smtp_port", "mail", "Puerto", "Habitual: 587 (STARTTLS), 465 (SSL) o 25.", "int", "", 1, 65535),
    Def("smtp_security", "mail", "Cifrado", "STARTTLS (587), SSL/TLS (465) o ninguno (solo redes de confianza).", "choice", choices=(("starttls", "STARTTLS"), ("ssl", "SSL/TLS"), ("none", "Ninguno"))),
    Def("smtp_user", "mail", "Usuario", "Vacío si el servidor no pide autenticación.", "str"),
    Def("smtp_from", "mail", "Remitente", "Dirección que aparece como remitente, p. ej. mimirsynth@ejemplo.com.", "str"),
    Def("doc_max_mb", "docs", "Tamaño máximo de un fichero", "Los ficheros más grandes se rechazan al subirlos o al escanear carpetas.", "int", "MB", 1, 20480),
    Def("doc_part_mb", "docs", "Tamaño de cada parte de una subida", "Las subidas se envían por partes de este tamaño (máximo 64).", "int", "MB", 1, 64),
    Def("doc_text_max_mb", "docs", "Texto máximo extraído por documento", "Un documento cuyo texto supere este tamaño no se indexa.", "int", "MB", 1, 2048),
    Def("recall_stale_weight", "recall", "Peso de un hecho a revisar", "Un hecho vigente que ha superado la vida útil de su relación pesa esto en el recall (y sale marcado «sin confirmar desde …»). 1: igual que los demás.", "float", "", 0, 1),
    Def("doc_min_similarity", "recall", "Similitud mínima de un pasaje", "Coseno mínimo para que un pasaje documental entre en el recall. Depende del modelo de embeddings; con nomic-embed-text, 0,66.", "float", "", 0, 1),
    Def("doc_passages", "recall", "Pasajes documentales por recall", "Máximo de pasajes de documentos que acompañan a los hechos en cada recall.", "int", "", 0, 10),
    Def("answer_engine", "recall", "Motor para «Responder»", "Nombre del motor LLM que redacta las respuestas con citas de Preguntar. Conviene el más capaz. Vacío: el motor LLM predeterminado.", "str"),
    Def("answer_per_hour", "recall", "Respuestas por persona y hora", "Cuántas respuestas redactadas puede pedir cada persona en cada brain por hora. Cada una es una llamada al motor. 0: sin límite.", "int", "", 0, 1000),
    Def("answer_max_tokens", "recall", "Longitud máxima de una respuesta", "Tokens que puede ocupar como mucho una respuesta redactada.", "int", "tokens", 100, 4000),
    Def("doc_search_timeout", "recall", "Tiempo máximo de la búsqueda documental", "Si tarda más, el recall responde sin documentos.", "float", "s", 0.1, 10),
    Def("index_sync_minutes", "recall", "Sincronización del índice de texto", "Cada cuántos minutos se copia el texto de los episodios al índice. 0 = desactivada.", "int", "min", 0, 1440),
    Def("ingest_retries", "ingest", "Reintentos de la ingesta", "Intentos cuando el modelo responde con límite de tasa o un error transitorio.", "int", "", 1, 20),
    Def("reindex_batch", "ingest", "Lote al cambiar de modelo de embeddings", "Textos por lote al recalcular los vectores con otro modelo. Más pequeño reparte mejor la carga en el proveedor.", "int", "textos", 1, 512),
    Def("reindex_pause", "ingest", "Pausa entre lotes al cambiar de modelo", "Segundos de espera entre lotes para respetar el límite de tasa del proveedor. Con un 429 se espera además lo que indique Retry-After.", "float", "s", 0, 600),
    Def("reindex_switch_wait", "ingest", "Espera del cambio de modelo", "Segundos que el cambio de modelo de embeddings espera a que terminen las escrituras de vectores en curso (ingestas, indexaciones). Si no terminan, el cambio se aplaza y se reintenta; las escrituras nunca se cortan.", "float", "s", 1, 3600),
    Def("reindex_orphan_hours", "ingest", "Avisar de un cambio de modelo parado", "Horas que un relleno de embeddings puede estar fallido o parado, con sus vectores sombra ocupando memoria, antes de avisar (evento «reindex.orphan»).", "float", "h", 0, 8760),
    Def("webhook_group_minutes", "ingest", "Agrupar las alertas de un webhook", "Una alerta que se repite y se resuelve dentro de este plazo deja una sola propuesta, con su inicio, su fin y el número de avisos. Si sigue activa pasado el plazo, se propone como activa y su resolución llega aparte.", "int", "min", 1, 1440),
    Def("jobs_keep_days", "ingest", "Conservar trabajos terminados", "Pasado este plazo se borran los trabajos terminados, fallidos y cancelados.", "int", "días", 1, 3650),
    Def("retention_rejected_days", "ingest", "Retención: texto de las propuestas rechazadas", "Pasado este plazo desde que se rechazó, una propuesta pierde su texto (queda su estado, sus autores y sus fechas). Cada brain puede fijar el suyo. 0: sin plazo.", "int", "días", 0, 3650),
    Def("retention_jobs_days", "ingest", "Retención: trabajos terminados de cada brain", "Pasado este plazo se borran los trabajos terminados, fallidos y cancelados de un brain, antes que con el plazo general de arriba. Cada brain puede fijar el suyo. 0: sin plazo.", "int", "días", 0, 3650),
    Def("retention_ratings_days", "ingest", "Retención: valoraciones del recall", "Pasado este plazo se borran las valoraciones del recall de un brain (y los registros de las consultas que valoraban). Cada brain puede fijar el suyo. 0: sin plazo.", "int", "días", 0, 3650),
    Def("jobs_keep_scheduled_days", "ingest", "Conservar reescaneos programados", "Los reescaneos automáticos sin incidencias son ruido (uno cada pocos minutos): se borran antes.", "int", "días", 1, 365),
    Def("notify_cooldown_minutes", "notifications", "Aviso repetido", "Mientras un problema siga abierto no se vuelve a avisar por los canales hasta pasado este plazo (en la campana solo suma una repetición). Un problema resuelto avisa de la recuperación.", "int", "min", 1, 10080),
    Def("notify_quiet_start", "notifications", "Silencio desde", "Hora (HH:MM) a partir de la cual solo se envían los avisos críticos; el resto espera al final del silencio. Vacío = sin horas de silencio.", "str"),
    Def("notify_quiet_end", "notifications", "Silencio hasta", "Hora (HH:MM) en que termina el silencio. Se usa la hora del servidor.", "str"),
    Def("notify_health_minutes", "notifications", "Comprobar el estado cada", "Cada cuántos minutos se comprueba que el grafo y los modelos de IA responden (un modelo con clave de pago recibe una llamada mínima). 0 = no comprobar.", "int", "min", 0, 1440),
    Def("notify_health_failures", "notifications", "Fallos seguidos para avisar", "Cuántas comprobaciones seguidas deben fallar antes de avisar de que el grafo o un modelo no responde. Con 2, un error puntual de un proveedor no genera aviso. Con 1 se avisa al primer fallo.", "int", "", 1, 10),
    Def("notify_update_check", "notifications", "Avisar de versiones nuevas", "Una vez al día consulta en GitHub si hay una versión más reciente. Es la única conexión de salida que hace la instancia por su cuenta; está desactivada por defecto.", "choice", choices=(("no", "No"), ("yes", "Sí"))),
    Def("notify_block_private", "notifications", "Prohibir redes privadas", "Impide que los canales apunten a direcciones privadas o locales (protege de que se use un canal para llegar a servicios internos). Déjalo en «No» si tu ntfy o Gotify están en la red local.", "choice", choices=(("no", "No"), ("yes", "Sí"))),
    Def("notify_keep_days", "notifications", "Conservar avisos", "Pasado este plazo se borran los avisos y su historial de envíos.", "int", "días", 1, 3650),
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


SECRET_KEYS = {"smtp_password"}


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


def stored(key: str):
    """What is saved under `key` for something that is not a setting of the registry (the metrics token): None if nothing."""
    return _overrides().get(key)


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
