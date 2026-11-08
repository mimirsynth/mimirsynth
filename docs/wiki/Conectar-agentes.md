[English](Connect-agents) · **Español**

# Conectar agentes

Un **agente** (Claude Code, un bot, un script, otro servicio) habla con MimirSynth con un **token de API**. Hay dos operaciones: **leer** memoria (*recall*) y **escribir** memoria (*propuestas*, que por MCP se llama `remember`). Un agente que hable el **Model Context Protocol (MCP)** se conecta al servidor MCP propio del brain con una sola línea; cualquier otro cliente usa la API HTTP.

## Lo más rápido: Conectar un agente
**Administración → Brain → Conectar un agente** lo hace en una pantalla, para Claude Code, Codex, OpenCode, Hermes Agent, OpenClaw o cualquier otro cliente MCP:
1. Elige el agente y crea allí un token para él (colaborador por defecto, o lector), o elige uno de los tuyos. El secreto de un token solo se muestra al crearlo: con uno anterior, los fragmentos llevan `mst_…` donde va el tuyo.
2. Copia lo que necesita, ya relleno con este servidor, el brain y el token: para un plugin nativo, el fichero compartido `~/.config/mimirsynth/config.json` y la línea que instala el plugin (su setup encuentra después cada respuesta en el fichero); para cualquier otro cliente, el servidor MCP del brain en la forma `mcpServers`, o su dirección y su cabecera.
3. Arranca el agente. El panel se pone en verde («Tu agente está conectado») unos segundos después de la primera llamada del agente con ese token, pida lo que pida, y luego hace un recall de prueba con lo que ese token puede ver, para que veas lo que recibe el agente. El recall de prueba es una vista previa: no queda registrado ni cuenta como un recall del agente.

La lista «Para empezar» de la pantalla de inicio enlaza aquí. El resto de esta página es lo mismo a mano.

## 1. Crea un token
En [[Mi cuenta]] → **Tokens de API** (o en [[Administrar brains y miembros]]):
1. Elige el **brain** al que accederá.
2. Ponle un **nombre** que identifique al agente («Claude Code portátil»).
3. Elige el **rol**:
   | Rol del token | El agente puede |
   |---|---|
   | **Lector** | Consultar: recall, hechos, documentos |
   | **Colaborador** | Además, **proponer** memoria (entra en cuarentena) y subir documentos |
   | **Curador** | Además, aprobar: sus propuestas se ingieren directamente |
4. Elige cuándo **caduca**: a los 30, 90 o 365 días, o nunca (la instancia puede fijar un máximo, y entonces no se ofrece «nunca»).
5. Elige su **alcance**, que lo limita más que el rol:
   | Alcance | El agente puede |
   |---|---|
   | **Consultar** | Hacer recall y leer la memoria (hechos, entidades, diario, grafo, consulta); por MCP, `recall`, `facts_about`, `timeline` y `whats_new` |
   | **Documentos** | Recibir pasajes de documentos en el recall, los propios y los que se prestan al brain, y leer documentos (`/docs`; `get_document` por MCP) |
   | **Proponer** | Enviar propuestas y correcciones (`remember` y `correct` por MCP) |

   Por defecto van marcados los tres. Un token sin **Documentos** no recibe ningún pasaje, ni por HTTP, ni por MCP, ni por federación. La curación depende solo del rol.
6. Copia el token (`mst_…`): **se muestra una sola vez**.

**Caducidad y rotación.** Un token caducado responde `401` con la fecha en que caducó, y el hook de recall enseña ese mensaje en vez de fallar sin decir nada. Unos días antes, el aviso `token.expiring` lo anuncia (ver [[Notificaciones]]). **Rotar** da un token nuevo con el mismo nombre, rol, alcance y duración, que se muestra una vez; el anterior sigue valiendo el periodo de gracia que elijas (ninguno, 1 hora, o 1, 3 o 7 días), para que dé tiempo a actualizar el agente. Solo el dueño del token puede rotarlo. Los tokens creados antes de que existiera la caducidad no caducan: la lista los marca **sin caducidad** y sugiere rotarlos. La lista también dice cuánto tiempo lleva un token sin usarse, para limpiar los olvidados. Los tokens de API se gestionan desde una sesión, nunca con otro token.

**Recomendación:** da a los agentes el rol de **colaborador**. Así lo que escriban pasa por la revisión de un curador (o del decisor) y un agente que se equivoca no ensucia el grafo. Un token **no puede tener más rol que tu usuario** y **nunca administra la instancia**.

Los tokens son **por brain**: un agente que use dos brains necesita dos tokens (o un brain al que los demás le presten, ver [Recall federado](#recall-federado)). Si deshabilitas o eliminas la cuenta que creó un token, el token deja de valer. Revoca los que ya no uses.

## 2. Conéctate por MCP
Cada brain expone un servidor MCP en:
```
https://tu-servidor/api/brains/<slug>/mcp        Authorization: Bearer mst_…
```
Usa el transporte HTTP «streamable», sin estado y solo con herramientas: sirve cualquier cliente MCP que pueda enviar una cabecera. Con Claude Code:
```bash
claude mcp add --transport http mimirsynth "https://tu-servidor/api/brains/mi-brain/mcp" --header "Authorization: Bearer mst_..."
```
El servidor ofrece estas herramientas:

| Herramienta | Rol mínimo del token | Qué hace |
|---|---|---|
| `recall` | Lector | Devuelve el contexto de memoria para una pregunta, igual que el recall HTTP. Argumentos: `query` y, opcionalmente, `facts`, `chunks`, `docs`, `max_chars`, `federated` y `min_similarity` |
| `remember` | Colaborador | Propone una memoria, con las mismas reglas que las propuestas HTTP (cuarentena para un colaborador, aprobada al instante para un curador). Argumentos: `name`, `body` y, opcionalmente, `source`, `source_description`, `reference_time` y `confidence` |
| `facts_about` | Lector | Todo lo que se sabe de una entidad: los hechos vigentes y los que dejaron de ser ciertos, del más reciente al más antiguo, con fechas, el episodio del que se aprendió cada uno y el **uuid de cada hecho** entre corchetes. La entidad se busca por nombre (sin distinguir mayúsculas ni espacios), por un nombre fusionado en ella o por su uuid; un nombre ambiguo devuelve las candidatas. Argumentos: `entity` y, opcionalmente, `status`, `limit`, `offset`, `max_chars` y `federated` |
| `timeline` | Lector | Cómo cambió lo que se sabe de una entidad: cuándo se aprendió cada hecho y cuándo dejó de ser cierto. Argumentos: `entity` y, opcionalmente, `since`, `until`, `limit`, `offset`, `max_chars` y `federated` |
| `get_document` | Lector | Lee un pasaje con el texto de alrededor (los números de `[doc N, trozo M]` que da `recall`) o un documento entero por tramos. Un pasaje que presta otro brain se lee con `origin`. Argumentos: `document` y, opcionalmente, `chunk`, `radius`, `offset`, `max_chars` y `origin` |
| `rate` | Lector | Dice si lo que devolvió un `recall` sirvió: útil, irrelevante o incorrecto, con el `recall_id` que sale al final de ese recall (vale 48 horas). Un hecho se señala por su texto tal como salió (al menos 12 caracteres; si varios hechos empiezan igual, responde con ellos para que el agente dé más texto), un pasaje por su «[doc N, trozo M]». «Incorrecto» en un hecho desde un token de colaborador propone su corrección, que decide una persona. Argumentos: `recall_id`, `rating` y `fact` o `document` y `chunk`; opcional `note` |
| `whats_new` | Lector | Hechos aprendidos y hechos que dejaron de ser ciertos desde una fecha, de lo más antiguo a lo más reciente. Sin `since`, desde donde se quedó la última llamada sin fecha de este token, así que un agente se pone al día al empezar una sesión sin guardar nada. Argumentos: opcionalmente `since`, `offset`, `limit`, `max_chars` y `federated` |
| `correct` | Colaborador | Propone invalidar un hecho que ya no es cierto, por su uuid, con el motivo y, opcionalmente, el texto que lo sustituye. **Siempre espera a una persona**, aunque el token sea de curador (ver [[Propuestas]]). Argumentos: `fact_uuid`, `reason` y, opcionalmente, `replacement`, `invalid_at`, `source_description` y `confidence` |

- El token decide el brain y el rol, así que las herramientas no llevan argumento de brain. Para usar dos brains, añade dos servidores con nombres distintos.
- Con un token de **lector**, `remember` y `correct` responden con un error que el modelo puede leer («este token solo puede leer»).
- Todas las respuestas tienen un tope de tamaño (`max_chars`) y dicen cómo pedir la página siguiente, y lo que prestan otros brains sale etiquetado con su origen.
- Solo se aceptan **tokens de API**, nunca la sesión del navegador; una petición desde una página web de otro origen se rechaza.
- Cuando una herramienta falla (argumentos no válidos, un secreto bloqueado…), el error vuelve al modelo como resultado de la herramienta, para que pueda corregirse.

Para Claude Code hay además un hook de recall que inyecta la memoria en cada prompt sin que el modelo la pida: ver [[Integración con Claude Code]].

## 3. Usa la API HTTP
Todas las peticiones llevan la cabecera `Authorization: Bearer mst_…`. La dirección base es `https://tu-servidor/api/brains/<slug>/…`.

### Leer: recall
```bash
curl -s -X POST "$URL/api/brains/mi-brain/recall" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query": "¿dónde corre la base de datos de producción ahora?"}'
```
La respuesta incluye:
- `facts`: los hechos más parecidos (vigentes e invalidados, con fechas), cada uno con su `similarity` con la pregunta (coseno, 0–1). Un hecho que entra porque sustituye a otro que ya no es cierto, o porque lo dice un fragmento o un pasaje del resultado y ya no es cierto, llega por ese vínculo y no por cercanía: su `similarity` es `null`.
- `chunks`: fragmentos del texto original de los episodios, cada uno con su `similarity`. Un fragmento de un episodio cuyos hechos dejaron de ser ciertos lleva `superseded` (cada hecho que ya no es cierto, cuándo dejó de serlo y los vigentes en `replaced_by`) y va al final; en `context` se lee «> Puede estar superado: … Ahora: …». Un hecho vigente que sustituye a otro lleva `replaces`.
- `documents`: los pasajes de documentos citados, si los hay, cada uno con `source_updated_at` (cuándo se actualizó su página por última vez). Un pasaje que dice un hecho que ya no es cierto lleva `superseded`, como los fragmentos, y va al final.
- `context`: **el bloque de texto listo para inyectar en el prompt**.
- `federated`: solo cuando otros brains prestan a este, el estado de cada uno (`ok`, `error`, `off`).
- `min_similarity`: el umbral aplicado a hechos y fragmentos.
- `ms`: tiempos.

Parámetros opcionales:
| Parámetro | Por defecto | Rango | Qué es |
|---|---|---|---|
| `facts` | 8 | 0–30 | Máximo de hechos |
| `chunks` | 4 | 0–15 | Máximo de fragmentos de episodios |
| `max_chars` | 6000 | 500–30000 | Tamaño máximo del contexto |
| `docs` | el de la instancia (2) | 0–6 | Pasajes de documentos. **0 = sin documentos** |
| `federated` | `true` | | Incluir lo que otros brains prestan a este. `false` = solo la memoria propia del brain |
| `min_similarity` | el de la instancia (0,55) | 0–1 | Similitud mínima para que entre un hecho o un fragmento de episodio. Si no llega nada, `context` vuelve **vacío**. **0 = sin umbral** |

> El recall tarda del orden de **100–300 ms** y **no usa ningún LLM**, así que es seguro llamarlo en cada turno. Si el servidor no responde, tu agente debe seguir sin memoria (el hook de Claude Code lo hace).

### Escribir: propuestas
```bash
curl -s -X POST "$URL/api/brains/mi-brain/proposals" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Base de datos migrada", "body": "El 19-oct la base de datos de producción pasó al servidor db02.", "confidence": 0.8}'
```
| Campo | Obligatorio | Qué es |
|---|---|---|
| `name` | sí | Título corto (hasta 255 caracteres) |
| `body` | sí | El contenido (hasta 50.000 caracteres) |
| `source` | no | `text` (por defecto), `message` o `json` |
| `source_description` | no | De dónde viene (hasta 255 caracteres) |
| `reference_time` | no | Fecha ISO de **cuándo ocurrió** lo que cuentas, si no es ahora |
| `confidence` | no | 0–1: tu confianza en el dato |

Con token de **colaborador** la propuesta queda **pendiente**; con **curador**, **aprobada** y se ingiere al momento. Para consejos de redacción, [[Escribir buena memoria]].

### Documentos
`GET /api/brains/<slug>/docs/search?q=…` busca por significado. `GET …/docs/<id>/context?chunk=<n>` devuelve más contexto de un pasaje y `…/docs/<id>/file` el original. Ver [[Memoria documental]].

## Recall federado
Un administrador de un brain puede **prestar su lectura** a otro brain (Administración → Brain → **Federación**). El recall del brain que recibe, por HTTP y por MCP, busca entonces también en lo prestado, lo fusiona con su propia memoria y marca cada elemento prestado con su origen (`· de «slug»` en el contexto, un campo `origin` en el JSON). El agente no necesita otro token: sigue usando el del brain que recibe. El préstamo es solo de lectura, en un sentido y de un salto; `remember` siempre escribe en el brain del token. Pasa `federated: false` para obtener solo la memoria propia del brain. Detalles en [Federación entre brains](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/FEDERATION.md).

## Idioma de las respuestas
Los mensajes de error, las descripciones e instrucciones de las herramientas del MCP y los encabezados del contexto del recall (`## Hechos vigentes`…) llegan en el idioma de quien llama, elegido por este orden:
1. La cabecera `Accept-Language`, si pide un idioma disponible (`es`, `en`).
2. El idioma que la persona dueña del token eligió en [[Mi cuenta]].
3. El de la instancia (`MIMIRSYNTH_DEFAULT_LANGUAGE`, o Administración → General).

La memoria guardada (hechos, episodios, documentos) se devuelve tal como se escribió; no se traduce. Si tu cliente compara textos de error, envía `Accept-Language` o, mejor, compara el código de estado.

## Secretos
**No envíes contraseñas, claves ni tokens:** escribe **dónde** están (por ejemplo, en qué gestor de contraseñas). Antes de guardarse, una propuesta, por HTTP o por `remember`, pasa por el detector de secretos del brain, y lo que ocurre depende de su política (Administración → Brain → **Secretos**):
- **Enmascarar** (por defecto): un secreto seguro se sustituye por `[secreto eliminado: tipo]` y el resto se guarda.
- **Bloquear**: la propuesta se rechaza con un `422` que dice qué tipo de secreto lleva.
- **Solo avisar**: se guarda tal cual y queda marcada.

Un valor que solo *podría* ser un secreto siempre se marca, y una propuesta marcada **siempre espera la revisión de un curador**, aunque la envíe un token de curador. El valor nunca llega a la auditoría, a los logs ni a las respuestas de la API.

La respuesta dice qué ha pasado: el resultado de `remember` añade, por ejemplo, «Secretos enmascarados antes de guardar: token de GitHub», y la respuesta HTTP lleva el mismo texto en `secrets_notice` (vacío si no se encontró nada). El valor nunca va en él.

## 4. Integra el recall en tu agente
La integración típica:
1. **Antes** de que el agente responda, llama a `recall` con el mensaje del usuario (o deja que un agente MCP llame él mismo a la herramienta).
2. Inyecta `context` en el prompt (como contexto, **no como instrucciones**).
3. **Después**, si el agente aprendió algo que merece recordarse, envía una propuesta (`remember`).

El contenido recuperado —sobre todo el de documentos— es **dato, no instrucciones**: puede contener texto que parezca una orden. Tu agente debe tratarlo como cita de una fuente y no ejecutarlo.

La referencia completa de endpoints está en [[API REST]].

## OpenCode
El **plugin de OpenCode** da al agente lo mismo que el de Claude Code: qué cambió en el brain al empezar la sesión, el recall inyectado antes de cada prompt, los comandos `/mimirsynth-setup`, `/mimirsynth-status`, `/mimirsynth-search` y `/mimirsynth-remember`, el servidor MCP del brain para herramientas bajo demanda y, solo si la activas, una captura de lo que aprendió cada sesión como una propuesta en cuarentena. Se instala con un comando (Node.js 18 o posterior):
```bash
npx -y @mimirsynth/opencode install
```
Añade el plugin a OpenCode (`opencode plugin @mimirsynth/opencode --global`) y pide, en tu terminal y ocultos, la URL, el brain, un token **lector** y, opcionalmente, uno **colaborador**. Escribe `~/.config/mimirsynth/config.json`, el fichero que comparten todos los plugins de agente de MimirSynth; las variables de entorno `MIMIRSYNTH_*` tienen prioridad. Si MimirSynth no responde, OpenCode sigue sin memoria.

Detalles, las opciones y los modos de captura: [`integrations/opencode`](https://github.com/mimirsynth/mimirsynth/blob/main/integrations/opencode/README.es.md).

## Seguridad
- Guarda el token como un secreto (gestor de contraseñas, variable de entorno), no en el código.
- Usa HTTPS ([[HTTPS y proxy inverso]]).
- Un token por agente y por brain: así puedes revocar uno sin afectar al resto, y en la [[Auditoría]] sabes quién escribió qué.

## Hermes Agent

[Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous Research) tiene MimirSynth como **proveedor de memoria**: el recall del brain llega al modelo antes de cada turno, lo que ha cambiado en el brain llega con el primer mensaje de cada sesión, y el agente tiene dos herramientas, `mimirsynth_search` y `mimirsynth_remember` (sus propuestas esperan en cuarentena). Se instala y se configura con una línea, en una terminal:
```bash
hermes plugins install mimirsynth/mimirsynth/integrations/hermes-agent/plugin && hermes memory setup mimirsynth
```
La configuración pide el servidor, el brain y los tokens (ocultos, nunca por el chat; un token de **lector** para consultar y uno de **colaborador** para proponer) y escribe `~/.config/mimirsynth/config.json`, el fichero que leen todas las integraciones de MimirSynth, así que una sola configuración sirve también para Claude Code y las demás. Un perfil de Hermes puede usar otro brain poniendo `MIMIRSYNTH_URL`, `MIMIRSYNTH_BRAIN` y `MIMIRSYNTH_TOKEN` en su `.env`.

- `hermes mimirsynth status` (o `/mimirsynth status` en un chat) comprueba cada token; `search`, `remember` y `drafts` funcionan en los dos sitios.
- Si MimirSynth no está o va lento, Hermes sigue sin memoria; un token caducado se avisa una vez.
- La **captura de sesiones** está apagada por defecto; con `capture` en `draft` o `send`, cada sesión terminada que cambió ficheros o acabó con una respuesta sustancial se convierte en un borrador o en una propuesta en cuarentena, sin secretos, y solo con un token de colaborador.

Los detalles, todos los comandos y qué hace en tu máquina: [el README del plugin](https://github.com/mimirsynth/mimirsynth/blob/main/integrations/hermes-agent/plugin/README.es.md).

## Codex
Un plugin nativo para el CLI de Codex (0.167 o posterior) hace el recall antes de cada prompt, trae lo que cambió al empezar la sesión y añade las skills `$mimirsynth:setup`, `$mimirsynth:status`, `$mimirsynth:search` y `$mimirsynth:remember`, con la misma configuración que el resto de plugins de agente de MimirSynth (`~/.config/mimirsynth/config.json`). Se instala con un comando:
```bash
codex plugin marketplace add mimirsynth/mimirsynth && codex plugin add mimirsynth@mimirsynth
```
Después, una vez:
1. Ejecuta `$mimirsynth:setup` en Codex: muestra el comando que pide la URL, el brain y los tokens, ocultos, en tu terminal. Si MimirSynth ya está configurado para otro agente en la máquina, no hay nada que hacer.
2. Abre `/hooks` en Codex y confía en los tres hooks de `mimirsynth`. Codex solo ejecuta los hooks de un plugin cuando confías en ellos, y vuelve a preguntar tras cada actualización; `$mimirsynth:status` avisa cuando no lo están.

La captura de lo que aprendió cada sesión está **desactivada** por defecto; si la activas, una sesión terminada se lee del propio fichero de sesión de Codex y se convierte como mucho en una propuesta, redactada, en cuarentena. Para que el modelo pueda llamar también a las herramientas de MimirSynth, añade el servidor MCP del brain con `codex mcp add mimirsynth --url "https://tu-servidor/api/brains/<slug>/mcp" --bearer-token-env-var MIMIRSYNTH_TOKEN`. Detalles en [el README del plugin](https://github.com/mimirsynth/mimirsynth/blob/main/integrations/codex/README.es.md).

## OpenClaw
[OpenClaw](https://github.com/openclaw/openclaw) usa MimirSynth con un plugin nativo: recall antes de cada prompt, qué cambió al empezar cada sesión, `mimirsynth_search` y `mimirsynth_remember` como herramientas del agente, `/mimirsynth status|search|drafts` en cualquier chat y una captura de sesiones opcional, desactivada por defecto. En la máquina donde corre el Gateway de OpenClaw (OpenClaw 2026.9.36 o posterior):
```bash
openclaw plugins install @mimirsynth/openclaw && openclaw mimirsynth setup
```
OpenClaw pide que aceptes las capacidades del plugin. `setup` pide, en la terminal y nunca por un chat, la URL, el brain, un token **lector** para el recall, opcionalmente un token **colaborador** para proponer (ocultos) y el modo de captura; escribe `~/.config/mimirsynth/config.json`, que comparten todas las integraciones de agentes de MimirSynth de esa máquina, y ofrece conceder el acceso a la conversación que OpenClaw exige antes de ejecutar el hook de recall de un plugin de terceros (`plugins.entries.mimirsynth.hooks.allowConversationAccess`). Compruébalo con `openclaw mimirsynth status`.

Es un plugin acompañante: la memoria propia de OpenClaw sigue funcionando. Por defecto solo tus propias conversaciones ven el brain; los grupos y otros remitentes no, salvo que pongas `plugins.entries.mimirsynth.config.conversations` a `true`. Si MimirSynth está caído, no se inyecta nada y el asistente sigue. Detalles, la captura y cómo instalarlo desde un clon: [`integrations/openclaw`](https://github.com/MimirSynth/mimirsynth/tree/main/integrations/openclaw).
