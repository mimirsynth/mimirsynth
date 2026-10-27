# Notificaciones

MimirSynth avisa a los administradores cuando algo necesita atención: un modelo que deja de responder, una ingesta que falla tras sus reintentos, una fuente de documentos que no se puede sincronizar, una versión nueva. Los avisos aparecen siempre en la **campana** de la interfaz y, opcionalmente, se envían también por **canales**.

## La campana

La campana (barra lateral → Notificaciones) lista los avisos que puedes ver y cuántos tienes sin leer.

- Los administradores de la instancia ven todos los avisos.
- Un curador o administrador de un brain ve los avisos de ese brain (ingestas fallidas, errores de fuentes), y ninguno de la instancia.
- Un problema que se repite cuenta una sola vez («3 veces») y se marca como **resuelto** cuando desaparece.

## Eventos

| Evento | Severidad por defecto | Cuándo |
|---|---|---|
| `model.unavailable` | crítico | El motor LLM, de embeddings o decisor por defecto no responde a la comprobación periódica |
| `graph.down` | crítico | FalkorDB no responde |
| `ingest.failed` | aviso | Una propuesta aprobada no se pudo ingerir tras sus reintentos |
| `job.failed` | aviso | Cualquier otro trabajo en segundo plano ha fallado |
| `docsource.error` | aviso | Una fuente de documentos no se pudo sincronizar |
| `security.lockout` | aviso | Una cuenta se ha bloqueado por demasiados intentos fallidos |
| `reindex.orphan` | aviso | Un cambio de modelo de embeddings (relleno en sombra) lleva fallido o parado más horas de las configuradas, con sus vectores sombra ocupando memoria |
| `update.available` | información | Hay una versión más reciente (opcional, ver más abajo) |

Los mensajes llevan metadatos (qué ha fallado, dónde, cuántas veces, un error recortado), **nunca el texto de las memorias**.

## Canales

Administración → Notificaciones → Canales. Cada canal elige una **severidad mínima** y, si quieres, qué eventos recibe (ninguno marcado = todos). **Enviar prueba** manda un mensaje al momento y muestra el resultado.

| Tipo | Qué necesitas |
|---|---|
| **Telegram** | El token del bot (de @BotFather) y el identificador del chat; el bot debe estar dentro. Opcionalmente, el tema del grupo (`thread_id`) y un servidor de API propio |
| **ntfy** | URL del servidor (por defecto `https://ntfy.sh`), tema y, si está protegido, un token de acceso |
| **Gotify** | URL del servidor y un token de aplicación |
| **Webhook** | Una URL. Con una clave de firma, cada petición lleva `X-MimirSynth-Signature: sha256=<HMAC-SHA256 del cuerpo>` para que el receptor compruebe que viene de esta instancia |
| **Correo** | Destinatarios. Usa el servidor SMTP de Administración → Correo |

Cuerpo del webhook:

```json
{"event": "model.unavailable", "kind": "alert", "severity": "critical", "title": "…", "body": "…", "brain": null, "count": 1, "instance": "MimirSynth · https://…", "ts": "2026-10-26T12:00:00+00:00"}
```

`kind` es `alert` o `recovery`. Los tokens y claves se guardan cifrados y no se vuelven a mostrar.

## Contra el ruido

- **Agrupación.** Mientras un problema siga abierto, el mismo evento y clave suman a un contador en lugar de crear un aviso nuevo, y los canales solo se avisan de nuevo pasado el *aviso repetido* (por defecto 60 minutos).
- **Recuperación.** Cuando el problema desaparece recibes un mensaje «Recuperado» en los canales que recibieron el aviso.
- **Severidad y eventos** por canal.
- **Horas de silencio.** Entre las dos horas que fijes en Administración solo se envían los avisos críticos; el resto espera al final del silencio.
- **Reintentos.** Un envío fallido se reintenta con esperas crecientes (1 min, 5 min, 30 min, 2 h, 12 h). Tras el último intento se marca como fallido; aparece en el historial de envíos, donde un administrador puede reintentarlo a mano.

## Comprobaciones de la instancia

- Cada *N* minutos (por defecto 10; 0 = no) comprueba FalkorDB y los motores LLM, de embeddings y decisor por defecto. Un modelo con clave de pago recibe una llamada mínima por comprobación. Solo se avisa tras **2 fallos seguidos** (ajuste «Fallos seguidos para avisar»; 1 = al primero), así que un 500 o un timeout puntual de un proveedor no genera aviso; la recuperación borra la cuenta.
- Las **versiones nuevas** se consultan una vez al día en la API de releases de GitHub, **solo si lo activas**. Es la única conexión de salida que hace la instancia por su cuenta.
- PostgreSQL no puede avisar de su propia caída (no habría dónde guardar el aviso): vigílalo con un monitor externo.

## Seguridad

- Solo los administradores de la instancia crean canales, y la URL es cosa suya. Aun así, los enlaces a la dirección de metadatos de la nube (169.254.0.0/16) se rechazan siempre.
- **Prohibir redes privadas** (desactivado por defecto, porque ntfy y Gotify suelen estar en la red local) rechaza también direcciones privadas y locales.
- No se siguen redirecciones.
- Los textos de los avisos se guardan en el idioma de la instancia en el momento de generarse.

## API

`GET /api/notifications` (la campana), `GET /api/notifications/summary`, `POST /api/notifications/read`; para administradores de la instancia: `/api/notifications/channels` (CRUD, `POST /{id}/test`), `/api/notifications/deliveries` y `POST /deliveries/{id}/retry`.
