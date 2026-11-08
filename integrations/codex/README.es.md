[English](README.md) · **Español**

# MimirSynth para Codex

Un plugin nativo para el [CLI de Codex](https://github.com/openai/codex) (0.167 o posterior), con las mismas funciones y la misma configuración que el [plugin de Claude Code](../claude-code/README.es.md):
- **Lo que cambió al empezar la sesión.** Los hechos aprendidos e invalidados desde la última sesión (`POST /news`), dentro de `<mimirsynth-news>`.
- **Recall antes de cada prompt.** Un hook pregunta al brain antes de que el modelo lea el prompt e inyecta la respuesta dentro de `<mimirsynth-memory>`, como contexto, no como instrucciones. Tú eliges el tamaño (`max_chars`, 4000) y el tiempo máximo (`timeout`, 4 s). Si el servidor no responde, no se inyecta nada y el prompt sigue; un token caducado o revocado se dice.
- **Cuatro comandos**, como skills de Codex:

| Skill | Qué hace |
|---|---|
| `$mimirsynth:setup` | Te dice cómo configurarlo. Los tokens nunca pasan por la conversación: ejecutas `cli.py setup` en tu terminal, que los pide ocultos |
| `$mimirsynth:status` | Conexión, brain, rol, permisos y caducidad de cada token, versión del servidor, si Codex confía en los hooks, modo de captura, borradores y otra memoria en Codex |
| `$mimirsynth:search` | Recall a demanda, con más resultados |
| `$mimirsynth:remember` | Codex redacta una memoria a partir de la conversación y la propone cuando estás de acuerdo; también revisa los borradores que dejó la captura |

- **Captura opcional de lo que aprendió cada sesión** (desactivada por defecto), leída de los propios ficheros de sesión de Codex.

Está construido sobre la librería cliente compartida, que lleva en `plugin/scripts/mimirsynth_agent/` (una copia de `integrations/shared/python/mimirsynth_agent`), y necesita `python3` en el `PATH` (`python` en Windows), Python 3.8 o posterior.

## Instalación

Un comando, desde el marketplace de este repositorio:

```bash
codex plugin marketplace add mimirsynth/mimirsynth && codex plugin add mimirsynth@mimirsynth
```

Después, una vez:
1. **Configúralo** en una terminal. En Codex, `$mimirsynth:setup` muestra el comando exacto para tu máquina; es
   ```bash
   python3 ~/.codex/plugins/cache/mimirsynth/mimirsynth/<versión>/scripts/cli.py setup
   ```
   Pide la URL y el brain, un token de **lector** para el recall, opcionalmente un token de **colaborador** para proponer, y el modo de captura, y escribe `~/.config/mimirsynth/config.json`, legible solo por ti. Si MimirSynth ya está configurado para otro agente en esta máquina (el plugin de Claude Code, por ejemplo), no hay nada que hacer: el fichero es compartido.
2. **Confía en los hooks.** Codex no ejecuta los hooks de un plugin hasta que confías en ellos: arranca Codex, abre `/hooks` y confía en los tres de `mimirsynth` (SessionStart, UserPromptSubmit, SessionEnd). Codex vuelve a preguntar tras cada actualización del plugin, y mientras tanto no hay recall antes de cada prompt ni novedades: `$mimirsynth:status` lo dice.

Las mismas claves pueden venir de variables de entorno `MIMIRSYNTH_*`, que tienen prioridad, y una entrada de `projects` puede dar a algunas carpetas otro brain con sus propios tokens: ver [`docs/es/AGENT_CLIENT.md`](../../docs/es/AGENT_CLIENT.md).

Para actualizar: `codex plugin marketplace upgrade mimirsynth` y vuelve a confiar en los hooks en `/hooks`. Para quitarlo: `codex plugin remove mimirsynth@mimirsynth`.

### También las herramientas (opcional)

El plugin hace el recall antes de cada prompt por sí solo. Para que además el modelo pueda llamar a las herramientas de MimirSynth (`recall`, `remember`, `facts_about`, `timeline`, `whats_new`…), añade el servidor MCP del brain, con el token en una variable de entorno y no en `config.toml`:

```bash
codex mcp add mimirsynth --url "https://mimirsynth.example.com/api/brains/mi-brain/mcp" --bearer-token-env-var MIMIRSYNTH_TOKEN
```

## Captura de lo que aprendió una sesión (desactivada por defecto)

La decide `capture`:
- **`off`** (por defecto): no se escribe, lee ni envía nada de las sesiones.
- **`draft`**: cada sesión terminada se guarda en esta máquina, ya redactada, hasta que la revisas con `$mimirsynth:remember`.
- **`send`**: al **siguiente** inicio de sesión, cada sesión terminada se convierte en una propuesta.

Cómo funciona con Codex:
- **Qué sesiones:** solo las que empezaron con la captura activada. El hook del prompt anota la sesión y dónde guarda Codex su fichero (`~/.codex/sessions/…/rollout-….jsonl`); las sesiones de antes, o de otra herramienta, nunca se leen. De esas, solo se proponen las que cambiaron ficheros o terminaron con una respuesta sustancial, como mucho **una propuesta por sesión**.
- **Qué contiene:** la tarea (el primer prompt), el resultado (la última respuesta) y los ficheros cambiados (solo las ediciones que Codex aplicó), leídos del fichero de la sesión cuando ha terminado. Nunca la transcripción.
- **Cuándo ha terminado una sesión:** cuando Codex lo dice (el hook SessionEnd) o, si Codex se cerró a la fuerza, cuando su fichero lleva 12 horas sin cambiar. Una sesión reanudada sigue y se vuelve a leer cuando termina.
- **Cómo se envía:** con confianza baja (`capture_confidence`, 0,3), así que espera en **cuarentena**, y solo con un token de **colaborador**: con uno de curador se aprobaría al momento, así que se rechaza y se dice.
- **Secretos:** antes de escribir nada en disco o enviarlo, se redacta con el propio detector del servidor (`scripts/mimirsynth_agent/secretscan.py` es el mismo fichero que `api/mimirsynth/secretscan.py`, y un test los mantiene iguales). Funciona por patrones y no es infalible: lee los borradores si tienes dudas.
- **Dónde viven los registros:** `~/.config/mimirsynth/state/codex/sessions/`, un fichero por sesión, legible solo por ti, borrado a los 14 días.

## Otra memoria

Si las memorias propias de Codex (`[features] memories = true`) u otro plugin o hook que parece de memoria también alimentan a Codex, el inicio de sesión lo dice (no bloquea nada). Los bloques de MimirSynth van marcados para distinguirlos.

## Falla en abierto

Cada llamada tiene el tiempo máximo configurado y cada hook termina limpio pase lo que pase: si MimirSynth está caído, Codex sigue sin memoria. SessionEnd solo marca la sesión como terminada (Codex le da como mucho 3 s); nada sale de la máquina hasta el siguiente inicio.

## Tests

`api/tests/test_codex_plugin.py` comprueba los hooks, el lector de ficheros de sesión y la captura con una API grabada y, con `MIMIRSYNTH_TEST_CODEX` apuntando a un ejecutable `codex`, instala el plugin desde este repositorio en un `CODEX_HOME` desechable y ejecuta el Codex real contra una instancia de prueba, con un sustituto del modelo para no necesitar cuenta. El workflow `plugin-codex` lo ejecuta en la CI.
