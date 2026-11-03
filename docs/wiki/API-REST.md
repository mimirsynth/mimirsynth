[English](REST-API) · **Español**

# API REST

Toda la funcionalidad de la interfaz está disponible por una API REST JSON bajo `/api`. Con la aplicación en marcha, la **documentación interactiva (OpenAPI)** está en `https://tu-servidor/docs`, con todos los parámetros y esquemas. Esta página es el mapa.

## Autenticación
- **Agentes y scripts:** cabecera `Authorization: Bearer mst_…` con un [token de API](Conectar-agentes). Un token está acotado a **un brain** y a un rol (máximo curador); no puede usar las rutas de administración de la instancia.
- **La interfaz web:** cookie de sesión firmada tras iniciar sesión.
- **MCP:** `POST /api/brains/{slug}/mcp` es el [servidor MCP](Conectar-agentes) del brain (HTTP «streamable», sin estado). Admite **solo tokens de API**, nunca la cookie de sesión, y rechaza orígenes de navegador distintos del de la instancia.

Errores habituales: `401` (no autenticado o token inválido), `403` (rol insuficiente), `404` (no existe o no tienes acceso), `409` (conflicto, p. ej. duplicado), `422` (datos no válidos, o una propuesta bloqueada por llevar un secreto), `429` (demasiados intentos), `503` (en `/health`: la base de datos o el grafo están caídos).

<!-- generated:start (scripts/wiki_reference.py writes this part from the code: do not edit it by hand) -->
## Rutas por brain
Todas cuelgan de `/api/brains/{slug}/…`. El rol es el **mínimo** que piden sus dependencias; unas pocas rutas comprueban algo más, ver las notas de abajo.

| Área | Rutas | Rol |
|---|---|---|
| **Recall** | `POST /recall` · `POST /mcp` · `POST /recall/{rid}/ratings` · `POST /answer` | lector |
| | `GET /recall/quality` | curador |
| | `PUT /recall/settings` | administrador |
| **Índice de texto** | `GET /index/status` | lector |
| | `POST /index/sync` | curador |
| **Resumen** | `GET /overview` · `GET /overview/activity` | lector |
| **Episodios** | `GET /episodes/sources` · `GET /episodes` · `GET /episodes/{uuid}` | lector |
| **Hechos** | `GET /facts/relations` · `GET /facts` · `GET /timeline` · `GET /entities/{uuid}` · `GET /entities` | lector |
| | `PATCH/DELETE /facts/{uuid}` · `POST /facts/{uuid}/invalidate` · `POST /facts/{uuid}/reactivate` · `PUT /entities/{uuid}/type` | curador |
| **Grafo y consulta** | `GET /graph` · `POST /query` | lector |
| **Propuestas** | `POST /proposals/corrections` · `GET/POST /proposals` · `GET /proposals/counts` · `GET /proposals/{pid}` | colaborador |
| | `POST /proposals/{pid}/reactivate` · `POST /proposals/{pid}/approve` · `POST /proposals/{pid}/ingest` · `POST /proposals/{pid}/reject` | curador |
| **Documentos** | `GET /docs/sources` · `GET /docs` · `GET /docs/search` · `GET /docs/{doc_id}` · `GET /docs/{doc_id}/text` · `GET /docs/{doc_id}/file` · `GET /docs/{doc_id}/context` · `GET /docs/{doc_id}/entities` · `GET /docs/mentions` | lector |
| | `DELETE /docs/{doc_id}` · `POST /docs/{doc_id}/reindex` · `POST /docs/uploads` · `PUT /docs/uploads/{uid}/parts/{n}` · `DELETE /docs/uploads/{uid}` · `POST /docs/uploads/{uid}/complete` · `POST /docs/{doc_id}/promote` | colaborador |
| | `POST /docs/duplicates` · `GET /docs/roots` · `POST /docs/sources` · `PATCH/DELETE /docs/sources/{sid}` · `POST /docs/sources/{sid}/scan` · `GET /docs/wiki/adapters` · `POST /docs/wiki/collections` · `GET /docs/sources/{sid}/wiki/collections` · `POST /docs/sources/wiki` | administrador |
| **Vocabulario** | `GET /vocabulary` · `GET /vocab/aliases` · `GET /vocab/types` · `GET /vocab/types/{name}/preview` · `POST /vocab/duplicates/preview` · `GET /ontology` | lector |
| | `POST /vocab/ops/{oid}/revert` | curador |
| | `POST /vocab/aliases` · `DELETE /vocab/aliases/{aid}` · `POST /vocab/types` · `PUT/DELETE /vocab/types/{name}` · `POST /vocab/types/{name}/move` · `POST /vocab/relations` · `PUT/DELETE /vocab/relations/{name}` · `PUT /vocab/map` · `PUT /vocab/instructions` · `POST /vocab/duplicates/merge` · `POST/DELETE /vocab/duplicates/ignore` · `GET /retype` · `POST /retype/scan` · `POST /retype/apply` · `POST /retype/reject` · `POST /retype/{sid}/apply-as` · `POST /retype/{sid}/revert` · `GET/POST /vocab/entity-aliases` · `PUT /ontology` · `POST /ontology/preset/{name}` | administrador |
| **Necesita tu atención** | `GET /attention` | curador |
| **Lo que ha cambiado** | `GET /changes` | curador |
| **Hechos a revisar** | `GET /review/stale` · `POST /review/stale/{uuid}/confirm` | curador |
| **Contradicciones** | `GET /conflicts` · `POST /conflicts/dismiss` · `DELETE /conflicts/dismiss/{did}` · `POST /conflicts/resolve` | curador |
| **Consultas de referencia** | `GET/POST /refqueries` · `PATCH/DELETE /refqueries/{qid}` · `GET /refqueries/export` · `POST /refqueries/import` · `GET/POST /refqueries/runs` · `GET /refqueries/runs/{rid}` | curador |
| **Federación** | `GET /grants` | lector |
| | `POST /grants` · `PATCH/DELETE /grants/{gid}` | administrador |
| **Trabajos** | `GET /jobs` · `GET /jobs/summary` · `GET /jobs/{jid}` | lector |
| | `POST /jobs/{jid}/cancel` · `POST /jobs/{jid}/retry` | curador |
| **Miembros** | `GET/PUT /members` · `DELETE /members/{user_id}` | administrador |
| **Tokens** | `GET/POST /tokens` · `POST /tokens/{token_id}/rotate` · `DELETE /tokens/{token_id}` | lector |
| **El propio brain** | `PATCH /api/brains/{slug}` · `GET /secrets/scan` | administrador |
| | `POST /delete` | propietario |
| **Consumo de IA** | `GET /ai-usage` · `PUT /ai-budget` | administrador |
| **Webhooks de entrada** | `GET/POST /webhooks` · `PUT/DELETE /webhooks/{hid}` · `POST /webhooks/{hid}/rotate` · `GET /webhooks/{hid}/events` · `POST /webhooks/preview` | administrador |
| | `POST /hooks/{key}` | el secreto del webhook |
| **Retención** | `GET/PUT /retention` · `POST /retention/run` | propietario |
| **Exportar** | `GET/POST /exports` · `GET /exports/{jid}/download` | administrador |

## Rutas de cuenta y de instancia
Cuelgan de `/api/…`.

| Área | Rutas | Acceso |
|---|---|---|
| **Acceso** | `GET /auth/options` · `POST /auth/setup` · `GET/POST /auth/login` · `POST /auth/mfa` · `GET /auth/token/{raw}` · `POST /auth/accept` · `POST /auth/forgot` · `GET /auth/login/{slug}` · `GET /auth/callback/{slug}` · `GET /auth/callback` · `POST /auth/logout` · `POST /auth/passkey/options` · `POST /auth/passkey/login` · `POST /auth/passkey/mfa/options` · `POST /auth/passkey/mfa` | pública |
| **Mi cuenta** | `POST /me/password` · `GET /me` · `GET /me/identities` · `DELETE /me/identities/{iid}` · `GET /me/identities/link/{slug}` · `GET/PATCH /me/profile` · `POST/DELETE /me/avatar` · `GET /users/{uid}/avatar` · `GET /me/tokens` · `GET /me/activity` · `POST /me/sessions/revoke-others` · `GET /me/2fa` · `POST /me/2fa/begin` · `POST /me/2fa/enable` · `POST /me/2fa/disable` · `POST /me/2fa/recovery` · `GET /me/passkeys` · `POST /me/passkeys/begin` · `POST /me/passkeys/finish` · `POST /me/passkeys/{pid}/delete` · `PATCH /me/passkeys/{pid}` · `GET/PUT /me/digest` · `GET /me/digest/preview` | con sesión |
| **Buscar en todos los brains** | `POST /search` | con sesión |
| **Notificaciones** | `GET /notifications` · `GET /notifications/summary` · `POST /notifications/read` | con sesión |
| | `GET /notifications/catalog` · `GET/POST /notifications/channels` · `PUT/DELETE /notifications/channels/{cid}` · `POST /notifications/channels/{cid}/test` · `GET /notifications/deliveries` · `POST /notifications/deliveries/{did}/retry` | administrador de la instancia |
| **Brains** | `GET /brains` | con sesión |
| | `POST /brains` | administrador de la instancia |
| **Consumo de IA** | `GET /ai-usage` · `PUT/DELETE /ai-usage/prices` | administrador de la instancia |
| **Importar un brain** | `POST /brain-imports/uploads` · `PUT /brain-imports/uploads/{uid}/parts/{n}` · `DELETE /brain-imports/uploads/{uid}` · `POST /brain-imports/uploads/{uid}/complete` · `GET/POST /brain-imports` | administrador de la instancia |
| **Administración** | `GET /ai-status` | con sesión |
| | `GET /users` · `GET /audit` · `GET/POST /doc-roots` · `DELETE /doc-roots/{rid}` · `POST /llm-engines/models` · `GET/POST /llm-engines` · `PATCH/DELETE /llm-engines/{eid}` · `POST /llm-engines/{eid}/default` · `POST /llm-engines/{eid}/test` · `GET/POST /decision-engines` · `PATCH/DELETE /decision-engines/{eid}` · `POST /decision-engines/{eid}/default` · `POST /decision-engines/{eid}/test` · `GET/POST /embedding-engines` · `PATCH/DELETE /embedding-engines/{eid}` · `POST /embedding-engines/{eid}/default` · `POST /embedding-engines/{eid}/test` · `GET /settings` · `POST /settings/smtp/test` · `PUT /settings/secret/{key}` · `PUT/DELETE /settings/{key}` · `GET/POST /oidc-providers` · `PUT/DELETE /oidc-providers/{slug}` · `POST /oidc-providers/{slug}/test` · `GET/POST /admin/users` · `GET/PATCH/DELETE /admin/users/{uid}` · `POST /admin/users/{uid}/link` · `POST /admin/users/{uid}/logout` · `POST /admin/users/{uid}/unlock` · `POST /admin/users/{uid}/mfa/reset` · `PUT /admin/users/{uid}/memberships` · `GET /admin/metrics` · `POST/DELETE /admin/metrics/token` | administrador de la instancia |
| **Cambio de modelo de embeddings** | `GET /embedding-engines/reindex` · `GET /embedding-engines/{eid}/reindex/estimate` · `POST /embedding-engines/{eid}/reindex` · `POST /embedding-engines/reindex/{jid}/cancel` · `POST /embedding-engines/reindex/{jid}/retry` · `POST /embedding-engines/reindex/discard` · `POST /embedding-engines/reindex/switch` | administrador de la instancia |
| **Públicas** | `GET /config` · `GET /health` | pública |
<!-- generated:end -->

## Notas sobre algunas rutas
- **Rutas que comprueban algo más que su rol:** `POST /tokens/{id}/rotate` es solo para el dueño del token, y `/tokens` y `POST /api/search` solo funcionan desde una sesión, nunca con un token de API (`403`); el rol de un token nunca supera el tuyo. Un colaborador solo ve sus propias propuestas. Conectar una wiki y cambiar sus colecciones o su clave necesita al administrador de la instancia. `PATCH /api/brains/{slug}` solo cambia el grafo si lo pide el administrador de la instancia.
- **`POST /recall`** devuelve un `recall_id`; `POST /recall/{recall_id}/ratings` valora lo que devolvió: `kind` (`fact`, `chunk` o `doc`), `id`, `rating` (`useful`, `irrelevant` o `incorrect`) y una `note` opcional. `GET /recall/quality?days=30` suma las valoraciones, y `PUT /recall/settings` (`keep_query_text`) decide si se guarda el texto de las consultas.
- **`PUT /entities/{uuid}/type`** recibe `{"type": …}`, un tipo de la ontología del brain; se deshace desde el historial del vocabulario. `GET /entities?q=` busca entidades por nombre.
- **`POST /query`** ejecuta Cypher de solo lectura.
- **Subidas:** `POST /docs/uploads`, después cada parte con `PUT /docs/uploads/{uid}/parts/{n}` y `POST …/complete`. Las fuentes wiki están en `/docs/sources` y `/docs/wiki`.
- **Las colecciones de una fuente wiki** (administrador de la instancia): `GET /docs/sources/{id}/wiki/collections` devuelve las disponibles, las seleccionadas (`selected`) y los documentos indexados (`documents`) por colección. `PATCH /docs/sources/{id}` con `collection_ids` las cambia: añadir lanza un escaneo y devuelve su `job`; quitar responde `409` con el número de documentos hasta que `confirm_removed` lo repite, y entonces retira solo esos del índice. Solo se retiran las páginas cuya colección se conoce; las páginas de la wiki no se tocan nunca. Ver [[Conocimiento]].
- **`GET /attention`** dice lo que espera una decisión: `proposals`, `corrections`, `duplicates`, `conflicts`, `stale`, `refqueries`, y `retype` para administradores; `null` si un contador no se pudo calcular. Se guarda un minuto y lo descarta cualquier escritura correcta en el brain; `?fresh=true` lo recalcula.
- **`GET /changes?days=7`** (1–31): `facts_new`, `facts_gone`, `docs_new`, `proposals_new` y `proposals_decided` del periodo; `null` si no se pudo contar el grafo.
- **`GET /review/stale`** lista los hechos vigentes que han superado la vida útil de su relación, los más antiguos primero; `…/confirm` confirma uno.
- **`/tokens`:** `scopes` (`recall`, `documents`, `propose`) y `days` hasta que caduca (vacío para nunca). `POST /tokens/{id}/rotate` recibe `grace_hours` (0–168, por defecto 24).
- **`PATCH /api/brains/{slug}`** cambia el nombre, la descripción, el slug y la política de secretos. `POST /api/brains/{slug}/delete` borra el brain.
- **Consumo de IA:** `GET /ai-usage?days=30` y `PUT /ai-budget` (`limit`, `unit`: `tokens` o `cost`, `pause`) en un brain; en la instancia, `GET /api/ai-usage?days=30` (por brain y motor, con las peticiones por minuto de ahora) y `PUT/DELETE /api/ai-usage/prices` (precio por millón de tokens de un modelo). Ver [[Consumo de IA]].
- **Webhooks de entrada:** `POST /hooks/{key}` no lleva sesión: el secreto del webhook es la credencial, como firma HMAC o en una cabecera, y responde `202` con qué pasó con cada evento. `POST /webhooks/{id}/rotate` da un secreto nuevo, que se muestra una vez; `POST /webhooks/preview` recibe `template`, `config`, `body` y `event`. Ver [[Webhooks de entrada]].
- **`/retention`:** `rejected_days` y `jobs_days`, en días (vacío para el de la instancia, 0 para siempre); `POST /retention/run` purga ahora.
- **`POST /exports`** recibe `vectors` y una `password` opcional; `GET /exports/{id}/download` funciona una vez (`410` cuando ya se descargó o caducó). Ver [[Exportar un brain]].
- **`POST /api/search`** `{query, facts, chunks}`: el recall en cada brain que la persona puede leer, agrupado por brain con `state` `ok`, `timeout` o `error`.
- **Importar un brain:** `POST /api/brain-imports/uploads`, sus partes y `…/complete` (que devuelve el resumen del manifiesto), y después `POST /api/brain-imports` (`upload_id`, `slug`, `name`, `mode`, `password` opcional, `dump` para la restauración rápida). Ver [[Importar un brain]].
- **Inicio de sesión:** `GET /api/auth/login/{proveedor}` y `/api/auth/callback/{proveedor}` son el inicio de sesión por OIDC.
- **`GET /api/ai-status`** (`?check=true` prueba todos los motores y devuelve `model` y `ms`).
- **Cambio de modelo de embeddings:** `GET /api/embedding-engines/reindex` es el estado del relleno en sombra (`orphan: true` solo para uno fallido o abandonado), y `POST /api/embedding-engines/reindex/switch` necesita `{"backup_confirmed": true}`.
- **`POST /mcp`**: el servidor MCP, con las herramientas `recall`, `facts_about`, `timeline`, `get_document` y `whats_new` (lector) y `remember` y `correct` (colaborador).
- **`POST /answer`** hace el recall como `POST /recall` y devuelve NDJSON en streaming, un objeto por línea: `{"type": "sources", "recall_id", "sources": [{"ref": "F1", "kind": "fact" | "episode" | "document", "id", "text", …}]}`, después `{"type": "delta", "text"}` según se escribe la respuesta, y `{"type": "done", "citations": ["F1", "D1"], "unknown": [], "called": true}` (o `{"type": "error", "detail"}`). `unknown` lista las etiquetas que citó el modelo y no estaban entre las pruebas. Sin pruebas responde que no hay información y `called` es `false`. Necesita el alcance `recall`, solo trae pasajes de documentos con `documents`, responde `429` pasado *Respuestas por persona y hora* o mientras el presupuesto de IA del brain esté agotado con pausa, y `503` sin motor LLM.
- **`POST /recall`** admite `federated` (por defecto `true`): busca también en lo que otros brains prestan a este, marca lo prestado con `origin` y añade una lista `federated` con el estado de cada origen. **`/grants`** gestiona lo que este brain presta (`scope`: `graph`, `docs` o `both`; caducidad opcional en `days`); el brain que recibe puede renunciar con `DELETE`.
- **`GET /entities/{uuid}`** es la [[Página de entidad]] en una sola llamada: la entidad, sus hechos agrupados por sentido y relación (`current` y `previous`, de lo más antiguo a lo más reciente, con la marca `conflict` en las relaciones de un solo valor y `generic` en las comodín como `RELATES_TO`, que van al final), sus vecinas y los episodios que la mencionan; los documentos que la mencionan salen de `GET /docs/mentions?entity=`. `as_of` (una fecha) da lo vigente ese día; `origin` lee una entidad que presta otro brain. `GET /entities?q=` busca entidades por nombre o por nombre fusionado. `entity.summary_repeats` es `true` cuando al menos la mitad de las líneas del resumen son los propios hechos de la entidad (la página lo oculta entonces), y `entity.aliases` nunca contiene el nombre de la propia entidad.
- **`GET /proposals`** está paginado: admite `status`, `kind` (`memory` o `correction`), `q` (título), `author` (id de usuario), `sort` (`id`, `name`, `author`, `conf`, `at`), `order` (`asc`/`desc`), `limit` (por defecto 50, máximo 500) y `offset`, y devuelve `{total, limit, offset, authors, items}` en lugar de una lista sin más. Un colaborador solo ve las suyas.
- **`GET /proposals/counts`** cuenta por estado (solo de un `kind` si se indica), y además `kinds` (cada tipo en todos los estados) y `corrections_pending`.
- **`POST /proposals`** devuelve la propuesta y `secrets_notice`: qué tipos de secreto se enmascararon o se marcaron, en el idioma de quien llama y nunca con el valor (vacío si no se encontró nada).
- **`POST /proposals/corrections`** propone invalidar un hecho: `{fact_uuid, reason, replacement?, invalid_at?}`. Si la envía un curador, se aplica al momento; `POST /proposals/{id}/reactivate` deshace una aplicada. Ver [[Propuestas]].
- **`GET /graph?group_by=`** (`label`, `source`, `document`, `author`, `token`) añade la procedencia: cada nodo y cada hecho llevan `sources`, `source_count` y `provenance` (las claves de todas las agrupaciones), y la respuesta añade `groups` con el nombre y los recuentos de cada origen. Sin `group_by` no se calcula nada: en un brain grande puede costar más que el propio subgrafo.
- **`GET /docs/{id}/entities`** devuelve, además de las `entities` mencionadas, las `relations` entre ellas (solo las vigentes, salvo `expired=true`), `total` y `expired_count`.
- **`POST /docs/duplicates`** lanza el trabajo *Buscar documentos duplicados* y devuelve su id; los documentos cuyo texto repite el de otro quedan marcados como `duplicate` y salen del índice.
- **`GET /secrets/scan`** pasa el detector de secretos en solo lectura por las propuestas y los documentos del brain y devuelve recuentos por regla, nunca valores. La política (`secret_mode`: `mask`, `block`, `warn`; `secret_allow`: excepciones) se cambia con `PATCH /api/brains/{slug}`.
- **`/conflicts`**: posibles contradicciones en relaciones de un solo valor; `/resolve` invalida los hechos de `invalidate` y conserva `keep` si se indica (sin él, solo se invalidan los de la lista); siempre tiene que quedar vigente al menos un hecho del grupo, o devuelve 400. Se puede deshacer desde el historial del vocabulario. Cada grupo lleva `targets` y `likely_multi` (la relación probablemente admite varios valores, así que no hay propuesta), y con `all=true` cada relación de `by_relation` lleva `max_targets` y `likely_multi`. `/dismiss` marca un grupo como no contradicción (`{source_uuid, source, relation, target_type, facts}`); sigue oculto mientras no se le sume otro hecho, y el `GET` lo lista en `dismissed`.
- **`/refqueries`**: consultas de referencia y sus ejecuciones; `POST /refqueries/runs` con `sweep` (una lista de umbrales de similitud) simula sin cambiar el ajuste.

`GET /health` responde `200` con `{"ok", "db", "graph", "graphs"}` cuando PostgreSQL y FalkorDB responden, y `503` con el mismo cuerpo cuando alguno está caído; es el endpoint para un monitor externo ([Vigilar la instancia](Instalaci%C3%B3n#vigilar-la-instancia)).

## Convenciones
- Fechas en ISO 8601 con zona horaria.
- Listas paginadas: `limit` y `offset`, y devuelven `total`.
- **Idioma:** los mensajes de error (`detail`), los textos del MCP y los encabezados del contexto del recall siguen la cabecera `Accept-Language` (`es`, `en`); si no, el idioma que eligió la persona dueña de la sesión o del token; si no, el de la instancia. La memoria guardada nunca se traduce. Si tu cliente compara textos de error, envía `Accept-Language` o compara el código de estado.
- La API **puede cambiar entre versiones 0.x**: fija la versión de MimirSynth que usas.

## Ejemplos
Ver [[Conectar agentes]] (recall, propuestas y MCP) y [[Memoria documental]] (búsqueda de documentos).
