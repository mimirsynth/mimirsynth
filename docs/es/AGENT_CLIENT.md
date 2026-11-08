[English](../AGENT_CLIENT.md) · **Español**

# Integraciones de agentes: el contrato de configuración y la biblioteca cliente compartida

Todos los plugins nativos de agentes (hoy Claude Code; Codex, OpenCode, Hermes Agent y OpenClaw en camino) leen **una sola configuración** y se construyen sobre **una sola biblioteca cliente**, para que un único `setup` sirva a todos los agentes de una máquina y todos se comporten igual: recall antes de cada prompt, lo que ha cambiado al empezar la sesión, `setup` / `status` / `search` / `remember`, y una captura de sesiones desactivada por defecto.

Esta página congela ese contrato (**versión 1**) y documenta la biblioteca. Para los tokens, los roles y la propia API, consulta [AGENTS.md](AGENTS.md).

## Dónde está

| Ruta | Qué |
|---|---|
| `integrations/shared/python/mimirsynth_agent/` | La biblioteca en Python (solo la biblioteca estándar, Python 3.8 o posterior). La fuente de verdad |
| `integrations/shared/typescript/` | Su port a TypeScript, para los agentes que ejecutan JavaScript (OpenCode, OpenClaw). Sin dependencias en ejecución |
| `integrations/shared/contract/cases.json` | Los casos que toda implementación tiene que pasar |
| `integrations/shared/vendor.py` | Copia la biblioteca de Python en cada plugin que la lleva |
| `integrations/<agente>/` | Cada plugin |

La biblioteca vive en `integrations/shared/`, junto a los plugins y versionada con el servidor, porque no es un agente en sí y todos los plugins dependen de ella. Un plugin de Python no puede importarla desde ahí: un agente instala la carpeta del plugin y nada de fuera (Claude Code copia el plugin a su caché). Por eso cada plugin de Python lleva una **copia exacta** (en Claude Code, `plugin/scripts/mimirsynth_agent/`), escrita por `python integrations/shared/vendor.py`, y un test falla si una copia difiere. A su vez, la biblioteca lleva el propio detector de secretos del servidor, `api/mimirsynth/secretscan.py`, byte a byte, para que un cliente enmascare exactamente lo que enmascararía el servidor. Un plugin de JavaScript importa directamente las fuentes de TypeScript o las empaqueta al construirse.

## El fichero de configuración

`~/.config/mimirsynth/config.json`, en todos los sistemas (Windows incluido), o el fichero que indique **`MIMIRSYNTH_CONFIG`**. Guarda tokens, así que quien lo escribe lo deja legible solo por su dueño (`0600`). Ejemplo:

```json
{
  "url": "https://mimirsynth.example.com",
  "brain": "equipo",
  "token": "mst_…",
  "write_token": "mst_…",
  "capture": "off",
  "projects": {
    "/home/yo/trabajo/infra": {"brain": "infra", "token": "mst_…", "write_token": "mst_…"}
  }
}
```

| Clave | Tipo | Por defecto | Significado |
|---|---|---|---|
| `url` | texto | — | El servidor, `https://…` (da igual una `/` al final) |
| `brain` | texto | — | El slug del brain |
| `token` | texto | — | Un token de API de ese brain. Para el recall basta uno de **lector** con el alcance Recall |
| `write_token` | texto | `token` | Un token de **colaborador**, para proponer. La captura nunca envía con un token de curador |
| `timeout` | número | `4` | Segundos que puede tardar una llamada antes de rendirse (más de 0) |
| `max_chars` | entero | `4000` | Máximo de caracteres que inyecta el recall antes de cada prompt (más de 0) |
| `recall` | booleano | `true` | Recall antes de cada prompt |
| `news` | booleano | `true` | Lo que ha cambiado en el brain, al empezar la sesión |
| `capture` | `off` · `draft` · `send` | `off` | Qué pasa con lo que aprendió una sesión (abajo) |
| `capture_confidence` | número | `0.3` | La confianza que declara una propuesta capturada (de 0 a 1) |
| `projects` | objeto | — | Otros valores para algunas carpetas (abajo) |

`url`, `brain` y `token` son lo que una integración necesita para funcionar; sin ellos no hace nada y lo dice en `status`. La autenticación es siempre un token de API por brain, nunca la sesión del navegador.

### De dónde sale cada valor

Gana el primero que lo da:
1. la variable de entorno **`MIMIRSYNTH_<CLAVE>`** (`MIMIRSYNTH_URL`, `MIMIRSYNTH_TOKEN`, `MIMIRSYNTH_BRAIN`, `MIMIRSYNTH_WRITE_TOKEN`, `MIMIRSYNTH_CAPTURE`…);
2. la entrada de `projects` del directorio de trabajo;
3. el nivel superior del fichero;
4. el valor por defecto.

Un valor vacío (una variable sin definir o en blanco, `""` o `null` en el fichero) cuenta como no dado, así que se aplica el siguiente. Un fichero que no existe, no es JSON válido o no es un objeto cuenta como vacío.

### Cómo se leen los valores

Un valor que no se puede leer como su tipo vuelve al valor por defecto: una errata nunca detiene a un agente.
- **Textos:** se recortan los espacios. Un número en el fichero se toma por sus cifras (`"brain": 42` es el brain `42`).
- **Booleanos:** `false`, `off`, `no` y `0` (en mayúsculas o minúsculas, sin contar los espacios de alrededor) y el número `0` son falso; cualquier otra palabra o número es verdadero. Cualquier otra cosa (una lista, un objeto) es el valor por defecto.
- **Números:** un número JSON, o un texto con un número decimal (`"2.5"`, `"1e3"` para `timeout`); `max_chars` solo admite enteros en un texto y recorta un número JSON con decimales (`2500.9` es `2500`). Fuera de rango, infinito o `true` es el valor por defecto.
- **`capture`:** `off`, `draft` o `send`, en mayúsculas o minúsculas. `drafts` se lee como `draft` y `auto` como `send`. Cualquier otra cosa es `off`.

### Un brain por proyecto: `projects`

`projects` relaciona una carpeta con un objeto con cualquiera de las claves anteriores. Cuando el agente trabaja en esa carpeta o por debajo, sus valores sustituyen a los del nivel superior; si varias carpetas contienen el directorio de trabajo, gana la más profunda. Las carpetas son absolutas (un `~` inicial es la carpeta personal), se comparan sin seguir enlaces y, en Windows, sin distinguir mayúsculas. Una carpeta cuyo nombre solo empieza igual no cuenta (`/trabajo` no contiene `/trabajos`). Las variables de entorno siguen ganando.

Como cada token vale para un brain, una entrada que cambia `brain` debería traer el `token` (y el `write_token`) de ese brain: si no, se usa el token del nivel superior y el servidor responde 403. Los tokens se quedan en este único fichero, legible solo por su dueño, nunca en el repositorio.

### Captura de lo que aprendió una sesión

| `capture` | Qué pasa |
|---|---|
| `off` | Por defecto. No se escribe ni se envía nada de las sesiones |
| `draft` | Cada sesión se guarda en esta máquina, ya redactada, hasta que la persona la revisa (`remember` sin título) |
| `send` | Al **siguiente** inicio de sesión, cada sesión terminada que lo merece se convierte en una propuesta, en cuarentena |

Las reglas que sigue toda integración:
- **Qué sesiones:** solo las que cambiaron ficheros o terminaron con una respuesta de al menos 400 caracteres; como mucho **una propuesta por sesión**.
- **Qué contiene:** la tarea (el primer prompt, hasta 500 caracteres), el resultado (la última respuesta, hasta 3000) y los ficheros cambiados (los 20 primeros). Nunca la transcripción.
- **La propuesta:** `name` «`<Agente>: <proyecto> — <primera línea de la tarea>`», `source` `text`, `source_description` «`<id-del-agente> session`», `origin` `auto` y `confidence` `capture_confidence`.
- **Solo con un token de colaborador:** antes de enviar, la integración pregunta `whoami`; con cualquier otro rol se niega y lo dice, porque la propuesta de un curador se saltaría la cuarentena.
- **Secretos:** todo se redacta antes de escribirse en disco o enviarse, con el propio detector del servidor (los hallazgos seguros y los posibles por igual, sustituidos por `[secret removed]`). Funciona por patrones y no es infalible.
- **Dónde quedan los registros:** un fichero JSON por sesión, legible solo por su dueño, en `~/.config/mimirsynth/state/<id-del-agente>/sessions/` salvo que el agente dé al plugin una carpeta de datos propia. Los registros de más de 14 días se borran. Claude Code los guarda en la carpeta de datos de su plugin (`$CLAUDE_PLUGIN_DATA/sessions`) o en `~/.config/mimirsynth/state/sessions/`.

## Qué hace toda integración

- **Recall antes de cada prompt** (con `recall` activado y si el prompt no es un comando): `POST /recall` con el prompt (hasta 1500 caracteres), `facts` 6, `chunks` 3 y `max_chars`, con `token`. El contexto va dentro de `<mimirsynth-memory brain="<slug>">…</mimirsynth-memory>`.
- **Lo que ha cambiado al empezar la sesión** (con `news` activado): `POST /news?limit=20&max_chars=4000`, dentro de `<mimirsynth-news brain="<slug>">…</mimirsynth-news>` cuando algo se ha añadido o ya no vale.
- **Fallo en abierto:** cada llamada tiene `timeout`; si no se llega al servidor, no se inyecta nada y el agente sigue. Si el servidor responde 401 o 403 (un token caducado o revocado, o sin el alcance), la integración lo dice con el mensaje del servidor, para que no deje de recordar sin que nadie lo vea.
- **Comandos:** `setup` (pide los tokens ocultos, en una terminal, nunca por la conversación, y escribe el fichero con `0600`), `status` (conexión, brain, rol, alcances y caducidad de cada token, versión del servidor, modo de captura, borradores), `search` (recall con más resultados) y `remember` (una propuesta con `origin` `agent`, redactada, con `write_token`).

Las rutas de la API, bajo `{url}/api/brains/{brain}`, siempre con `Authorization: Bearer <token>`:

| Ruta | Token | Respuesta |
|---|---|---|
| `POST /recall` | `token` (alcance Recall) | `{"context": …}` entre otros |
| `POST /news?limit=&max_chars=` | `token` (alcance Recall) | `{"text", "added", "gone"}` |
| `GET /whoami` | cualquiera | `{"brain", "name", "role", "version", "token": {"name", "scopes", "expires_at"}}` |
| `POST /proposals` | `write_token` (alcance Proponer) | `{"id", "status"}`; `pending` con un token de colaborador |

Una respuesta de error trae `{"detail": …}`; la biblioteca lo da como texto (en JSON cuando no lo es, como en un 422).

## La biblioteca

### Python

```python
import mimirsynth_agent as mimir
from mimirsynth_agent import capture

conf = mimir.Config(cwd=carpeta_del_proyecto)    # path=…, env=… para los tests
client = mimir.Client(conf)
answer, error = mimir.fail_open(client.recall, prompt)
if answer and answer.get("context"):
    inyectar(answer["context"])
elif error and error.auth:
    avisar_a_la_persona(error.detail)
```

- `Config(path=None, env=None, cwd=None)`: `get(key)`, `source(key)` (`env`, `project`, `file` o `default`), `capture_mode()`, `configured()`, `values()`. Además `config_path()`, `DEFAULTS`, `KEYS`, `CAPTURE_MODES`, `CAPTURE_ALIASES`.
- `Client(conf)`: `recall(query, facts=6, chunks=3, max_chars=None, timeout=None)`, `news(limit=20, max_chars=4000)`, `whoami(token=None)`, `propose(body, token=None)`, `remember(title, content, confidence=None, source_description="", origin="agent")` y `call(method, path, …)`. Lanzan `ApiError` (`status`, `detail`, `auth`) cuando el servidor responde con un error, y cualquier otra excepción cuando no se le puede alcanzar.
- `fail_open(fn, *args)`: `(respuesta, None)`, `(None, ApiError)` o `(None, None)`; nunca lanza.
- `redact(text)`: el texto con cada hallazgo sustituido por `[secret removed]`.
- `capture`: `Sessions(carpeta)` (`load`, `save`, `all`, `drop`), `worth(rec)`, `is_draft(rec)`, `proposal(rec, agent, source, confidence)`, `send(client, store, rec, agent, source)` y `default_dir(agent)`.

### TypeScript

```ts
import { Client, Config, failOpen } from "../../shared/typescript/src/index.ts";

const client = new Client(new Config({ cwd: carpetaDelProyecto }));
const { value, error } = await failOpen(() => client.recall(prompt));
```

La misma API con nombres de JavaScript (`captureMode()`, `failOpen`, `capture.isDraft`, `capture.defaultDir`, objetos de opciones como `recall(query, { maxChars })` y `remember(title, content, { confidence, sourceDescription })`), con todas las llamadas asíncronas. `Client` admite un segundo argumento, el transporte (`fetch` por defecto), que los tests sustituyen. Necesita Node 22.6 o posterior, o Bun, que ejecutan las fuentes de TypeScript tal cual; el detector de secretos es un port del del servidor, que mantienen igual los casos del contrato y un test que compara las reglas.

## Tests de contrato

- **Casos** (`integrations/shared/contract/cases.json`): cómo se lee la configuración (capas, valores vacíos, tipos, `projects`, alias de la captura), la redacción, qué sesiones merece la pena proponer, la propuesta en que se convierte una sesión, la petición exacta de cada llamada, cómo se lee una respuesta de error y que la captura rechaza un token de curador. `api/tests/test_agent_client.py` los pasa sobre la biblioteca de Python y `npm test` sobre el port de TypeScript. Una implementación en otro lenguaje también tiene que pasarlos.
- **Contra una instancia de prueba** (`api/tests/test_agent_contract.py`): el fixture `agent_instance` arranca un MimirSynth real en un puerto local con un brain nuevo y un token por rol (lector, colaborador, curador y un colaborador que solo puede proponer). Las dos bibliotecas comprueban el recall y `whoami`, que se dicen un 401 y un 403, el fallo en abierto con el servidor caído, `remember` redactado y en cuarentena, y la captura rechazada con un token de curador y enviada una vez con uno de colaborador; con grafo (`MIMIRSYNTH_TEST_FALKOR`), también `news`. Las comprobaciones de TypeScript están en `integrations/shared/typescript/test/live.test.ts` y se ejecutan con `MIMIRSYNTH_CONTRACT_URL`, `_BRAIN`, `_READER`, `_CONTRIBUTOR`, `_CURATOR`, `_PROPOSE_ONLY` y `_NEWS`.
- **En la CI:** el job `api` ejecuta las dos (tiene FalkorDB y Node), y el job `agent-client` comprueba los tipos del port de TypeScript y pasa sus casos.

Un plugin nuevo:
1. **Python:** añade su carpeta a `TARGETS` en `integrations/shared/vendor.py` y ejecútalo; el test existente mantiene igual su copia. Sus propios tests de extremo a extremo pueden usar el fixture `agent_instance`.
2. **JavaScript:** importa `integrations/shared/typescript/src/index.ts` (o lo empaqueta); sus tests de extremo a extremo pueden leer las mismas variables `MIMIRSYNTH_CONTRACT_*`, que pone un test de `api/tests` que use `agent_instance`, como hace `test_the_typescript_port_against_a_test_instance`.

## Publicar un cambio en un plugin

Un agente solo actualiza un plugin instalado cuando cambia la versión de su manifiesto (en Claude Code, `version` en `plugin/.claude-plugin/plugin.json`): con la misma versión, `/plugin update` y el refresco del marketplace lo dan por actual y las instalaciones existentes se quedan con los scripts viejos. Por eso **cualquier cambio en la carpeta de un plugin sube su versión**, también la copia de esta biblioteca que lleva (ejecutar `vendor.py` tras cambiar la biblioteca cambia todos los plugins que la llevan). Se sigue el versionado semántico: una corrección sube el parche; una funcionalidad nueva o una clave nueva del contrato, la versión menor. La comprobación `plugin-version` de cada pull request (`scripts/plugin_versions.py`) falla si cambió la carpeta de un plugin y su versión no subió; un plugin nuevo añade allí su carpeta y su manifiesto a `PLUGINS`.

## Cambiar el contrato

La versión 1 está congelada: las integraciones dependen de ella. Añadir una clave con valor por defecto, o un alias de la captura, es compatible. Renombrar o quitar una clave, o cambiar un valor por defecto, el orden de las capas o cómo se lee un valor, no lo es: sube `CONTRACT_VERSION` en las dos bibliotecas y en `cases.json`, actualiza esta página en los dos idiomas, y se comprueba cada plugin contra él.
