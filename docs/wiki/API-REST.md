[English](REST-API) · **Español**

# API REST

Toda la funcionalidad de la interfaz está disponible por una API REST JSON bajo `/api`. Con la aplicación en marcha, la **documentación interactiva (OpenAPI)** está en `https://tu-servidor/docs`, con todos los parámetros y esquemas. Esta página es el mapa.

## Autenticación
- **Agentes y scripts:** cabecera `Authorization: Bearer mst_…` con un [token de API](Conectar-agentes). Un token está acotado a **un brain** y a un rol (máximo curador); no puede usar las rutas de administración de la instancia.
- **La interfaz web:** cookie de sesión firmada tras iniciar sesión.
- **MCP:** `POST /api/brains/{slug}/mcp` es el [servidor MCP](Conectar-agentes) del brain (HTTP «streamable», sin estado). Admite **solo tokens de API**, nunca la cookie de sesión, y rechaza orígenes de navegador distintos del de la instancia.

Errores habituales: `401` (no autenticado o token inválido), `403` (rol insuficiente), `404` (no existe o no tienes acceso), `409` (conflicto, p. ej. duplicado), `422` (datos no válidos, o una propuesta bloqueada por llevar un secreto), `429` (demasiados intentos), `503` (en `/health`: la base de datos o el grafo están caídos).

## Rutas por brain
Todas cuelgan de `/api/brains/{slug}/…`. El rol es el **mínimo** necesario.

| Área | Rutas | Rol |
|---|---|---|
| **Recall** | `POST /recall` (`federated` opcional) · `POST /mcp` | lector |
| **Índice de texto** | `GET /index/status` · `POST /index/sync` | lector · curador |
| **Resumen** | `GET /overview` · `GET /overview/activity` | lector |
| **Episodios** | `GET /episodes` · `GET /episodes/sources` · `GET /episodes/{uuid}` | lector |
| **Hechos** | `GET /facts` · `GET /facts/relations` · `GET /timeline` · `GET /entities?q=` · `GET /entities/{uuid}` | lector |
| | `PATCH /facts/{uuid}` · `POST …/invalidate` · `POST …/reactivate` · `DELETE …` | curador |
| **Grafo y consulta** | `GET /graph` (`group_by` opcional) · `POST /query` (Cypher de solo lectura) | lector |
| **Propuestas** | `GET /proposals` (paginado) · `GET /proposals/counts` · `GET /proposals/{id}` · `POST /proposals` · `POST /proposals/corrections` | colaborador |
| | `POST /proposals/{id}/approve` · `…/reject` · `…/ingest` · `…/reactivate` | curador |
| **Documentos** | `GET /docs` · `GET /docs/search` · `GET /docs/{id}` · `…/text` · `…/file` · `…/context` · `…/entities` · `GET /docs/mentions` · `GET /docs/sources` | lector |
| | `POST /docs/uploads` (+ partes y `complete`) · `POST /docs/{id}/promote` | colaborador |
| | `DELETE /docs/{id}` · `POST /docs/{id}/reindex` · `POST /docs/duplicates` · fuentes (`/docs/sources`, escanear, wikis) | administrador |
| **Vocabulario** | `GET /vocabulary` · `GET /vocab/aliases` · `GET /vocab/types` · `GET /ontology` | lector |
| | alias, tipos, relaciones, mover/fusionar, duplicados, ontología, corrector (`/retype`) | administrador |
| | `POST /vocab/ops/{id}/revert` | curador |
| **Contradicciones** | `GET /conflicts` (`?all=true` mide todas las relaciones) · `POST /conflicts/resolve` · `POST /conflicts/dismiss` · `DELETE /conflicts/dismiss/{id}` | curador |
| **Consultas de referencia** | `GET/POST /refqueries` · `PATCH/DELETE /refqueries/{id}` · `GET /refqueries/export` · `POST /refqueries/import` · `GET/POST /refqueries/runs` · `GET /refqueries/runs/{id}` | curador |
| **Federación** | `GET /grants` | lector |
| | `POST /grants` · `PATCH /grants/{id}` · `DELETE /grants/{id}` | administrador |
| **Trabajos** | `GET /jobs` · `GET /jobs/summary` · `GET /jobs/{id}` | lector |
| | `POST /jobs/{id}/cancel` · `…/retry` | curador |
| **Miembros** | `GET/PUT /members` · `DELETE /members/{user_id}` | administrador |
| **Tokens** | `GET/POST /tokens` (`scopes`: `recall`, `documents`, `propose`; `days`: hasta que caduca, vacío para nunca) · `POST /tokens/{id}/rotate` (`grace_hours`, 0–168, por defecto 24; solo su dueño) · `DELETE /tokens/{id}`. Solo desde una sesión, nunca con un token de API | lector (de tu propio rol hacia abajo) |
| **El propio brain** | `PATCH /api/brains/{slug}` (nombre, descripción, slug, política de secretos) · `GET /api/brains/{slug}/secrets/scan` | administrador |
| **Exportar** | `POST /exports` (`vectors`, `password` opcional) · `GET /exports` · `GET /exports/{id}/download` (una vez; 410 cuando ya se descargó o caducó). Ver [[Exportar un brain]] | administrador |
| | `POST /api/brains/{slug}/delete` | propietario |

### Qué ha cambiado desde la 0.6
- **`POST /mcp`**: el servidor MCP, con las herramientas `recall`, `facts_about`, `timeline`, `get_document` y `whats_new` (lector) y `remember` y `correct` (colaborador).
- **`POST /recall`** admite `federated` (por defecto `true`): busca también en lo que otros brains prestan a este, marca lo prestado con `origin` y añade una lista `federated` con el estado de cada origen. **`/grants`** gestiona lo que este brain presta (`scope`: `graph`, `docs` o `both`; caducidad opcional en `days`); el brain que recibe puede renunciar con `DELETE`.
- **`GET /entities/{uuid}`** es la [[Página de entidad]] en una sola llamada: la entidad, sus hechos agrupados por sentido y relación (`current` y `previous`, de lo más antiguo a lo más reciente, con la marca `conflict` en las relaciones de un solo valor y `generic` en las comodín como `RELATES_TO`, que van al final), sus vecinas y los episodios que la mencionan; los documentos que la mencionan salen de `GET /docs/mentions?entity=`. `as_of` (una fecha) da lo vigente ese día; `origin` lee una entidad que presta otro brain. `GET /entities?q=` busca entidades por nombre o por nombre fusionado.
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

## Rutas de cuenta y de instancia
| Área | Rutas |
|---|---|
| **Acceso** | `GET /auth/options` · `POST /auth/login` · `POST /auth/mfa` · `POST /auth/logout` · `POST /auth/forgot` · `GET /auth/token/{código}` · `POST /auth/accept` · `POST /auth/setup` · `GET /auth/login/{proveedor}` y `/auth/callback/{proveedor}` (OIDC) · `POST /auth/passkey/options`, `/auth/passkey/login`, `/auth/passkey/mfa/options`, `/auth/passkey/mfa` |
| **Mi cuenta** | `GET /me` · `GET/PATCH /me/profile` · `POST/DELETE /me/avatar` · `POST /me/password` · `GET /me/tokens` · `GET /me/activity` · `POST /me/sessions/revoke-others` · `GET /me/2fa` y las del doble factor · `GET /me/passkeys`, `POST /me/passkeys/begin`, `…/finish`, `PATCH /me/passkeys/{id}`, `POST /me/passkeys/{id}/delete` · `GET /me/identities`, `DELETE /me/identities/{id}`, `GET /me/identities/link/{proveedor}` |
| **Notificaciones** | `GET /notifications` · `GET /notifications/summary` · `POST /notifications/read` (los avisos que puedes ver) |
| **Brains** | `GET /brains` · `POST /brains` (administrador de la instancia) |
| **Importar un brain** (administrador de la instancia) | `POST /brain-imports/uploads` · `PUT /brain-imports/uploads/{id}/parts/{n}` · `POST /brain-imports/uploads/{id}/complete` (el resumen del manifiesto) · `DELETE /brain-imports/uploads/{id}` · `POST /brain-imports` (`upload_id`, `slug`, `name`, `mode`, `password` opcional) · `GET /brain-imports`. Ver [[Importar un brain]] |
| **Administración** (administrador de la instancia) | `GET/POST /admin/users` y las acciones por usuario · `GET /settings` · `PUT/DELETE /settings/{clave}` · `POST /settings/smtp/test` · `/oidc-providers` (listar, añadir, editar, borrar, `…/{proveedor}/test`) · `GET/POST /llm-engines`, `/embedding-engines`, `/decision-engines` (+ probar, por defecto) · `/notifications/channels` (+ probar), `/notifications/deliveries` (+ reintentar), `/notifications/catalog` · `GET/POST /doc-roots` · `GET /audit` · `GET /ai-status` (`?check=true` prueba todos los motores y devuelve `model` y `ms`) |
| **Cambio de modelo de embeddings** (administrador de la instancia) | `GET /embedding-engines/reindex` (estado del relleno en sombra; `orphan: true` solo para uno fallido o abandonado) · `GET /embedding-engines/{id}/reindex/estimate` · `POST /embedding-engines/{id}/reindex` · `POST /embedding-engines/reindex/{trabajo}/cancel` · `…/retry` · `POST /embedding-engines/reindex/discard` · `POST /embedding-engines/reindex/switch` (con `{"backup_confirmed": true}`) |
| **Públicas** | `GET /health` · `GET /config` |

`GET /health` responde `200` con `{"ok", "db", "graph", "graphs"}` cuando PostgreSQL y FalkorDB responden, y `503` con el mismo cuerpo cuando alguno está caído; es el endpoint para un monitor externo ([Vigilar la instancia](Instalaci%C3%B3n#vigilar-la-instancia)).

## Convenciones
- Fechas en ISO 8601 con zona horaria.
- Listas paginadas: `limit` y `offset`, y devuelven `total`.
- **Idioma:** los mensajes de error (`detail`), los textos del MCP y los encabezados del contexto del recall siguen la cabecera `Accept-Language` (`es`, `en`); si no, el idioma que eligió la persona dueña de la sesión o del token; si no, el de la instancia. La memoria guardada nunca se traduce. Si tu cliente compara textos de error, envía `Accept-Language` o compara el código de estado.
- La API **puede cambiar entre versiones 0.x**: fija la versión de MimirSynth que usas.

## Ejemplos
Ver [[Conectar agentes]] (recall, propuestas y MCP) y [[Memoria documental]] (búsqueda de documentos).
