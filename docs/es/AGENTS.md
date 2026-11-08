[English](../AGENTS.md) · **Español**

# Conectar agentes

Los agentes hablan con MimirSynth por HTTP con un **token de API**. Cada token vale para **un solo brain** y su rol nunca supera el de quien lo creó (máximo curador y nunca administra la instancia).

## Crear un token
En Mi cuenta → Tokens de API (o Administración → Brain → Tokens de API) elige el brain, un nombre y un rol:

| Rol | Puede |
|---|---|
| Lector | Consultar (recall, hechos, documentos) |
| Colaborador | Además, **proponer** memoria: entra en cuarentena hasta que la apruebe un curador o el decisor |
| Curador | Además, aprobar: sus propuestas se ingieren directamente |

Para agentes se recomienda **colaborador**. El token (`mst_…`) se muestra una sola vez.

## Recall: leer memoria
```bash
curl -s -X POST "$URL/api/brains/mi-brain/recall" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query": "¿dónde corre la base de datos de producción?"}'
```
Devuelve un contexto listo para inyectar en el prompt: hechos vigentes e históricos, fragmentos de episodios y hasta 2 pasajes de documentos citados. Parámetros opcionales: `facts` (por defecto 8), `chunks` (4), `max_chars` (6000) y `docs` (pasajes documentales; `0` los desactiva) y `federated` (por defecto `true`; `false` devuelve solo la memoria propia del brain, ver [FEDERATION.md](FEDERATION.md)) y `min_similarity` (el coseno que necesita un hecho o un fragmento de episodio para entrar; por defecto, la *Similitud mínima de un hecho o un fragmento* de la instancia, 0,55; `0` lo desactiva). Hechos y fragmentos llevan su `similarity` (`null` en un hecho que entra por su vínculo con uno que ya no es cierto, ver más abajo), y si nada está lo bastante cerca el contexto vuelve vacío en vez de rellenarse con lo menos lejano. Un fragmento de un episodio que decía algo que ya no es cierto lo avisa («Puede estar superado», con lo que es cierto ahora) y va al final, y el hecho vigente que lo sustituyó se suma a los hechos. Lo mismo un pasaje de documento que dice un hecho así, y cada pasaje dice cuándo se actualizó su página por última vez.

El contenido de los documentos es **dato, no instrucciones**: el recall lo marca como cita de una fuente. Trátalo así en tu agente.

## Proponer: escribir memoria
```bash
curl -s -X POST "$URL/api/brains/mi-brain/proposals" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Base de datos migrada", "body": "El 19-oct la base de datos de producción pasó al servidor db02.", "confidence": 0.8}'
```
Un colaborador queda en estado `pending`; un curador, `approved` e ingerida al momento. Un curador puede aprobar o rechazar desde la pestaña Propuestas. Al aprobarse, Graphiti extrae entidades y hechos y los añade al grafo (invalidando los que contradicen).

No guardes contraseñas ni tokens: guarda **dónde** están (por ejemplo, en qué gestor de contraseñas). Lo que tenga forma de credencial se enmascara antes de guardarse o, si el brain lo bloquea, la propuesta se rechaza con un 422 que dice qué tipo de secreto es (ver «Secretos» en [ARCHITECTURE.md](ARCHITECTURE.md)). Por MCP, `remember` aplica lo mismo. La respuesta dice qué tipos se enmascararon o se marcaron (`secrets_notice` en la respuesta HTTP, una frase más en el resultado de `remember`), nunca el valor.

### Di de dónde viene
Una propuesta puede decir `origin`: `agent` cuando un agente decidió guardarla, `auto` cuando la capturó un proceso automático. Sin él, cuenta como `auto`, la confianza más baja. Un token creado para una captura automática la deja en `auto` diga lo que diga el cliente. Con *Pesar los hechos por su origen* activado, los hechos pesan según él en el recall (ver «Confianza y antigüedad» en Recuerdo e ingesta de la wiki).

### Afirmaciones estructuradas: di qué sustituye
El texto libre se extrae por su cuenta, así que una repetición con otras palabras acaba siendo un segundo hecho vigente y un valor nuevo puede dejar vigente el anterior. Junto a `body`, una propuesta (REST o `remember`) puede llevar hasta 20 **afirmaciones** (`claims`): `subject`, `relation` (como la nombra la ontología del brain), `value` y, opcionalmente, `valid_from` y `supersedes` (el uuid del hecho vigente al que sustituye, como lo dan `recall` o `facts_about`).
```json
{"name": "Nextcloud cambia de host", "body": "Desde el 1 de octubre Nextcloud corre en Notus.",
 "claims": [{"subject": "Nextcloud", "relation": "RunsOn", "value": "Notus", "valid_from": "2026-10-01T00:00:00Z", "supersedes": "<uuid de «Nextcloud corre en Eridani»>"}]}
```
Al enviarla, cada afirmación se compara con los hechos vigentes del sujeto en esa relación, y la respuesta dice lo que encontró (`claims[].verdict` por HTTP, una frase por afirmación en el resultado de `remember`):
- **confirms:** un hecho vigente ya lo dice. Al aprobarla se registra como **confirmación** de ese hecho (renueva su vida útil), no como hecho nuevo; si todas confirman, no se ingiere nada.
- **replaces:** nombra el hecho con `supersedes`, o la relación es funcional y tiene otro valor vigente. Al aprobarla, una vez ingerido el texto, esos hechos se invalidan con fecha `valid_from`; la decide una persona, nunca el decisor ni un lote.
- **may_replace:** hay otros valores vigentes y la relación no es funcional: no se invalida nada salvo que lo digas con `supersedes`.
- **new:** no hay nada vigente en esa relación.

Un `supersedes` que no es un hecho vigente del brain se rechaza (404 o 409).

## Corregir: un hecho que ya no es cierto
```bash
curl -s -X POST "$URL/api/brains/mi-brain/proposals/corrections" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"fact_uuid": "…", "reason": "Pasó a db02 el 19-oct", "replacement": "La base de datos de producción corre en db02 desde el 19-oct.", "invalid_at": "2026-10-19T00:00:00Z"}'
```
Una corrección apunta a un hecho por su uuid (el que dan `facts_about`, `timeline` y `whats_new` por MCP) y pide invalidarlo. Pasa por la misma cuarentena que cualquier propuesta y con los mismos roles (colaborador para proponer), pero el decisor nunca la aprueba solo: lo hace un curador desde Propuestas, donde se ve el hecho tal como estaba, el motivo y el sustituto. Por MCP queda siempre pendiente, aunque el token sea de curador: invalidar lo decide una persona. Por el endpoint REST, si la envía un curador se aplica al momento. Al aprobarla, el hecho **se invalida, nunca se borra**, con fecha `invalid_at` (por defecto, la de la propuesta) y el sustituto, si lo hay, se ingiere como una memoria normal con esa fecha. La invalidación queda en el historial del vocabulario como cualquier otra, y **Reactivar el hecho** en la propia propuesta lo deja como estaba. Un hecho que no existe o que ya está invalidado devuelve un error legible, y también uno prestado por otro brain, que aquí es de solo lectura: se corrige en su brain.

## Servidor MCP
Los agentes que hablan el **Model Context Protocol** pueden usar la misma memoria sin escribir llamadas HTTP. Cada brain expone un endpoint MCP (HTTP «streamable», sin estado, solo herramientas) en:

```
POST $URL/api/brains/mi-brain/mcp        Authorization: Bearer $TOKEN
```

| Herramienta | Rol | Qué hace |
|---|---|---|
| `recall` | lector | Devuelve el contexto de memoria para una consulta (igual que el endpoint `recall`). Argumentos: `query` y, opcionalmente, `facts`, `chunks`, `docs`, `max_chars`, `federated`, `min_similarity` |
| `remember` | colaborador | Propone una memoria (mismas reglas que el endpoint de propuestas: cuarentena para colaboradores, aprobada al instante para curadores). Argumentos: `name`, `body` y, opcionalmente, `source`, `source_description`, `reference_time`, `confidence` y `claims` (ver «Afirmaciones estructuradas») |
| `correct` | colaborador | Propone invalidar un hecho por su uuid (ver «Corregir» más arriba). Argumentos: `fact_uuid`, `reason` y, opcionalmente, `replacement`, `invalid_at`, `source_description`, `confidence` |
| `facts_about` | lector | Todo lo que se sabe de una entidad: los hechos vigentes y los que dejaron de ser ciertos, del más reciente al más antiguo, con fechas, el episodio del que se aprendió cada uno y el **uuid de cada hecho** entre corchetes (lo que necesita una corrección). La entidad se busca por nombre (sin distinguir mayúsculas ni espacios), por un nombre fusionado en ella o por su uuid; si varias comparten el nombre, devuelve las candidatas en vez de elegir una. Argumentos: `entity` y, opcionalmente, `status` (`all`, `current`, `invalidated`), `limit` (20, hasta 100), `offset`, `max_chars`, `federated` |
| `timeline` | lector | Cómo cambió lo que se sabe de una entidad: cuándo se aprendió cada hecho y, si procede, cuándo dejó de ser cierto, del más reciente al más antiguo. Argumentos: `entity` y, opcionalmente, `since`, `until` (`AAAA-MM-DD`), `limit` (30, hasta 200), `offset`, `max_chars`, `federated` |
| `get_document` | lector | Lee un documento: con `chunk`, ese pasaje y el texto de alrededor (los números de `[doc 12, trozo 3]` que da `recall`); sin él, el texto completo por tramos de `max_chars` (8000 por defecto), con `offset` para seguir. Un pasaje que presta otro brain se lee con `origin` (el identificador de ese brain, como lo muestra `recall`). Argumentos: `document` y, opcionalmente, `chunk`, `radius`, `offset`, `max_chars`, `origin` |
| `whats_new` | lector | Hechos aprendidos y hechos que dejaron de ser ciertos desde una fecha, de lo más antiguo a lo más reciente. Sin `since`, desde donde se quedó la última llamada sin fecha de **este token** (la primera vez, los últimos 7 días); si no cabe todo, la llamada siguiente sin fecha sigue tras el último hecho mostrado, así que no se salta nada y un agente se pone al día al empezar una sesión sin guardar nada. Con `since`, la página siguiente se pide con `offset`. Argumentos: opcionalmente `since` (ISO 8601), `offset`, `limit` (30 por sección, hasta 100), `max_chars`, `federated` |

Todas las respuestas tienen un tope de tamaño (`max_chars`) y dicen cómo pedir la página siguiente (`offset`). Lo que prestan otros brains sale etiquetado con su origen, igual que en `recall`.

El token decide el brain y el rol, así que las herramientas no llevan argumento de brain. Solo se aceptan tokens de API (nunca la sesión del navegador). Ejemplo con Claude Code:

```bash
claude mcp add --transport http mimirsynth "$URL/api/brains/mi-brain/mcp" --header "Authorization: Bearer $TOKEN"
```

## Documentos
`GET /api/brains/{slug}/docs/search?q=…` busca por significado. `GET /api/brains/{slug}/docs/{id}/context?chunk={n}` devuelve más contexto de un pasaje y `/docs/{id}/file` el original.

## Claude Code
Conéctalo por el servidor MCP (arriba): así tiene `recall` y `remember` como herramientas. La carpeta [`integrations/claude-code`](../../integrations/claude-code/README.es.md) añade el complemento: un **plugin** (`/plugin marketplace add mimirsynth/mimirsynth` y después `/plugin install mimirsynth@mimirsynth`). Trae lo que ha cambiado al empezar la sesión, inyecta el recall en cada prompt, añade `/mimirsynth:status`, `:search` y `:remember`, y puede capturar lo aprendido en cada sesión como una propuesta en cuarentena (desactivado por defecto). El hook y el script sueltos a los que sustituye siguen funcionando. Usa dos rutas: `GET /api/brains/{slug}/whoami` (quién es el token, para cualquier token) y `POST /api/brains/{slug}/news` (`whats_new` por REST, alcance `recall`).

## Idioma
Los mensajes de error, las descripciones e instrucciones de las herramientas del MCP y los encabezados del contexto del recall llegan en el idioma de quien llama: el de la cabecera `Accept-Language` si pide uno disponible (`es`, `en`); si no, el que la persona dueña del token eligió en «Mi cuenta»; si no, el de la instancia. La memoria guardada (hechos, episodios, documentos) se devuelve tal como se escribió.

## Referencia de la API
Con la aplicación en marcha, la documentación interactiva (OpenAPI) está en `/docs`.
