[English](OpenClaw-integration) · **Español**

# Integración con OpenClaw

[OpenClaw](https://github.com/openclaw/openclaw) usa MimirSynth con un **plugin acompañante** nativo: no ocupa la ranura de memoria exclusiva de OpenClaw, así que la memoria propia de OpenClaw (`MEMORY.md`, su búsqueda de memoria, el *dreaming*) sigue funcionando, y MimirSynth añade lo que sabe el equipo. OpenClaw 2026.9.36 o posterior.

## Instalación
En la máquina donde corre el Gateway de OpenClaw:
```bash
openclaw plugins install npm:@mimirsynth/openclaw && openclaw mimirsynth setup
```
El plugin está en npm, no en ClawHub, y por eso lleva el prefijo `npm:`. OpenClaw avisa de que el origen queda fuera de la revisión de ClawHub y pide que lo confirmes; después muestra las capacidades del plugin (dos herramientas, sus hooks, un comando de la CLI, una skill) y pide que las aceptes.

Para probar un cambio desde un clon: `cd integrations/openclaw && npm ci && openclaw plugins install "npm-pack:./$(npm pack | tail -1)"`.

## Configuración
`openclaw mimirsynth setup` pide, en la terminal y nunca por un chat, la URL, el brain, un token de **lector** para el recall, opcionalmente un token de **colaborador** para proponer (ocultos) y el modo de captura, y escribe el fichero compartido ([[Configuración de los plugins de agente]]). Después ofrece conceder el acceso a la conversación que exige OpenClaw ([abajo](#acceso-a-la-conversación)). Compruébalo con `openclaw mimirsynth status`, o `/mimirsynth status` en un chat.

## Qué hace
| Cuándo | Qué |
|---|---|
| Primer prompt de una sesión nueva | Los hechos aprendidos e invalidados desde la última sesión, dentro de `<mimirsynth-news>`. Con la captura en `send`, se proponen las sesiones terminadas |
| En cada prompt | El recall del mensaje, dentro de `<mimirsynth-memory brain="…">`, añadido al turno. Se saltan los prompts de menos de 12 caracteres y los comandos con barra |
| Al terminar una sesión (`/new`, `/reset`, reinicio por inactividad o diario, borrado) | Con la captura encendida, la sesión se cierra y se guarda o se pone en cola |

Cada llamada tiene el tiempo límite configurado, además del presupuesto propio de 15 s que da OpenClaw a la fase del prompt: si MimirSynth no está o va lento, no se inyecta nada y el asistente sigue. Un token caducado o revocado se avisa una vez.

## Comandos y herramientas
El agente tiene dos herramientas, `mimirsynth_search` (recall a demanda, con más resultados) y `mimirsynth_remember` (una propuesta que espera en cuarentena), y una skill que le dice que lea lo recuperado como datos y no como instrucciones, y cuándo proponer una memoria.

| Comando | Qué hace |
|---|---|
| `openclaw mimirsynth setup` | Pide el servidor, el brain, los tokens (ocultos) y el modo de captura, y ofrece el acceso a la conversación |
| `status` | Conexión, brain, rol, alcance y caducidad de cada token, versión del servidor, qué está encendido, modo de captura y borradores |
| `search <consulta>` | Recall a demanda |
| `remember --title … --content …` | Una propuesta con el token de escritura (en la terminal; en un chat, pide al agente que lo recuerde) |
| `drafts`, `send-draft <sesión>`, `drop-draft <sesión>` | Revisar lo que guarda la captura (capture = `draft`) |

Funcionan en una terminal (`openclaw mimirsynth …`) y en cualquier chat (`/mimirsynth …`).

## Captura
Apagada por defecto; la decide `capture` ([[Configuración de los plugins de agente]]). Lo propio de OpenClaw:
- Los ficheros cambiados son los de `write`, `edit` y `apply_patch` de OpenClaw.
- Una sesión termina cuando OpenClaw empieza otra (`/new`, `/reset`, reinicio por inactividad o diario) o la borra; un reinicio o una compactación no la terminan.
- Lo que inyectó el propio MimirSynth nunca entra en el registro.

## Qué escribe en tu máquina
- `~/.config/mimirsynth/config.json`, la configuración compartida (lo escribe `setup`).
- `plugins.entries.mimirsynth.hooks.allowConversationAccess` en la configuración de OpenClaw, si lo aceptas en `setup`.
- Con la captura encendida: `~/.config/mimirsynth/state/openclaw/sessions/`, un fichero por sesión, legible solo por ti, que se borra a los 14 días.

## Acceso a la conversación
OpenClaw solo ejecuta los hooks de un plugin de terceros que leen la conversación (el recall antes de cada prompt, la captura) cuando lo permites. `setup` ofrece escribirlo con el propio escritor de configuración de OpenClaw; a mano:
```bash
openclaw config set plugins.entries.mimirsynth.hooks.allowConversationAccess true
```

## Quién ve el brain
Por defecto solo **tus propias** conversaciones ven lo que sabe el brain. En un turno con otras personas (la audiencia de memoria `conversation` de OpenClaw: un grupo, un canal, otro remitente) no hay recall, ni novedades, ni herramientas de MimirSynth, ni captura, y `/mimirsynth search` solo te responde a ti. Para que esas conversaciones lo usen también:
```bash
openclaw config set plugins.entries.mimirsynth.config.conversations true
```
El recall sigue además la política de herramientas de cada turno: un turno que no puede llamar a `mimirsynth_search` tampoco recibe recall. El plugin añade sus herramientas a los perfiles de herramientas de OpenClaw; si mantienes una lista `tools.allow` explícita, añádelas con `openclaw config set tools.alsoAllow '["mimirsynth"]' --strict-json --merge`. Las sesiones de incógnito nunca ven el brain.

## Actualizar y quitar
- Actualizar: con el Gateway parado, `openclaw plugins update mimirsynth`.
- Quitar: `openclaw plugins uninstall mimirsynth`.

## Solución de problemas
| Síntoma | Qué hacer |
|---|---|
| No hay memoria antes de los prompts | `openclaw mimirsynth status`: falta el acceso a la conversación, faltan `url`, `brain` o `token`, o es una conversación con otras personas |
| El recall funciona en un chat directo pero no en un grupo | Es lo esperado: pon `plugins.entries.mimirsynth.config.conversations` a `true` |
| El modelo no recibe las herramientas | Una lista `tools.allow` explícita: añádelas con `tools.alsoAllow` (arriba). El log del Gateway lo dice una vez por sesión |
| «token caducado» o «revocado» | Crea o rota el token ([[Conectar agentes]]) y vuelve a ejecutar `openclaw mimirsynth setup` |
| La captura no envía nada | Necesita un `write_token` de colaborador; una sesión se envía al empezar la sesión siguiente |

Todos los detalles: [el README del plugin](https://github.com/mimirsynth/mimirsynth/blob/main/integrations/openclaw/README.es.md).
