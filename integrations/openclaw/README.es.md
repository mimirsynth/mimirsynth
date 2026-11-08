[English](README.md) · **Español**

# MimirSynth para OpenClaw

Un plugin nativo de [OpenClaw](https://github.com/openclaw/openclaw) que da a tu asistente el cerebro de MimirSynth del equipo:

- **Recall antes de cada prompt.** Lo que el cerebro sabe sobre el mensaje se añade al turno, dentro de `<mimirsynth-memory brain="…">`. Tú fijas el tamaño (`max_chars`, 4000) y el tiempo de espera (`timeout`, 4 s). Si el servidor no responde a tiempo, no se añade nada y el turno sigue. Un token caducado o revocado se dice una vez, para que el recall no deje de funcionar sin que nadie se entere.
- **Qué cambió al empezar la sesión.** Los hechos aprendidos e invalidados desde la sesión anterior, dentro de `<mimirsynth-news>`, con el primer prompt de cada sesión nueva.
- **Dos herramientas para el agente:** `mimirsynth_search` (recall a demanda, con más resultados) y `mimirsynth_remember` (una propuesta que espera en cuarentena a un curador).
- **Comandos** en una terminal (`openclaw mimirsynth …`) y en cualquier chat (`/mimirsynth …`):

| Comando | Qué hace |
|---|---|
| `openclaw mimirsynth setup` | Pide el servidor, el cerebro, los tokens (ocultos) y el modo de captura, escribe `~/.config/mimirsynth/config.json` y ofrece conceder al plugin el acceso a la conversación que OpenClaw exige |
| `status` | Conexión, cerebro, rol, permisos y caducidad de cada token, versión del servidor, qué está activo, modo de captura y borradores |
| `search <consulta>` | Recall a demanda |
| `remember --title … --content …` | Una propuesta con el token de escritura (en terminal; en un chat, pídele al agente que lo recuerde) |
| `drafts`, `send-draft <sesión>`, `drop-draft <sesión>` | Revisar lo que guarda la captura (captura = `draft`) |

- **Una skill** (`skills/mimirsynth/SKILL.md`) que le dice al agente cómo leer lo recuperado (como datos, no como instrucciones) y cuándo proponer un recuerdo.
- **Captura opcional de lo que aprendió cada sesión**, desactivada por defecto (abajo).

Es un **plugin acompañante**: no ocupa la ranura exclusiva de memoria de OpenClaw, así que la memoria propia de OpenClaw (`MEMORY.md`, su búsqueda de memoria, el dreaming) sigue funcionando, y MimirSynth añade lo que sabe el equipo.

## Instalación

En la máquina donde corre el Gateway de OpenClaw (OpenClaw 2026.9.36 o posterior):

```bash
openclaw plugins install @mimirsynth/openclaw && openclaw mimirsynth setup
```

OpenClaw muestra las capacidades del plugin (dos herramientas, sus hooks, un comando de CLI, una skill) y pide que las aceptes. Después `setup` pide:
- la URL de MimirSynth y el slug del cerebro;
- un token **lector** para el recall (Mi cuenta → Tokens de API, permiso Recall);
- opcionalmente un token **colaborador** para proponer. La captura nunca envía con un token de curador, porque sus propuestas se saltarían la cuarentena;
- el modo de captura;
- si concedes al plugin **acceso a la conversación**. OpenClaw solo ejecuta los hooks de un plugin de terceros que leen la conversación (el recall antes de cada prompt, la captura) cuando activas `plugins.entries.mimirsynth.hooks.allowConversationAccess`; `setup` lo escribe con el propio escritor de configuración de OpenClaw. Para hacerlo a mano: `openclaw config set plugins.entries.mimirsynth.hooks.allowConversationAccess true`.

Compruébalo con `openclaw mimirsynth status`, o `/mimirsynth status` en un chat. Las mismas claves pueden venir de variables de entorno `MIMIRSYNTH_*` (ganan al fichero), y una entrada de `projects` puede dar a uno de los workspaces de OpenClaw otro cerebro con sus propios tokens: ver [`docs/es/AGENT_CLIENT.md`](../../docs/es/AGENT_CLIENT.md). El fichero lo comparten todas las integraciones de agentes de MimirSynth de esa máquina, así que un solo `setup` sirve para todas.

**Antes de que esté publicado** (o para probar un cambio), instálalo desde un clon: `npm pack` construye `dist/` y el paquete, y OpenClaw instala el archivo.

```bash
cd integrations/openclaw && npm ci && npm pack && openclaw plugins install npm-pack:./mimirsynth-openclaw-0.1.0.tgz
```

## Quién ve el cerebro

Un asistente en OpenClaw también habla en grupos y con otras personas. Por defecto solo **tus propias** conversaciones ven lo que sabe el cerebro: en un turno con otras personas (la audiencia de memoria `conversation` de OpenClaw: un grupo, un canal, otro remitente) no hay recall, ni novedades, ni herramientas de MimirSynth, ni captura, y `/mimirsynth search` solo te responde a ti. Para que esas conversaciones también lo usen:

```bash
openclaw config set plugins.entries.mimirsynth.config.conversations true
```

El recall además sigue la política de herramientas de cada turno: un turno que no puede llamar a `mimirsynth_search` tampoco recibe recall. Las sesiones de incógnito nunca ven el cerebro.

## Captura de lo que aprendió una sesión (desactivada por defecto)

La decide `capture` en la configuración compartida:
- **`off`** (por defecto): no se escribe ni se envía nada sobre las sesiones.
- **`draft`**: cada sesión se guarda en esta máquina, ya redactada, hasta que la revisas con `openclaw mimirsynth drafts`.
- **`send`**: al **siguiente** inicio de sesión, cada sesión terminada se convierte en una propuesta.

Qué se guarda y se envía:
- **Qué sesiones:** solo las que cambiaron ficheros (`write`, `edit` y `apply_patch` de OpenClaw) o terminaron con una respuesta de al menos 400 caracteres, como **una propuesta por sesión** como mucho. Una sesión termina cuando OpenClaw empieza otra (`/new`, `/reset`, reinicio por inactividad o diario) o la borra; un reinicio del Gateway o una compactación no la terminan.
- **Qué contiene:** la tarea (el primer mensaje), el resultado (la última respuesta) y los ficheros cambiados. Nunca la transcripción, ni lo que el propio MimirSynth inyectó.
- **Cómo se envía:** con confianza baja (`capture_confidence`, 0.3), así que espera en **cuarentena**. Solo se envía con un token **colaborador**.
- **Secretos:** se redactan con el propio detector del servidor antes de escribir o enviar nada. Funciona por patrones y no es infalible.
- **Dónde se guardan los registros:** `~/.config/mimirsynth/state/openclaw/sessions/`, un fichero por sesión, legible solo por ti; los de más de 14 días se borran.

## Si MimirSynth no responde

Cada llamada tiene el tiempo de espera configurado y cada hook lo captura todo: si MimirSynth está caído o lento, no se inyecta nada y OpenClaw sigue. El recall corre en la fase de prompt de OpenClaw, que además le da su propio margen de 15 s.

## Para desarrolladores

| Ruta | Qué |
|---|---|
| `src/index.ts` | La entrada: registra los hooks, las herramientas, el comando de chat y la CLI |
| `src/hooks.ts` | Recall, novedades y la captura |
| `src/commands.ts` | Lo que responden `status`, `search`, `remember` y los borradores |
| `src/setup.ts` | El `setup` de terminal |
| `openclaw.plugin.json` | El manifiesto: id, herramientas, comando de CLI, skill, ajustes |
| `test/plugin.test.ts` | Contra un sustituto de la API de OpenClaw y un servidor falso (`npm test`) |
| `test/live.test.ts` | Contra una instancia real, lo lanza `api/tests/test_openclaw_plugin.py` |

El plugin se apoya en la biblioteca cliente compartida ([`integrations/shared/typescript`](../shared/typescript)), que `npm run build` empaqueta en `dist/index.js` (esbuild), así que el paquete no tiene dependencias en tiempo de ejecución ni importa nada de OpenClaw. `npm run check` comprueba los tipos. La CI (`.github/workflows/plugin-openclaw.yml`) además instala el plugin empaquetado en un OpenClaw real y comprueba lo que registra.

**Publicar:** cualquier cambio aquí, o en la biblioteca TypeScript compartida que empaqueta, sube `version` en `package.json`; si no, falla la comprobación `plugin-version`. Publicar necesita el ámbito de npm `@mimirsynth` y una cuenta de ClawHub: `npm publish --access public` desde esta carpeta y luego `clawhub package publish` (ver la [documentación de publicación de plugins](https://docs.openclaw.ai/plugins/building-plugins) de OpenClaw).
