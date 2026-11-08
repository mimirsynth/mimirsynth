[English](README.md) · **Español**

# MimirSynth para Hermes Agent

Un **proveedor de memoria** de [Hermes Agent](https://github.com/NousResearch/hermes-agent) que conecta el agente con un brain de [MimirSynth](https://github.com/mimirsynth/mimirsynth), la memoria compartida de un equipo:

- **Recall antes de cada turno.** Hermes pregunta a MimirSynth qué sabe sobre tu mensaje y la respuesta llega al modelo dentro de `<mimirsynth-memory brain="…">`, sin que tenga que llamar a ninguna herramienta. Los mensajes cortos («ok», «sigue») y los comandos con barra no se consultan.
- **Qué ha cambiado, al empezar la sesión.** Los hechos que el brain aprendió o dejó de dar por buenos desde tu última sesión llegan una vez, con el primer mensaje, dentro de `<mimirsynth-news>`.
- **Dos herramientas para el agente.** `mimirsynth_search` busca más; `mimirsynth_remember` propone un hecho, una decisión o un procedimiento duradero. La propuesta **espera en cuarentena** hasta que un curador la aprueba.
- **Comandos.** `hermes mimirsynth setup | status | search | remember | drafts` en una terminal, y `/mimirsynth status | search | remember | drafts` en un chat.
- **Captura de sesiones, apagada por defecto.** Si la activas, lo que aprendió una sesión (su tarea, su resultado y los ficheros que cambió; nunca la transcripción) se convierte en una propuesta en cuarentena, o en un borrador para que lo revises.
- **Nunca para al agente.** Cada llamada tiene un tiempo límite corto; si MimirSynth no está o va lento, Hermes sigue sin memoria. Un token caducado o revocado se avisa una vez, para que la memoria no deje de funcionar sin que nadie se entere.

Está hecho sobre la biblioteca compartida de agentes de MimirSynth y lee la misma configuración que el resto de integraciones (Claude Code, Codex, OpenCode, OpenClaw): una sola configuración sirve para todas.

## Instalación

Necesitas un servidor de MimirSynth, un brain y un token de API para él (un token de **lector** para consultar y uno de **colaborador** para proponer; ver [Conectar agentes](https://github.com/mimirsynth/mimirsynth/wiki/Conectar-agentes)). Después, en una terminal:

```bash
hermes plugins install mimirsynth/mimirsynth/integrations/hermes-agent/plugin && hermes memory setup mimirsynth
```

El primer comando instala el plugin en tu perfil de Hermes (`$HERMES_HOME/plugins/mimirsynth`); el segundo pide el servidor, el brain y los tokens (ocultos, nunca por el chat), escribe la configuración compartida y hace de MimirSynth el proveedor de memoria del perfil. Abre una sesión nueva y ya funciona: `hermes mimirsynth status` dice a qué se ha conectado.

Hermes Agent 0.21.4 o posterior. El plugin no tiene más dependencias que la biblioteca estándar de Python.

Para dejar de usarlo, elige otro proveedor con `hermes memory setup` (o `hermes memory off`) y quítalo con `hermes plugins remove mimirsynth`.

## Configuración

`hermes memory setup mimirsynth` (o `hermes mimirsynth setup`) escribe `~/.config/mimirsynth/config.json`, que solo puedes leer tú. Es el fichero que leen todas las integraciones de MimirSynth; sus claves están en [AGENT_CLIENT.md](https://github.com/mimirsynth/mimirsynth/blob/main/docs/es/AGENT_CLIENT.md):

| Clave | Por defecto | Qué es |
|---|---|---|
| `url`, `brain`, `token` | — | El servidor, el slug del brain y un token de API (con lector basta para consultar) |
| `write_token` | `token` | Un token de colaborador, para proponer |
| `timeout` | `4` | Segundos que puede tardar una llamada antes de rendirse |
| `max_chars` | `4000` | Máximo de caracteres que inyecta el recall antes de cada turno |
| `recall`, `news` | activados | Recall antes de cada turno; qué ha cambiado al empezar la sesión |
| `capture` | `off` | `off`, `draft` o `send` (abajo) |
| `projects` | — | Otro brain (y sus tokens) para algunas carpetas |

Cualquier clave puede venir también de una variable `MIMIRSYNTH_<CLAVE>` (`MIMIRSYNTH_URL`, `MIMIRSYNTH_TOKEN`, `MIMIRSYNTH_BRAIN`…), que gana al fichero. Dentro de Hermes se leen a través del ámbito de secretos del propio Hermes, así que un perfil puede tener su propio brain y su token en su `.env` (`$HERMES_HOME/.env`) mientras los demás usan el fichero compartido.

## Comandos

| En una terminal | En un chat | Qué hace |
|---|---|---|
| `hermes mimirsynth setup` | — | Pide el servidor, el brain y los tokens, ocultos, y escribe la configuración |
| `hermes mimirsynth status` | `/mimirsynth status` | Conexión, brain, rol, permisos y caducidad de cada token, versión del servidor, modo de captura, borradores |
| `hermes mimirsynth search <consulta>` | `/mimirsynth search <consulta>` | Recall a demanda, con más resultados que antes de cada turno |
| `hermes mimirsynth remember --title T --content C` | `/mimirsynth remember <título> :: <contenido>` | Propone una memoria (antes se le quitan los secretos); espera a un curador |
| `hermes mimirsynth drafts` | `/mimirsynth drafts` | Las sesiones que la captura guardó para que las revises |
| `hermes mimirsynth send-draft <sesión>` / `drop-draft <sesión>` | lo mismo | Propone una de ellas, o la olvida |

Hermes muestra los comandos `hermes mimirsynth …` mientras MimirSynth es el proveedor de memoria activo.

## Captura de sesiones

| `capture` | Qué pasa |
|---|---|
| `off` | Por defecto. No se escribe ni se envía nada de tus sesiones |
| `draft` | Cada sesión se guarda en esta máquina, ya sin secretos, hasta que la revisas (`hermes mimirsynth drafts`) |
| `send` | Al empezar la sesión **siguiente**, cada sesión terminada que lo merece se convierte en una propuesta, en cuarentena |

Solo merecen la pena las sesiones que cambiaron ficheros (con `write_file` o `patch` de Hermes) o que terminaron con una respuesta de al menos 400 caracteres; como mucho una propuesta por sesión, y solo con un token de **colaborador**: con cualquier otro rol la captura se niega y lo dice, porque la propuesta de un curador se saltaría la cuarentena. Los registros se construyen con los turnos que Hermes pasa a su proveedor de memoria, viven en `$HERMES_HOME/mimirsynth/sessions/` (un JSON por sesión, por perfil de Hermes, que solo puedes leer tú) y se borran a los 14 días. Los subagentes y las ejecuciones programadas (cron) nunca se capturan.

## Privacidad y qué hace en tu máquina

- **Red:** solo habla con el servidor de MimirSynth que configures: tu mensaje (hasta 1.500 caracteres) en cada recall, y lo que tú o el agente decidáis recordar. Con la captura en `send`, un resumen de cada sesión terminada.
- **Secretos:** todo lo que propone o guarda pasa antes por el detector de secretos del propio MimirSynth (tokens, claves, contraseñas y credenciales en URLs se cambian por `[secret removed]`). Funciona por patrones y no es infalible: no pegues secretos.
- **Ficheros:** lee `~/.config/mimirsynth/config.json` (que guarda tus tokens de MimirSynth) y, solo con la captura activada, escribe en `$HERMES_HOME/mimirsynth/sessions/`.
- **Trabajo en segundo plano:** un hilo corto al empezar la sesión (las novedades y los envíos de la captura), acotado por el tiempo límite. Sin telemetría.

## Si algo falla

- `hermes mimirsynth status` comprueba cada token contra el servidor y dice por qué falla.
- No recuerda nada: comprueba que `recall` está activado y que el brain tiene memoria sobre el tema (`hermes mimirsynth search …`). Un servidor que no responde dentro de `timeout` se salta en silencio; `hermes logs errors` dice por qué.
- `hermes memory status` dice si MimirSynth es el proveedor activo y, si no está disponible, qué le falta.

El plugin vive en [`integrations/hermes-agent`](https://github.com/mimirsynth/mimirsynth/tree/main/integrations/hermes-agent) del repositorio de MimirSynth y se versiona con él. Apache-2.0.
