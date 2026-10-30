[English](Settings-reference) · **Español**

# Referencia de ajustes

Todos los ajustes que se cambian en **Administración** (solo el administrador de la instancia), agrupados por sección. Se aplican **sin reiniciar**. Si existe la variable de entorno equivalente (`MIMIRSYNTH_<CLAVE_EN_MAYÚSCULAS>`), hace de **valor por defecto**, y «Restaurar» vuelve a él. La contraseña SMTP se guarda cifrada y no se muestra.

No aparecen aquí porque no son ajustes sueltos: los proveedores OIDC (cada uno con sus propios campos, ver [[Identidad OIDC]]), los motores de IA ([[Proveedores de IA]]), los canales de notificación ([[Notificaciones]]) y las opciones propias de cada brain, como la federación y los secretos ([[Administrar brains y miembros]]).

Esta página se genera a partir del código; ver también [[Visión general de la administración]].

## General

Guía: [[Visión general de la administración]]

| Ajuste | Clave | Por defecto | Rango o valores | Descripción |
|---|---|---|---|---|
| Idioma por defecto | `default_language` | `en` | `es` (Español) / `en` (English) | Idioma de la interfaz y de los correos para quien no haya elegido uno propio en «Mi cuenta». Cada persona puede cambiarlo. |

## Seguridad de cuentas

Guía: [[Seguridad y doble factor]]

| Ajuste | Clave | Por defecto | Rango o valores | Descripción |
|---|---|---|---|---|
| Longitud mínima de contraseña | `password_min_length` | `12` caracteres | 8–64 caracteres | Se aplica al crear o cambiar contraseñas. |
| Intentos fallidos antes de bloquear | `login_max_attempts` | `5` | 3–20 | Tras este número de contraseñas incorrectas seguidas la cuenta se bloquea temporalmente. |
| Duración del bloqueo | `lockout_minutes` | `15` min | 1–1440 min | Tiempo que una cuenta queda bloqueada tras demasiados intentos fallidos. |
| Exigir doble factor | `require_2fa` | `no` | `no` (No) / `yes` (Sí, a todos) | Quien entre con contraseña deberá activar el doble factor (app de autenticación) antes de usar la aplicación. No afecta a quien entra por el proveedor de identidad, que aplica sus propias reglas. |
| Validez de invitaciones y enlaces de recuperación | `invite_days` | `7` días | 1–30 días | Pasado este plazo el enlace deja de funcionar y hay que generar otro. |

## Correo (SMTP)

Guía: [[Correo SMTP]]

| Ajuste | Clave | Por defecto | Rango o valores | Descripción |
|---|---|---|---|---|
| Servidor SMTP | `smtp_host` | — | texto | Necesario para enviar invitaciones y enlaces de recuperación por correo. Sin él, los enlaces se copian desde Administración. |
| Puerto | `smtp_port` | `587` | 1–65535 | Habitual: 587 (STARTTLS), 465 (SSL) o 25. |
| Cifrado | `smtp_security` | `starttls` | `starttls` (STARTTLS) / `ssl` (SSL/TLS) / `none` (Ninguno) | STARTTLS (587), SSL/TLS (465) o ninguno (solo redes de confianza). |
| Usuario | `smtp_user` | — | texto | Vacío si el servidor no pide autenticación. |
| Remitente | `smtp_from` | — | texto | Dirección que aparece como remitente, p. ej. mimirsynth@ejemplo.com. |

## Identidad

Guía: [[Identidad OIDC]]

| Ajuste | Clave | Por defecto | Rango o valores | Descripción |
|---|---|---|---|---|
| URL pública | `public_url` | — | URL | Dirección con la que se accede a la aplicación; se usa para construir la URL de retorno del inicio de sesión (p. ej. https://mimirsynth.ejemplo.com). |
| Administradores de la instancia | `admin_emails` | — | texto | Emails (separados por comas) que entran como administradores la primera vez que inician sesión por OIDC, solo si el proveedor marca el email como verificado. |
| Gestión de la cuenta | `account_url` | — | URL | Página de tu proveedor donde se gestionan contraseña, llaves de acceso y doble factor; se enlaza desde «Mi cuenta». |

## Documentos

Guía: [[Carpetas y límites]]

| Ajuste | Clave | Por defecto | Rango o valores | Descripción |
|---|---|---|---|---|
| Tamaño máximo de un fichero | `doc_max_mb` | `2048` MB | 1–20480 MB | Los ficheros más grandes se rechazan al subirlos o al escanear carpetas. |
| Tamaño de cada parte de una subida | `doc_part_mb` | `64` MB | 1–64 MB | Las subidas se envían por partes de este tamaño (máximo 64). |
| Texto máximo extraído por documento | `doc_text_max_mb` | `100` MB | 1–2048 MB | Un documento cuyo texto supere este tamaño no se indexa. |

## Recuerdo (recall)

Guía: [[Recuerdo e ingesta]]

| Ajuste | Clave | Por defecto | Rango o valores | Descripción |
|---|---|---|---|---|
| Similitud mínima de un pasaje | `doc_min_similarity` | `0.66` | 0–1 | Coseno mínimo para que un pasaje documental entre en el recall. Depende del modelo de embeddings; con nomic-embed-text, 0,66. |
| Pasajes documentales por recall | `doc_passages` | `2` | 0–10 | Máximo de pasajes de documentos que acompañan a los hechos en cada recall. |
| Tiempo máximo de la búsqueda documental | `doc_search_timeout` | `0.6` s | 0.1–10 s | Si tarda más, el recall responde sin documentos. |
| Sincronización del índice de texto | `index_sync_minutes` | `10` min | 0–1440 min | Cada cuántos minutos se copia el texto de los episodios al índice. 0 = desactivada. |

## Ingesta y trabajos

Guía: [[Recuerdo e ingesta]]

| Ajuste | Clave | Por defecto | Rango o valores | Descripción |
|---|---|---|---|---|
| Reintentos de la ingesta | `ingest_retries` | `4` | 1–20 | Intentos cuando el modelo responde con límite de tasa o un error transitorio. |
| Lote al cambiar de modelo de embeddings | `reindex_batch` | `64` textos | 1–512 textos | Textos por lote al recalcular los vectores con otro modelo. Más pequeño reparte mejor la carga en el proveedor. |
| Pausa entre lotes al cambiar de modelo | `reindex_pause` | `0` s | 0–600 s | Segundos de espera entre lotes para respetar el límite de tasa del proveedor. Con un 429 se espera además lo que indique Retry-After. |
| Espera del cambio de modelo | `reindex_switch_wait` | `60` s | 1–3600 s | Segundos que el cambio de modelo de embeddings espera a que terminen las escrituras de vectores en curso (ingestas, indexaciones). Si no terminan, el cambio se aplaza y se reintenta; las escrituras nunca se cortan. |
| Avisar de un cambio de modelo parado | `reindex_orphan_hours` | `24` h | 0–8760 h | Horas que un relleno de embeddings puede estar fallido o parado, con sus vectores sombra ocupando memoria, antes de avisar (evento «reindex.orphan»). |
| Conservar trabajos terminados | `jobs_keep_days` | `60` días | 1–3650 días | Pasado este plazo se borran los trabajos terminados, fallidos y cancelados. |
| Conservar reescaneos programados | `jobs_keep_scheduled_days` | `7` días | 1–365 días | Los reescaneos automáticos sin incidencias son ruido (uno cada pocos minutos): se borran antes. |

## Notificaciones

Guía: [[Notificaciones]]

| Ajuste | Clave | Por defecto | Rango o valores | Descripción |
|---|---|---|---|---|
| Aviso repetido | `notify_cooldown_minutes` | `60` min | 1–10080 min | Mientras un problema siga abierto no se vuelve a avisar por los canales hasta pasado este plazo (en la campana solo suma una repetición). Un problema resuelto avisa de la recuperación. |
| Silencio desde | `notify_quiet_start` | — | texto | Hora (HH:MM) a partir de la cual solo se envían los avisos críticos; el resto espera al final del silencio. Vacío = sin horas de silencio. |
| Silencio hasta | `notify_quiet_end` | — | texto | Hora (HH:MM) en que termina el silencio. Se usa la hora del servidor. |
| Comprobar el estado cada | `notify_health_minutes` | `10` min | 0–1440 min | Cada cuántos minutos se comprueba que el grafo y los modelos de IA responden (un modelo con clave de pago recibe una llamada mínima). 0 = no comprobar. |
| Fallos seguidos para avisar | `notify_health_failures` | `2` | 1–10 | Cuántas comprobaciones seguidas deben fallar antes de avisar de que el grafo o un modelo no responde. Con 2, un error puntual de un proveedor no genera aviso. Con 1 se avisa al primer fallo. |
| Avisar de versiones nuevas | `notify_update_check` | `no` | `no` (No) / `yes` (Sí) | Una vez al día consulta en GitHub si hay una versión más reciente. Es la única conexión de salida que hace la instancia por su cuenta; está desactivada por defecto. |
| Prohibir redes privadas | `notify_block_private` | `no` | `no` (No) / `yes` (Sí) | Impide que los canales apunten a direcciones privadas o locales (protege de que se use un canal para llegar a servicios internos). Déjalo en «No» si tu ntfy o Gotify están en la red local. |
| Conservar avisos | `notify_keep_days` | `30` días | 1–3650 días | Pasado este plazo se borran los avisos y su historial de envíos. |
## Cómo se guardan
- Un ajuste solo se guarda si **difiere** de su valor por defecto.
- Los cambios de un ajuste quedan en la [[Auditoría]] (`settings.set`, `settings.reset`, `settings.secret`).
- Los secretos se cifran con una clave derivada de `MIMIRSYNTH_SESSION_SECRET`: si cambias ese secreto hay que volver a introducirlos.
