[English](README.md) · **Español**

# MimirSynth para Claude Code

Claude Code se conecta a MimirSynth por el **servidor MCP** que expone cada brain: así el agente tiene `recall` y `remember` como herramientas. Esta carpeta añade el complemento, un **hook de recall** que inyecta la memoria en cada prompt sin que el agente tenga que pedirla, y un script para enviar aprendizajes como propuestas desde la línea de comandos. Tokens, roles y API, en [`docs/es/AGENTS.md`](../../docs/es/AGENTS.md).

## El plugin (recomendado)

La carpeta `plugin/` es un plugin de Claude Code que empaqueta el hook de recall y añade más:
- **Lo que ha cambiado al empezar la sesión.** Trae los hechos aprendidos e invalidados desde la sesión anterior (`POST /news`, la cara REST de `whats_new` del MCP), dentro de `<mimirsynth-news>`.
- **Recall antes de cada prompt.** Como el hook suelto, dentro de `<mimirsynth-memory>`. Se ajusta el tamaño (`max_chars`, 4000) y el tiempo máximo (`timeout`, 4 s). Si el servidor no responde, no se inyecta nada y el prompt sigue. Un token caducado o revocado se avisa.
- **Cuatro comandos:**

| Comando | Qué hace |
|---|---|
| `/mimirsynth:setup` | Explica cómo configurarlo. Los tokens nunca pasan por la conversación: se ejecuta `cli.py setup` en tu terminal, que los pide ocultos |
| `/mimirsynth:status` | Conexión, brain, rol, alcances y caducidad de cada token, versión del servidor, modo de captura, borradores y otros hooks de memoria del equipo |
| `/mimirsynth:search <consulta>` | Recall a demanda, con más resultados |
| `/mimirsynth:remember [título]` | Claude redacta una memoria a partir de la conversación y la envía cuando estás de acuerdo; sin título, revisa los borradores que dejó la captura |

- **Captura opcional de lo aprendido en cada sesión**, que se explica más abajo.

### Instalación

En Claude Code:
```
/plugin marketplace add mimirsynth/mimirsynth
/plugin install mimirsynth@mimirsynth
```
Después se configura en una terminal; `/mimirsynth:setup` muestra la ruta exacta:
```bash
python3 ~/.claude/plugins/…/mimirsynth/scripts/cli.py setup
```
Pide:
- la URL y el brain;
- un token de **lector** para el recall;
- opcionalmente, uno de **colaborador** para proponer;
- el modo de captura.

Lo guarda en `~/.config/mimirsynth/config.json`, que solo puedes leer tú. Las mismas claves pueden venir de variables `MIMIRSYNTH_*`, que tienen prioridad. Los hooks necesitan `python3` en el `PATH`.

El fichero lo comparten todos los plugins de agentes de MimirSynth, y una entrada de `projects` puede dar a algunas carpetas otro brain con sus propios tokens: consulta [`docs/es/AGENT_CLIENT.md`](../../docs/es/AGENT_CLIENT.md). El plugin se apoya en la biblioteca cliente compartida, que lleva en `scripts/mimirsynth_agent/` (una copia de `integrations/shared/python/mimirsynth_agent`).

### Captura de lo aprendido en una sesión (desactivada por defecto)

La decide `capture`:
- **`off`** (por defecto): no se escribe ni se envía nada de las sesiones.
- **`draft`**: cada sesión se guarda en el equipo, ya redactada, hasta que la revisas con `/mimirsynth:remember`.
- **`send`**: al **empezar la siguiente** sesión, cada sesión terminada se convierte en una propuesta.

Qué se guarda y se envía:
- **Qué sesiones:** solo las que cambiaron ficheros o terminaron con una respuesta sustancial, y como mucho **una propuesta por sesión**.
- **Qué contiene:** la tarea (el primer prompt), el resultado (la última respuesta) y los ficheros cambiados. Nunca el transcript.
- **Cómo se envía:** con confianza baja (`capture_confidence`, 0,3), así que espera en **cuarentena**. Solo se envía con un token de **colaborador**: con uno de curador se aprobaría al momento, así que se rechaza y se avisa.
- **Secretos:** antes de escribir nada en disco o enviarlo, se redacta con el propio detector del servidor (`scripts/mimirsynth_agent/secretscan.py` es el mismo fichero que `api/mimirsynth/secretscan.py`, y un test los mantiene iguales). Funciona por patrones y no es infalible: si dudas, lee los borradores.
- **Cuándo sale del equipo:** al empezar la siguiente sesión, no al terminar, porque Claude Code solo da 1,5 s a un plugin al cerrar.

### Otros plugins de memoria

Si otro plugin o hook también inyecta memoria, el inicio de sesión lo avisa (sin bloquear nada). Los bloques de MimirSynth van marcados para distinguirlos. Si `mimirsynth_recall.py` sigue en `settings.json`, también lo dice.

### Pasar de los scripts sueltos

1. Instala el plugin. Tu `~/.config/mimirsynth/config.json` sigue valiendo, con las mismas claves.
2. Quita el hook `mimirsynth_recall.py` de `~/.claude/settings.json`; si no, el contexto se inyecta dos veces. `/mimirsynth:status` lo avisa mientras siga ahí.
3. `mimirsynth_remember.py` puede quedarse para scripts. Dentro de Claude Code, `/mimirsynth:remember` hace lo mismo.

Los scripts sueltos de abajo siguen funcionando igual.

## 1. Conectar por MCP

1. En MimirSynth: Mi cuenta → Tokens de API → crea un token para tu brain. Se recomienda **Colaborador**: puede consultar y proponer, y lo que propone entra en cuarentena hasta que lo apruebe un curador o el decisor. Un token de *Lector* basta si el agente solo debe consultar.
2. Añade el servidor a Claude Code:
   ```bash
   claude mcp add --transport http mimirsynth "https://mimirsynth.example.com/api/brains/mi-brain/mcp" --header "Authorization: Bearer mst_..."
   ```
   Añade `--scope user` para tenerlo en todos los proyectos.
3. En Claude Code, `/mcp` muestra el servidor y sus herramientas:

| Herramienta | Rol | Qué hace |
|---|---|---|
| `recall` | lector | Devuelve el contexto de memoria para una consulta: hechos vigentes e históricos, fragmentos de episodios y pasajes de documentos citados |
| `remember` | colaborador | Propone una memoria (cuarentena para colaboradores, aprobada al instante para curadores) |

El token decide el brain y el rol, así que las herramientas no llevan argumento de brain. Solo se aceptan tokens de API, nunca la sesión del navegador.

## 2. Hook de recall (complemento opcional)

Por MCP, el recall solo ocurre cuando el agente decide llamar a la herramienta. `mimirsynth_recall.py` es un hook `UserPromptSubmit` que consulta MimirSynth **antes de cada prompt** e inyecta el contexto relevante (entre etiquetas `<mimirsynth-memory>`), así el agente siempre empieza con él. Es de solo lectura: basta un token de *Lector* (con el alcance **Consultar**), y también sirve el del MCP. Falla en abierto: si MimirSynth no responde, no inyecta nada. Si el token **caducó o se revocó**, lo dice, con el mensaje de MimirSynth (por ejemplo «token caducado el …»), para que el agente no deje de recordar sin que nadie se entere.

1. Guarda la configuración en `~/.config/mimirsynth/config.json`:
   ```json
   {"url": "https://mimirsynth.example.com", "token": "mst_...", "brain": "mi-brain"}
   ```
   Las variables de entorno `MIMIRSYNTH_URL`, `MIMIRSYNTH_TOKEN` y `MIMIRSYNTH_BRAIN` tienen prioridad sobre el fichero.
2. Añade el hook en `~/.claude/settings.json`:
   ```json
   {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python3 /ruta/a/mimirsynth_recall.py"}]}]}}
   ```

Los prompts de menos de 12 caracteres y los comandos con barra se saltan. Si el servidor no responde en 4 s (`MIMIRSYNTH_TIMEOUT`), no se inyecta nada y el prompt sigue su curso.

Con los dos puestos, el hook trae el contexto a cada prompt y las herramientas MCP permiten al agente volver a consultar con otras palabras o proponer lo que aprende.

## 3. Escribir memoria desde la línea de comandos

Por MCP, el agente propone con `remember`. Para scripts u otros hooks, `mimirsynth_remember.py` envía un aprendizaje como propuesta:

```bash
python3 mimirsynth_remember.py --title "Base de datos migrada a db02" --content "El 19-oct la base de datos de producción pasó al servidor db02" --confidence 0.8
```

- Usa `write_token` de `~/.config/mimirsynth/config.json` (token de API con rol **colaborador**: entra en cuarentena y la aprueba un curador o el decisor). Sin él usa `token`, que si es de lector devuelve 403.
- Con un token de curador queda aprobada y se ingiere al momento. Para agentes se recomienda colaborador.
- `--dry-run` muestra la petición sin enviarla.

No guardes contraseñas ni tokens, solo **dónde** están: lo que tenga forma de credencial se enmascara antes de guardarse o, si el brain lo bloquea, la propuesta se rechaza con un 422. `remember` por MCP aplica las mismas reglas.

## Documentos en el recall

Con la memoria documental, el contexto que devuelve `recall` (herramienta, hook o endpoint `/recall`) puede incluir una sección `## Documentos` con hasta 2 pasajes citados (título, sección, `[doc N, trozo M]`). Solo aparece si hay un pasaje realmente relevante, no pasa de ~600 tokens y se omite si la búsqueda tarda más de 0,6 s. El agente puede pedir más contexto con `GET /api/brains/{slug}/docs/{N}/context?chunk={M}` o el original con `/docs/{N}/file`. Para desactivarlo en una petición, `"docs": 0`; el umbral (Administración → Recuerdo → «Similitud mínima de un pasaje») hay que recalibrarlo si se cambia el modelo de embeddings.
