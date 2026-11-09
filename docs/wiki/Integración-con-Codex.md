[English](Codex-integration) · **Español**

# Integración con Codex

Un plugin nativo para el [CLI de Codex](https://github.com/openai/codex) (0.167 o posterior) da a Codex la memoria del brain en cada prompt, con las mismas funciones y la misma configuración que el resto de plugins de agente. Necesita `python3` en el `PATH` (`python` en Windows), Python 3.8 o posterior.

## Instalación
```bash
codex plugin marketplace add mimirsynth/mimirsynth && codex plugin add mimirsynth@mimirsynth
```

## Configuración
Después, una vez:
1. **Configúralo en una terminal.** En Codex, `$mimirsynth:setup` muestra el comando exacto para tu máquina:
   ```bash
   python3 ~/.codex/plugins/cache/mimirsynth/mimirsynth/<versión>/scripts/cli.py setup
   ```
   Pide la URL y el brain, un token de **lector** para el recall, opcionalmente un token de **colaborador** para proponer, y el modo de captura, y escribe el fichero compartido ([[Configuración de los plugins de agente]]). Si MimirSynth ya está configurado para otro agente en esta máquina, no hay nada que hacer.
2. **Confía en los hooks** (ver [abajo](#codex-solo-ejecuta-los-hooks-en-los-que-confías)).

## Qué hace
| Cuándo | Qué |
|---|---|
| Al empezar la sesión | Los hechos aprendidos e invalidados desde la última sesión, dentro de `<mimirsynth-news>`. Con la captura en `send`, se proponen las sesiones terminadas |
| En cada prompt | El recall del prompt, dentro de `<mimirsynth-memory>`, como contexto y no como instrucciones. Se saltan los prompts de menos de 12 caracteres y los comandos con barra |
| Al terminar la sesión | Solo marca la sesión como terminada (Codex da a un hook 3 s como mucho): nada sale de la máquina hasta el siguiente arranque |

Si MimirSynth no responde en `timeout`, no se inyecta nada y el prompt sigue; un token caducado o revocado se avisa.

## Comandos
Son skills de Codex:

| Skill | Qué hace |
|---|---|
| `$mimirsynth:setup` | Te dice cómo configurarlo. Los tokens nunca pasan por la conversación |
| `$mimirsynth:status` | Conexión, brain, rol, alcance y caducidad de cada token, versión del servidor, si Codex confía en los hooks, modo de captura, borradores y otra memoria en Codex |
| `$mimirsynth:search` | Recall a demanda, con más resultados |
| `$mimirsynth:remember` | Codex redacta una memoria a partir de la conversación y la propone cuando estás de acuerdo; también revisa los borradores que dejó la captura |

Para que el modelo pueda llamar también a las herramientas de MimirSynth (`recall`, `remember`, `facts_about`, `timeline`, `whats_new`…), añade el servidor MCP del brain, con el token en una variable de entorno y no en `config.toml`:
```bash
codex mcp add mimirsynth --url "https://mimirsynth.example.com/api/brains/mi-brain/mcp" --bearer-token-env-var MIMIRSYNTH_TOKEN
```

## Captura
Apagada por defecto; la decide `capture` ([[Configuración de los plugins de agente]]). Lo propio de Codex:
- Solo se leen las sesiones que **empezaron con la captura encendida**. El hook del prompt anota la sesión y dónde guarda Codex su fichero (`~/.codex/sessions/…/rollout-….jsonl`); las sesiones anteriores, o las de otra herramienta, nunca se leen.
- La tarea, el resultado y los ficheros cambiados (solo las ediciones que aplicó Codex) salen de ese fichero de sesión cuando la sesión termina.
- Una sesión termina cuando Codex lo dice o, si Codex se cerró a la fuerza, cuando su fichero lleva 12 horas sin cambiar. Una sesión reanudada sigue y se vuelve a leer cuando termina.

## Qué escribe en tu máquina
- `~/.config/mimirsynth/config.json`, la configuración compartida (lo escribe `setup`).
- Con la captura encendida: `~/.config/mimirsynth/state/codex/sessions/`, un fichero por sesión, legible solo por ti, que se borra a los 14 días.
- Nada en la configuración propia de Codex, salvo que añadas tú el servidor MCP.

## Codex solo ejecuta los hooks en los que confías
Codex no ejecuta los hooks de un plugin hasta que confías en ellos. Arranca Codex, abre `/hooks` y confía en los tres de `mimirsynth` (SessionStart, UserPromptSubmit, SessionEnd). Codex vuelve a preguntar **tras cada actualización** del plugin, y hasta entonces no hay recall antes de cada prompt ni novedades: `$mimirsynth:status` lo dice.

Si las memorias propias de Codex (`[features] memories = true`) u otro plugin o hook que parezca de memoria alimentan también a Codex, el inicio de sesión lo dice; no bloquea nada, y los bloques de MimirSynth van marcados para distinguirlos.

## Actualizar y quitar
- Actualizar: `codex plugin marketplace upgrade mimirsynth`, y vuelve a confiar en los hooks en `/hooks`.
- Quitar: `codex plugin remove mimirsynth@mimirsynth`.

## Solución de problemas
| Síntoma | Qué hacer |
|---|---|
| No hay memoria antes de los prompts | `$mimirsynth:status`: no se confía en los hooks (abre `/hooks`), o faltan `url`, `brain` o `token` |
| «python3: command not found» en los hooks | Instala Python 3.8 o posterior y ponlo en el `PATH` (`python` en Windows) |
| «token caducado» o «revocado» | Crea o rota el token ([[Conectar agentes]]) y vuelve a ejecutar `setup` |
| No vuelve nada para una pregunta que el brain sabe | `$mimirsynth:search` con las mismas palabras; comprueba que el token es de ese brain y tiene el alcance Consultar |
| La captura no envía nada | Necesita un `write_token` de colaborador; solo cuentan las sesiones empezadas con la captura encendida |

Todos los detalles: [el README del plugin](https://github.com/mimirsynth/mimirsynth/blob/main/integrations/codex/README.es.md).
