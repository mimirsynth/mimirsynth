[English](README.md) · **Español**

# MimirSynth para OpenCode

Un plugin nativo de [OpenCode](https://opencode.ai) que da al agente la memoria de tu equipo, con lo mismo que el [plugin de Claude Code](../claude-code/README.es.md):
- **Qué cambió al empezar la sesión.** Los hechos aprendidos e invalidados desde la sesión anterior (`POST /news`), dentro de `<mimirsynth-news>`, con el primer mensaje.
- **Recall antes de cada prompt.** La memoria para el prompt, dentro de `<mimirsynth-memory>`, añadida al mensaje antes de que el modelo lo lea. Tú decides el tamaño (`max_chars`, 4000) y el tiempo de espera (`timeout`, 4 s). El prompt se limpia de secretos antes de salir de la máquina. Si el servidor no responde, no se inyecta nada y el prompt sigue; un token caducado o revocado se avisa.
- **Cuatro comandos:**

| Comando | Qué hace |
|---|---|
| `/mimirsynth-setup` | Te dice cómo configurarlo. Los tokens nunca pasan por la conversación: la configuración se hace en tu terminal, que los pide ocultos |
| `/mimirsynth-status` | Conexión, brain, rol, permisos y caducidad de cada token, versión del servidor, modo de captura, borradores y otros plugins de memoria |
| `/mimirsynth-search <consulta>` | Recall bajo demanda, con más resultados |
| `/mimirsynth-remember [título]` | El agente redacta una memoria a partir de la conversación y la propone cuando estás de acuerdo; sin título, repasa los borradores que dejó la captura |

- **El servidor MCP del brain** para herramientas bajo demanda, añadido como `mimirsynth` con el token de recall, así que ofrece las de lectura (`recall`, `facts_about`, `timeline`, `whats_new`…); las propuestas van por la herramienta propia del plugin, que antes limpia los secretos y usa el token de escritura. El token se queda en el fichero de MimirSynth: nunca se escribe en `opencode.json`.
- **Captura opcional de lo que aprendió cada sesión**, explicada abajo.

Los comandos se ejecutan dentro del plugin, así que no necesitan shell ni Node.js; solo la configuración, que pide tokens, se hace en una terminal.

## Instalación

Un comando, con [Node.js](https://nodejs.org) 18 o posterior:
```bash
npx -y @mimirsynth/opencode install
```
Añade el plugin a la configuración global de OpenCode (`opencode plugin @mimirsynth/opencode --global`, que OpenCode instala desde npm al arrancar) y después lanza la configuración. Si lo prefieres, haz los dos pasos tú:
```bash
opencode plugin @mimirsynth/opencode --global
npx -y @mimirsynth/opencode setup
```
O añade `"@mimirsynth/opencode"` a `"plugin"` en `~/.config/opencode/opencode.json` (todos los proyectos) o en el `opencode.json` de un proyecto.

La configuración pide:
- la URL y el brain;
- un token **lector** para el recall (Mi cuenta → Tokens de API, permiso Recall);
- opcionalmente, un token **colaborador** para proponer;
- el modo de captura.

Escribe `~/.config/mimirsynth/config.json`, legible solo por ti. Las mismas claves pueden venir de variables de entorno `MIMIRSYNTH_*` (`MIMIRSYNTH_URL`, `MIMIRSYNTH_BRAIN`, `MIMIRSYNTH_TOKEN`…), que tienen prioridad. Reinicia OpenCode después y compruébalo con `/mimirsynth-status`.

El fichero lo comparten todos los plugins de agente de MimirSynth, así que una sola configuración sirve para Claude Code, OpenCode y el resto, y una entrada de `projects` puede dar a algunas carpetas otro brain con sus propios tokens: ver [`docs/es/AGENT_CLIENT.md`](../../docs/es/AGENT_CLIENT.md).

### Opciones

En `opencode.json`, el plugin acepta opciones: `["@mimirsynth/opencode", {"mcp": false}]` no añade el servidor MCP y `{"commands": false}` no añade los cuatro comandos. El plugin nunca sustituye un comando o un servidor MCP con el mismo nombre que ya tengas: para configurar tú el servidor MCP, añade tu propia entrada `mimirsynth`.

## Captura de lo que aprendió una sesión (desactivada por defecto)

La decide `capture`:
- **`off`** (por defecto): no se escribe ni se envía nada de las sesiones.
- **`draft`**: cada sesión se guarda en esta máquina, ya limpia de secretos, hasta que la repasas con `/mimirsynth-remember`.
- **`send`**: al **siguiente** inicio de sesión, cada sesión terminada se convierte en una propuesta.

Qué se registra y se envía:
- **Qué sesiones:** solo las que cambiaron ficheros o terminaron con una respuesta sustancial, como mucho **una propuesta por sesión**. Lo que cambia un subagente cuenta en la sesión que lo lanzó.
- **Qué contiene:** la tarea (el primer prompt), el resultado (la última respuesta) y los ficheros cambiados. Nunca la transcripción.
- **Cómo se envía:** con confianza baja (`capture_confidence`, 0.3), así que espera en **cuarentena**. Solo se envía con un token **colaborador**: con uno de curador se aprobaría al momento, así que se rechaza y se avisa.
- **Secretos:** antes de escribir nada en disco o enviarlo, se limpia con un port del propio detector del servidor, que los tests de contrato compartidos mantienen igual. Funciona por patrones y no es infalible: si dudas, lee los borradores.
- **Cuándo termina una sesión:** OpenCode no tiene «fin de sesión», así que una sesión cuenta como terminada cuando cierras OpenCode, cuando la borras o tras 30 minutos sin un prompt nuevo. Sale de la máquina en el siguiente inicio de sesión.
- **Dónde:** `~/.config/mimirsynth/state/opencode/sessions/`, un fichero por sesión legible solo por ti; los registros de más de 14 días se borran.

## Otros plugins de memoria

Si otro plugin o servidor MCP de la configuración de OpenCode parece inyectar memoria también, el inicio de sesión lo avisa (no bloquea nada) y `/mimirsynth-status` los lista. Los bloques de MimirSynth van marcados para distinguirlos.

## Cómo funciona

El plugin usa los [hooks de plugins](https://opencode.ai/docs/plugins) de OpenCode: `config` (añade los comandos y el servidor MCP), `chat.message` (recall y novedades, como una parte sintética del mensaje), `command.execute.before` (ejecuta los comandos), `tool.execute.after` y los eventos `session.*` / `message.*` (la captura), y tres herramientas propias: `mimirsynth_propose_memory`, `mimirsynth_send_draft` y `mimirsynth_drop_draft`. Todos los hooks fallan en abierto: pase lo que pase, OpenCode sigue.

Está construido sobre la librería cliente compartida ([`integrations/shared/typescript`](../shared/typescript)), que va empaquetada dentro al construirlo, y se escribió contra OpenCode 1.19.

## Desarrollo

```bash
npm ci
npm run check   # tipos
npm test        # los hooks y la herramienta de línea de comandos, contra un servidor falso
npm run build   # dist/index.js (el plugin) y dist/cli.js (la herramienta de línea de comandos)
```
`api/tests/test_opencode_plugin.py` prueba los hooks contra una instancia de prueba de MimirSynth y, con `MIMIRSYNTH_TEST_OPENCODE=<opencode>`, OpenCode de verdad con el plugin y un modelo simulado local (`test/mock-llm.mjs`); el workflow `plugin-opencode` ejecuta ambos. Para probar una copia local en OpenCode, pon su carpeta en `"plugin"`: `"file:///ruta/a/integrations/opencode"` (tras `npm run build`).

**Publicar:** cualquier cambio en esta carpeta sube `version` en `package.json` (si no, falla la comprobación `plugin-version`, y npm no deja publicar dos veces la misma versión). Publicar en npm es `npm publish` desde esta carpeta, por alguien con permisos en el scope `@mimirsynth`; `prepack` lo construye antes.
