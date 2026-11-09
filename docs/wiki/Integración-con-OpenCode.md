[English](OpenCode-integration) · **Español**

# Integración con OpenCode

Un plugin nativo de [OpenCode](https://opencode.ai) da al agente la memoria del brain en cada prompt, añade cuatro comandos y el servidor MCP del brain, con la misma configuración que el resto de plugins de agente. Está escrito contra OpenCode 1.19.

## Instalación
Un comando, con [Node.js](https://nodejs.org) 18 o posterior:
```bash
npx -y @mimirsynth/opencode install
```
Añade el plugin a la configuración global de OpenCode (`opencode plugin @mimirsynth/opencode --global`, que OpenCode instala desde npm en el siguiente arranque) y luego ejecuta la configuración. Los dos pasos también se pueden hacer por separado:
```bash
opencode plugin @mimirsynth/opencode --global
npx -y @mimirsynth/opencode setup
```
O añade `"@mimirsynth/opencode"` a `"plugin"` en `~/.config/opencode/opencode.json` (todos los proyectos) o en el `opencode.json` de un proyecto.

## Configuración
`npx -y @mimirsynth/opencode setup` pide, en tu terminal y ocultos, la URL y el brain, un token de **lector** para el recall, opcionalmente un token de **colaborador** para proponer, y el modo de captura, y escribe el fichero compartido ([[Configuración de los plugins de agente]]). Reinicia OpenCode después y compruébalo con `/mimirsynth-status`. Los comandos corren dentro del plugin y no necesitan ni una shell ni Node.js; solo la configuración, que pide tokens, corre en una terminal.

## Qué hace
| Cuándo | Qué |
|---|---|
| Primer mensaje de una sesión | Los hechos aprendidos e invalidados desde la última sesión, dentro de `<mimirsynth-news>`. Con la captura en `send`, se proponen las sesiones terminadas |
| En cada prompt | El recall del prompt, dentro de `<mimirsynth-memory>`, añadido al mensaje antes de que lo lea el modelo. El prompt se redacta antes de salir de la máquina. Se saltan los prompts de menos de 12 caracteres y los comandos con barra |
| Al arrancar OpenCode | Añade los cuatro comandos y el servidor MCP `mimirsynth` a la configuración de OpenCode, en memoria |

Si MimirSynth no responde en `timeout`, no se inyecta nada y el prompt sigue; un token caducado o revocado se avisa con una notificación.

## Comandos y herramientas
| Comando | Qué hace |
|---|---|
| `/mimirsynth-setup` | Te dice cómo configurarlo. Los tokens nunca pasan por la conversación |
| `/mimirsynth-status` | Conexión, brain, rol, alcance y caducidad de cada token, versión del servidor, modo de captura, borradores y otros plugins de memoria |
| `/mimirsynth-search <consulta>` | Recall a demanda, con más resultados |
| `/mimirsynth-remember [título]` | El agente redacta una memoria a partir de la conversación y la propone cuando estás de acuerdo; sin título, revisa los borradores que dejó la captura |

El modelo recibe también las herramientas MCP del brain que leen (`recall`, `facts_about`, `timeline`, `whats_new`…). Propone con las herramientas propias del plugin, `mimirsynth_propose_memory`, `mimirsynth_send_draft` y `mimirsynth_drop_draft`, que redactan antes y usan el token de escritura.

Los mismos comandos existen en una terminal: `npx -y @mimirsynth/opencode status`, `search`, `remember`, `drafts`, `send-draft` y `drop-draft`.

## Captura
Apagada por defecto; la decide `capture` ([[Configuración de los plugins de agente]]). Lo propio de OpenCode:
- OpenCode no tiene «fin de sesión», así que una sesión cuenta como terminada cuando se cierra OpenCode, cuando la borras o tras 30 minutos sin un prompt nuevo. Sale de la máquina al empezar la sesión siguiente.
- Lo que cambia un subagente cuenta en la sesión que lo lanzó.

## Qué escribe en tu máquina
- `~/.config/mimirsynth/config.json`, la configuración compartida (lo escribe `setup`).
- La entrada del plugin en el `opencode.json` de OpenCode (la escribe `install`, o tú).
- Con la captura encendida: `~/.config/mimirsynth/state/opencode/sessions/`, un fichero por sesión, legible solo por ti, que se borra a los 14 días.

## El servidor MCP, sin el token en `opencode.json`
El plugin añade el servidor MCP del brain como `mimirsynth` cuando OpenCode carga su configuración, con el token de recall sacado del fichero propio de MimirSynth. Esa entrada vive solo en memoria: el token **nunca se escribe en `opencode.json`**, así que la configuración de un proyecto se puede subir al repositorio sin riesgo.

En `opencode.json` el plugin admite opciones: `["@mimirsynth/opencode", {"mcp": false}]` deja fuera el servidor MCP, `{"commands": false}` los cuatro comandos. El plugin nunca sustituye un comando o un servidor MCP con el mismo nombre que ya tengas: para configurar tú el servidor MCP, añade tu propia entrada `mimirsynth`.

Si otro plugin o servidor MCP parece inyectar memoria también, el inicio de sesión lo dice en una notificación y `/mimirsynth-status` los lista; no se bloquea nada.

## Actualizar y quitar
- Actualizar: OpenCode comprueba al arrancar los plugins que figuran sin versión; `opencode plugin update @mimirsynth/opencode` instala la nueva. Una entrada con versión exacta (`@mimirsynth/opencode@0.1.1`) se queda en ella.
- Quitar: saca `@mimirsynth/opencode` de `"plugin"` en `opencode.json`.

## Solución de problemas
| Síntoma | Qué hacer |
|---|---|
| No aparecen los comandos `/mimirsynth-…` | Reinicia OpenCode tras la instalación; comprueba que `@mimirsynth/opencode` está en `"plugin"` del `opencode.json` que lee |
| No hay memoria antes de los prompts | `/mimirsynth-status`: faltan `url`, `brain` o `token`, o `recall` está apagado |
| «token caducado» o «revocado» | Crea o rota el token ([[Conectar agentes]]) y vuelve a ejecutar `npx -y @mimirsynth/opencode setup` |
| Faltan las herramientas MCP | La opción `mcp` está en `false`, o ya tienes una entrada MCP `mimirsynth` propia, que gana |
| La captura no envía nada | Necesita un `write_token` de colaborador; una sesión se envía al empezar la sesión siguiente |

Todos los detalles: [el README del plugin](https://github.com/mimirsynth/mimirsynth/blob/main/integrations/opencode/README.es.md).
