[English](Hermes-Agent-integration) · **Español**

# Integración con Hermes Agent

[Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous Research) tiene MimirSynth como **proveedor de memoria**: el recall del brain llega al modelo antes de cada turno, lo que ha cambiado llega con el primer mensaje de cada sesión y el agente tiene dos herramientas. Hermes Agent 0.21.4 o posterior; el plugin no tiene más dependencias que la biblioteca estándar de Python.

## Instalación
En una terminal:
```bash
hermes plugins install mimirsynth/mimirsynth/integrations/hermes-agent/plugin && hermes memory setup mimirsynth
```
El primer comando instala el plugin en tu perfil de Hermes (`$HERMES_HOME/plugins/mimirsynth`); el segundo lo configura y lo hace proveedor de memoria del perfil.

## Configuración
`hermes memory setup mimirsynth` (o `hermes mimirsynth setup`, que solo escribe el fichero) pide el servidor, el brain, un token de **lector** para consultar y uno de **colaborador** para proponer, ocultos y nunca por el chat, y escribe el fichero compartido ([[Configuración de los plugins de agente]]). Empieza una sesión nueva y ya funciona: `hermes mimirsynth status` dice a qué se conectó.

## Qué hace
| Cuándo | Qué |
|---|---|
| Primer mensaje de una sesión | Los hechos que el brain aprendió o descartó desde tu última sesión, una vez, dentro de `<mimirsynth-news>`. Con la captura en `send`, se proponen las sesiones terminadas, en un hilo corto en segundo plano |
| En cada turno | El recall de tu mensaje, dentro de `<mimirsynth-memory brain="…">`, sin llamar a ninguna herramienta. No se hace recall de los mensajes cortos («vale», «sigue») ni de los comandos con barra |
| En cada turno, con la captura encendida | Se anotan para la sesión la tarea, el resultado y los ficheros cambiados (con `write_file` o `patch` de Hermes) |

Cada llamada tiene un tiempo límite corto: si MimirSynth no está o va lento, Hermes sigue sin memoria. Un token caducado o revocado se avisa una vez.

## Comandos y herramientas
El agente tiene dos herramientas: `mimirsynth_search` busca más, y `mimirsynth_remember` propone un hecho, una decisión o un procedimiento duradero, que espera en cuarentena.

| En una terminal | En un chat | Qué hace |
|---|---|---|
| `hermes mimirsynth setup` | — | Pide el servidor, el brain y los tokens, ocultos, y escribe la configuración |
| `hermes mimirsynth status` | `/mimirsynth status` | Conexión, brain, rol, alcance y caducidad de cada token, versión del servidor, modo de captura, borradores |
| `hermes mimirsynth search <consulta>` | `/mimirsynth search <consulta>` | Recall a demanda, con más resultados que antes de cada turno |
| `hermes mimirsynth remember --title T --content C` | `/mimirsynth remember <título> :: <contenido>` | Propone una memoria (redactada antes); espera a un curador |
| `hermes mimirsynth drafts` | `/mimirsynth drafts` | Las sesiones que la captura guardó para que las revises |
| `hermes mimirsynth send-draft <sesión>` / `drop-draft <sesión>` | lo mismo | Propone una de ellas, o la olvida |

Hermes muestra los comandos `hermes mimirsynth …` mientras MimirSynth es el proveedor de memoria activo.

## Captura
Apagada por defecto; la decide `capture` ([[Configuración de los plugins de agente]]). Lo propio de Hermes: los registros salen de los turnos que Hermes entrega a su proveedor de memoria, uno por perfil de Hermes, y nunca se capturan los subagentes ni las ejecuciones programadas (cron).

## Qué escribe en tu máquina
- `~/.config/mimirsynth/config.json`, la configuración compartida (lo escribe `setup`).
- `memory.provider: mimirsynth` en la configuración de Hermes del perfil (lo escribe `hermes memory setup mimirsynth`).
- Con la captura encendida: `$HERMES_HOME/mimirsynth/sessions/`, un fichero por sesión, legible solo por ti, que se borra a los 14 días.

Solo habla con el servidor de MimirSynth que configures, envía tu mensaje (hasta 1.500 caracteres) en cada recall y no tiene telemetría.

## Un proveedor de memoria por perfil
Hermes usa **un** proveedor de memoria a la vez, el de `memory.provider`. `hermes memory setup mimirsynth` lo pone en `mimirsynth`; si no puede, lo dice, y lo pones tú con `hermes config set memory.provider mimirsynth`. Elegir MimirSynth sustituye al proveedor que tuviera el perfil. `hermes memory status` dice qué proveedor está activo y, si MimirSynth no está disponible, qué le falta.

Cada perfil puede usar otro brain: pon `MIMIRSYNTH_URL`, `MIMIRSYNTH_BRAIN` y `MIMIRSYNTH_TOKEN` (y `MIMIRSYNTH_WRITE_TOKEN`) en su `.env` (`$HERMES_HOME/.env`). Dentro de Hermes se leen con su propio ámbito de secretos y ganan al fichero compartido.

## Actualizar y quitar
- Actualizar: `hermes plugins update mimirsynth`.
- Dejar de usarlo: elige otro proveedor con `hermes memory setup`, o `hermes memory off`.
- Quitar: `hermes plugins remove mimirsynth`.

## Solución de problemas
| Síntoma | Qué hacer |
|---|---|
| No hay memoria en los turnos | `hermes memory status`: MimirSynth no es el proveedor activo, o a la configuración le faltan `url`, `brain` o `token` |
| No existen los comandos `hermes mimirsynth` | Solo aparecen mientras MimirSynth es el proveedor de memoria activo |
| No sale nada de un tema que el brain sabe | `hermes mimirsynth search …`; un servidor que no responde en `timeout` se salta sin avisar, y `hermes logs errors` dice por qué |
| «token caducado» o «revocado» | Crea o rota el token ([[Conectar agentes]]) y vuelve a ejecutar `hermes mimirsynth setup` |
| La captura no envía nada | Necesita un `write_token` de colaborador; los subagentes y el cron nunca se capturan |

Todos los detalles: [el README del plugin](https://github.com/mimirsynth/mimirsynth/blob/main/integrations/hermes-agent/plugin/README.es.md).
