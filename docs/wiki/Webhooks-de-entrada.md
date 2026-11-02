[English](Incoming-webhooks) · **Español**

# Webhooks de entrada

Lo que pasa en la infraestructura (una alerta, un despliegue, un pipeline, una copia fallida) es justo la memoria episódica que luego se busca: «¿qué pasó con X la semana pasada?», «¿cuándo se actualizó Y?». Un **webhook de entrada** deja que una herramienta mande esos eventos a un brain, donde entran como **propuestas** redactadas como «qué pasó y cuándo». Los administradores del brain los gestionan en Administración → Acceso al brain → **Webhooks de entrada**.

## Plantillas
Cada webhook tiene una plantilla que lee el JSON de su emisor:

| Plantilla | Emisor | Qué se convierte en memoria |
|---|---|---|
| **Alertmanager** | Prometheus Alertmanager, `webhook_configs` | Cada alerta del grupo: al dispararse se abre y al resolverse se cierra |
| **CheckMK** | El script de notificación de `integrations/checkmk` | `PROBLEM` abre una alerta y `RECOVERY` la cierra; los reconocimientos, las paradas programadas y el flapping se quedan fuera |
| **Uptime Kuma** | Notificación «Webhook», cuerpo JSON | Caído abre una alerta y activo la cierra |
| **Proxmox VE** | Destino de notificación «Webhook» (8.3 o posterior), con el cuerpo de abajo | Cada notificación, como evento (una copia, una replicación, un fencing) |
| **GitHub Actions** | Webhook del repositorio, eventos `workflow_run` y `deployment_status` | Una ejecución terminada o un estado de despliegue final |
| **GitLab CI** | Webhook del proyecto, eventos de pipeline y de despliegue | Un pipeline o un despliegue terminado (success, failed, canceled) |
| **Genérica** | Cualquier JSON | Título y texto con huecos `{{ruta}}`; opcionalmente, las rutas de la fecha, el estado y la huella |

Un cuerpo que no anuncia nada terminado (un pipeline aún en marcha, un ping de GitHub) se acepta y se ignora.

Para **Proxmox VE**, pon como cuerpo del webhook:
```json
{"title": "{{ escape title }}", "message": "{{ escape message }}", "severity": "{{ severity }}", "timestamp": {{ timestamp }}, "fields": {{ json fields }}}
```

La plantilla **Genérica** admite huecos `{{campo.subcampo}}` (las listas, con su número, como `alerts.0.labels.alertname`). Con una ruta en **Estado**, los valores `resolved`, `ok`, `up` o `recovery` cierran la alerta y cualquier otro la abre; sin ella, cada petición es un evento.

**Probar la plantilla**, en el diálogo del webhook: pega un JSON de ejemplo y verás los eventos que sacaría, sin crear nada.

## Dirección y secreto
Cada webhook tiene su dirección, `https://<instancia>/api/brains/<slug>/hooks/<clave>`, y un secreto que se muestra **una sola vez** al crearlo (y otra al pulsar **Nuevo secreto**, que deja sin efecto el anterior al momento). El emisor demuestra que lo tiene de una de estas formas:
- una **firma HMAC-SHA256** del cuerpo en `X-Hub-Signature-256` o `X-MimirSynth-Signature`, como `sha256=<hex>` (así firma GitHub, y también el script de CheckMK);
- el propio secreto en `Authorization: Bearer <secreto>`, `X-Gitlab-Token` (el «Secret token» de GitLab) o `X-Webhook-Token`.

Las comparaciones son de tiempo constante. Una dirección desconocida, un webhook desactivado o un secreto incorrecto responden igual, `401`, y no crean nada. El cuerpo tiene un máximo de 256 KB y tiene que ser JSON.

## De un evento a una propuesta
- Cada evento se convierte en una propuesta del brain, con el webhook como origen, y pasa por el detector de [[Secretos]] y después por el decisor y los curadores como cualquier otra ([[Propuestas]]). Un webhook no invalida nada: la ontología de infraestructura ya tiene los tipos **Incident** y **Event**, y son el decisor y los curadores quienes deciden qué significa cada episodio.
- **Agrupación.** Una alerta que se sigue disparando (con la misma huella) no crea una propuesta por aviso: se cuentan las repeticiones. Si se resuelve dentro de *Agrupar las alertas de un webhook* (15 minutos por defecto), deja **una sola** propuesta con su inicio, su fin y el número de avisos. Si sigue activa pasado ese plazo (contado desde el primer aviso recibido), una propuesta dice que está activa y otra, cuándo se resolvió.
- **Webhooks de confianza.** Marcar un webhook como de confianza aprueba sus propuestas sin revisión. Úsalo solo con emisores fiables: el tope diario sigue valiendo, y una propuesta en la que el detector de secretos marque algo va siempre a revisión.

## Límites
- **Peticiones por minuto** de cada webhook (60 por defecto): pasado el límite responde `429` y el emisor reintenta.
- **Propuestas al día** de cada webhook (200 por defecto): lo que pase del tope queda en el registro como «sobre el tope», sin proponerse, y el aviso `webhook.capped` avisa una vez al día ([[Notificaciones]]). Las propuestas son llamadas al motor de IA: así se protege el límite del proveedor y el [[Consumo de IA]] del brain.

## El registro
**Registro** enseña lo que ha recibido cada webhook: el título, si fue una alerta o un evento, cuántos avisos, desde cuándo y hasta cuándo, su estado y las propuestas que se crearon. **Del cuerpo recibido no se guarda nada.** El registro se olvida a los 90 días. La lista enseña además cuántas peticiones llegaron, cuántas se rechazaron y el último problema (un secreto incorrecto, un cuerpo que no era JSON, una petición que la plantilla no entendió).

## API
`POST /api/brains/{slug}/hooks/{clave}` responde `202` con el número de eventos y qué pasó con cada uno (`open`, `grouped`, `resolved`, `proposed`, `capped` o `blocked`). La gestión, para administradores del brain: `GET/POST /webhooks`, `PUT/DELETE /webhooks/{id}`, `POST /webhooks/{id}/rotate`, `GET /webhooks/{id}/events` y `POST /webhooks/preview`. Ver [[API REST]].
