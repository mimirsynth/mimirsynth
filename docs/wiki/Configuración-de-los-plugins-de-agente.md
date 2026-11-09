[English](Agent-plugin-configuration) · **Español**

# Configuración de los plugins de agente

Todos los plugins nativos de agente ([[Integración con Claude Code]], [[Integración con Codex]], [[Integración con OpenCode]], [[Integración con Hermes Agent]], [[Integración con OpenClaw]]) leen **un mismo fichero de configuración** y se comportan igual: recall antes de cada prompt, qué cambió al empezar la sesión, `setup` / `status` / `search` / `remember`, y una captura de sesiones apagada por defecto. Un solo `setup`, en cualquiera de ellos, sirve para todos los agentes de la máquina. Esta página es ese fichero; la página de cada plugin solo cuenta lo propio de su agente.

El contrato completo, para quien escriba un plugin, está en [`docs/es/AGENT_CLIENT.md`](https://github.com/mimirsynth/mimirsynth/blob/main/docs/es/AGENT_CLIENT.md).

## El fichero
`~/.config/mimirsynth/config.json`, en todos los sistemas (Windows incluido), o el que diga **`MIMIRSYNTH_CONFIG`**. Lo escribe el `setup` de cada plugin, que pide los tokens ocultos, en una terminal y nunca por la conversación, y lo deja legible solo por su dueño (`0600`). Volver a ejecutar `setup` conserva lo que no cambies.

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

| Clave | Por defecto | Significado |
|---|---|---|
| `url` | — | El servidor, `https://…` (da igual la `/` final) |
| `brain` | — | El slug del brain |
| `token` | — | Un token de API de ese brain, para el recall. Basta con **lector** con el alcance Consultar |
| `write_token` | `token` | Un token de **colaborador**, para proponer |
| `timeout` | `4` | Segundos que puede tardar una llamada antes de que el plugin la abandone |
| `max_chars` | `4000` | Máximo de caracteres que inyecta el recall antes de cada prompt |
| `recall` | `true` | Recall antes de cada prompt |
| `news` | `true` | Qué cambió en el brain, al empezar la sesión |
| `capture` | `off` | Qué pasa con lo que aprendió una sesión: `off`, `draft` o `send` ([abajo](#captura-de-lo-que-aprendió-una-sesión)) |
| `capture_confidence` | `0.3` | La confianza que declara una propuesta capturada (de 0 a 1) |
| `projects` | — | Otros valores para algunas carpetas ([abajo](#otro-brain-por-carpeta-projects)) |

`url`, `brain` y `token` son lo que necesita un plugin para funcionar; sin ellos no hace nada y lo dice en `status`.

## De dónde sale cada valor
Gana el primero que lo da:
1. la variable de entorno **`MIMIRSYNTH_<CLAVE>`**: `MIMIRSYNTH_URL`, `MIMIRSYNTH_BRAIN`, `MIMIRSYNTH_TOKEN`, `MIMIRSYNTH_WRITE_TOKEN`, `MIMIRSYNTH_CAPTURE`…;
2. la entrada de `projects` de la carpeta de trabajo;
3. el nivel superior del fichero;
4. el valor por defecto.

Un valor vacío (una variable sin definir o en blanco, `""` o `null` en el fichero) cuenta como no dado, así que vale el siguiente. Un fichero que no existe o no es JSON válido cuenta como vacío. Un valor que no se puede leer como su tipo (`"timeout": "pronto"`) vuelve al de por defecto: una errata nunca para a un agente. Los booleanos toman `false`, `off`, `no` y `0` como falso.

Las variables de entorno son la forma de que un agente use otro brain sin tocar el fichero compartido, por ejemplo un perfil de Hermes Agent con su propio `.env`.

## Otro brain por carpeta: `projects`
`projects` asocia una carpeta a un objeto con cualquiera de las claves de arriba. Cuando el agente trabaja en esa carpeta o por debajo, sus valores sustituyen a los del nivel superior; si varias carpetas contienen la de trabajo, gana la más profunda. Las carpetas son absolutas (una `~` al principio es la carpeta personal), se comparan sin seguir enlaces y, en Windows, sin distinguir mayúsculas. Una carpeta cuyo nombre solo empieza igual no cuenta: `/trabajo` no contiene `/trabajos`. Las variables de entorno siguen ganando.

Cada token vale para un brain, así que una entrada que cambia `brain` trae el `token` y el `write_token` de ese brain: si no, se usa el token del nivel superior y el servidor responde 403. Los tokens se quedan en este fichero, nunca en el repositorio.

## Tokens de lector y de colaborador
Un plugin usa hasta dos tokens del mismo brain, creados en [[Mi cuenta]] → **Tokens de API** ([[Conectar agentes]]):

| Clave | Rol | Para qué |
|---|---|---|
| `token` | **Lector** (alcance Consultar; añade Documentos para recibir pasajes) | El recall antes de cada prompt, qué cambió, `search`, `status` |
| `write_token` | **Colaborador** (alcance Proponer) | `remember` y las propuestas de la captura, que esperan en cuarentena a un curador |

Sin `write_token`, las propuestas van con `token`, y un token de lector no puede proponer. Un token de colaborador en `token` sirve para las dos cosas. No des a un plugin un token de **curador**: sus propuestas se saltarían la cuarentena, así que la captura se niega a enviar con él y lo dice. `status` muestra el rol, el alcance y la caducidad de cada token, y un token caducado o revocado se avisa en el agente, para que la memoria nunca deje de funcionar sin que nadie lo note.

## Captura de lo que aprendió una sesión
| `capture` | Qué pasa |
|---|---|
| `off` | Por defecto. No se escribe ni se envía nada de las sesiones |
| `draft` | Cada sesión se guarda en esta máquina, ya redactada, hasta que la revises (`remember` sin título, o el comando `drafts` del plugin) |
| `send` | Al empezar la sesión **siguiente**, cada sesión terminada que lo merezca se convierte en una propuesta, en cuarentena |

`drafts` se lee como `draft` y `auto` como `send`; cualquier otro valor es `off`. Las reglas son las mismas en todos los plugins:
- **Qué sesiones:** solo las que cambiaron ficheros o acabaron con una respuesta de al menos 400 caracteres; como mucho **una propuesta por sesión**.
- **Qué lleva:** la tarea (el primer prompt, hasta 500 caracteres), el resultado (la última respuesta, hasta 3000) y los ficheros cambiados (los 20 primeros). Nunca la transcripción.
- **La propuesta:** se llama «`<Agente>: <proyecto> — <primera línea de la tarea>`», con `capture_confidence` (0,3), para que la mire un curador o el decisor.
- **Solo con un token de colaborador**, como arriba.
- **Secretos:** todo se redacta antes de escribirse en disco o enviarse, con el mismo detector de secretos del servidor. Funciona por patrones y no es infalible: lee los borradores si tienes dudas.
- **Dónde viven los registros:** un fichero por sesión, legible solo por ti, en `~/.config/mimirsynth/state/<agente>/sessions/` salvo que el agente dé al plugin una carpeta propia (la página de cada plugin dice dónde). Los registros de más de 14 días se borran.

## Versiones de los plugins y actualizaciones
Cada plugin tiene su propia versión, que sube cada vez que cambia algo en su carpeta; un agente solo actualiza un plugin instalado cuando esa versión sube. Cada agente guarda su propia copia, así que cada uno se actualiza por separado:

| Agente | Actualizar |
|---|---|
| Claude Code | `claude plugin marketplace update mimirsynth`, después `claude plugin update mimirsynth@mimirsynth` (o **Update now** en `/plugin` → Installed), después `/reload-plugins` |
| Codex | `codex plugin marketplace upgrade mimirsynth`, y vuelve a confiar en los hooks en `/hooks` |
| OpenCode | OpenCode comprueba al arrancar los plugins que figuran sin versión; `opencode plugin update @mimirsynth/opencode` instala la nueva |
| Hermes Agent | `hermes plugins update mimirsynth` |
| OpenClaw | Con el Gateway parado, `openclaw plugins update mimirsynth` |

El fichero de configuración no cambia con una actualización: un plugin más nuevo lee las mismas claves.

## Ver también
- [[Conectar agentes]]: tokens, roles, alcances, el servidor MCP y la API HTTP.
- [[Escribir buena memoria]]: qué merece la pena proponer.
