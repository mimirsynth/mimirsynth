[English](Notifications) · **Español**

# Notificaciones

MimirSynth avisa cuando algo necesita atención: un modelo que deja de responder, una ingesta que falla tras sus reintentos, una fuente de documentos que no se puede sincronizar, una versión nueva. Los avisos aparecen siempre en la **campana**; el administrador de la instancia puede además enviarlos a **canales** (Telegram, ntfy, Gotify, un webhook o correo).

Los avisos solo llevan metadatos (qué falló, dónde, cuántas veces, un error recortado), **nunca el texto de tus memorias**.

## La campana
**Notificaciones**, abajo en la barra lateral, abre la lista de avisos que puedes ver. A su lado, un contador muestra los no leídos (en rojo si alguno es crítico) o, cuando está todo leído, cuántos problemas siguen abiertos.
- **Los administradores de la instancia** ven todos los avisos.
- **Los curadores y administradores de un brain** ven los avisos de ese brain (ingestas fallidas, errores de fuentes, contradicciones, consultas de referencia que empeoran), y nada de la instancia.
- Cada aviso muestra su severidad (**Crítico**, **Aviso** o **Información**), si es **nuevo** y si el problema sigue **abierto** o ya está **resuelto**. Un problema que se repite cuenta una sola vez («3 veces»).
- Filtra **Todas** o **Sin leer**, y **Marcar todo como leído**.

## Eventos
| Evento | Severidad | Cuándo |
|---|---|---|
| `model.unavailable` | crítico | El motor LLM, de embeddings o decisor por defecto no responde a la comprobación periódica |
| `graph.down` | crítico | El grafo (FalkorDB) no responde |
| `ingest.failed` | aviso | Una propuesta aprobada no se pudo ingerir tras sus reintentos |
| `job.failed` | aviso | Cualquier otro trabajo en segundo plano ha fallado |
| `docsource.error` | aviso | Una fuente de documentos no se pudo sincronizar |
| `security.lockout` | aviso | Una cuenta se ha bloqueado tras demasiados intentos fallidos |
| `reindex.orphan` | aviso | Un cambio de modelo de embeddings lleva fallido o parado más horas de las configuradas, con sus vectores sombra ocupando memoria ([[Proveedores de IA]]) |
| `refquery.regressed` | aviso | Tras un cambio de modelo de embeddings, las consultas de referencia de un brain dejan de encontrar elementos esperados o muestran falsos positivos nuevos. Si no había una ejecución anterior con la que comparar, lo dice, como información |
| `token.expiring` | información | Un token de API caduca en 7 días o menos; se avisa una vez por token, con su nombre y su prefijo, nunca el token. Un token rotado no se avisa ([[Conectar agentes]]) |
| `conflicts.found` | información | Un brain tiene hechos vigentes que se contradicen en una relación de un solo valor; se comprueba una vez al día ([[Vocabulario]]) |
| `update.available` | información | Hay una versión más reciente (solo si lo activas, ver abajo) |

## Canales
**Administración → Notificaciones → Canales** (administrador de la instancia). **Añadir canal**, con un **Nombre** y un **Tipo**:

| Tipo | Qué necesitas |
|---|---|
| **Telegram** | El **Token del bot** (de @BotFather) y el identificador del **Chat**; el bot debe estar dentro (los grupos empiezan por `-100…`). Opcionalmente, el **Tema del grupo** y un **Servidor de la API** propio |
| **ntfy** | **URL del servidor** (por defecto `https://ntfy.sh`), **Tema** y, si está protegido, un **Token de acceso**. En un servidor público cualquiera que conozca el tema puede leerlo: usa un nombre difícil de adivinar o un servidor propio |
| **Gotify** | **URL del servidor** y un **Token de la aplicación** |
| **Webhook** | Una URL. Con una **Clave de firma HMAC**, cada petición lleva `X-MimirSynth-Signature: sha256=<HMAC-SHA256 del cuerpo>` para que el receptor compruebe que viene de esta instancia |
| **Correo** | **Destinatarios**, separados por comas. Usa el servidor de [[Correo SMTP]] |

Cada canal tiene además:
- **Severidad mínima:** por debajo de ella no se envía nada por este canal.
- **Eventos:** cuáles recibe; sin ninguno marcado, los recibe todos.
- **Canal activo.**

**Enviar prueba** manda un mensaje de prueba al momento y muestra el resultado. Los tokens y las claves se guardan cifrados y no se vuelven a mostrar (al editar, deja el campo vacío para conservarlos). La lista muestra el último envío de cada canal y si salió bien.

El cuerpo del webhook es un JSON con `event`, `kind` (`alert` o `recovery`), `severity`, `title`, `body`, `brain`, `count`, `instance` y `ts`. Más en [docs/es/NOTIFICATIONS.md](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/NOTIFICATIONS.md).

## Contra el ruido
- **Agrupación.** Mientras un problema sigue abierto, el mismo evento suma a un contador en lugar de crear un aviso nuevo, y los canales solo vuelven a recibirlo pasado el **Aviso repetido** (60 minutos por defecto).
- **Recuperaciones.** Cuando el problema se resuelve, los canales que recibieron el aviso reciben un mensaje de «Recuperado».
- **Severidad y eventos** por canal.
- **Horas de silencio.** Entre **Silencio desde** y **Silencio hasta** (hora del servidor) solo salen los avisos críticos; el resto espera al final del silencio.
- **Reintentos.** Un envío fallido se reintenta con esperas crecientes (1 min, 5 min, 30 min, 2 h, 12 h). Tras el último intento queda como fallido. El **Historial de envíos** lista cada envío con su resultado (filtrable por estado) y permite **Reintentar** a mano uno fallido.

## Lo que la instancia comprueba sola
Los ajustes del final de la sección:

| Ajuste | Por defecto | Qué hace |
|---|---|---|
| **Aviso repetido** | 60 min | Espera antes de volver a anunciar por los canales un problema que sigue abierto |
| **Silencio desde** / **Silencio hasta** | vacío | Horas de silencio (HH:MM). Vacío = ninguna |
| **Comprobar el estado cada** | 10 min | Cada cuánto se comprueban el grafo y los motores de IA por defecto. 0 = no comprobar. Un modelo con clave de pago recibe una llamada mínima en cada comprobación |
| **Fallos seguidos para avisar** | 2 | Un error puntual de un proveedor no genera aviso. 1 = avisar al primer fallo |
| **Avisar de versiones nuevas** | No | Una vez al día pregunta a GitHub si hay una versión más reciente. Es la única conexión de salida que hace la instancia por su cuenta |
| **Prohibir redes privadas** | No | Rechaza canales que apunten a direcciones privadas o locales. Déjalo en «No» si tu ntfy o tu Gotify están en la red local |
| **Conservar avisos** | 30 días | Pasado ese plazo se borran los avisos y su historial de envíos |

Los enlaces a la dirección de metadatos de la nube se rechazan siempre, y no se siguen redirecciones.

> PostgreSQL no puede avisar de su propia caída (no habría dónde guardar el aviso). Vigílalo con un monitor externo apuntado a `GET /api/health`, que distingue «aplicación caída» de «aplicación viva, base de datos caída». Ver [Vigilar la instancia](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/INSTALL.md#vigilar-la-instancia).

Los textos de los avisos se guardan en el idioma de la instancia al generarse. Crear, cambiar, borrar y probar un canal queda en la [[Auditoría]].
