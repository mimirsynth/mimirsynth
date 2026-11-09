[English](Claude-Code-integration) · **Español**

# Integración con Claude Code

Hay dos formas de conectar [Claude Code](https://claude.com/claude-code) a un brain, y conviven:

| Forma | Qué da | Cuándo |
|---|---|---|
| **Plugin** (recomendada) | Lo que ha cambiado al empezar la sesión, recall antes de cada prompt, `/mimirsynth:status`, `:search` y `:remember`, y una captura opcional de lo aprendido en cada sesión | Si usas Claude Code a diario: la memoria está en cada turno sin que Claude tenga que pedirla |
| **Servidor MCP** | Claude recibe las herramientas del brain (`recall`, `remember`, `facts_about`…) y decide cuándo leer la memoria y cuándo proponer algo | Solo, sin instalar nada, o junto al plugin para que Claude vuelva a preguntar con otras palabras |

## El plugin

### Instalación
En Claude Code:
```
/plugin marketplace add mimirsynth/mimirsynth
/plugin install mimirsynth@mimirsynth
```
Los hooks necesitan `python3` en el `PATH`.

### Configuración
Ejecuta `/mimirsynth:setup`, que muestra el comando que lo configura en tu terminal:
```bash
python3 ~/.claude/plugins/…/mimirsynth/scripts/cli.py setup
```
Pide la URL y el brain, un token de **lector** para el recall, opcionalmente un token de **colaborador** para proponer, y el modo de captura, y escribe el fichero compartido ([[Configuración de los plugins de agente]]). Los tokens nunca pasan por la conversación. Si MimirSynth ya está configurado para otro agente en esta máquina, no hay nada que hacer.

### Qué hace
| Cuándo | Qué |
|---|---|
| Al empezar la sesión | Los hechos aprendidos e invalidados desde la última sesión, dentro de `<mimirsynth-news>`. Con la captura en `send`, se proponen las sesiones terminadas |
| En cada prompt | El recall del prompt, dentro de `<mimirsynth-memory>`, como contexto y no como instrucciones. Se saltan los prompts de menos de 12 caracteres y los comandos con barra |
| Tras una edición, y cuando Claude se detiene | Con la captura encendida, se anotan para la sesión los ficheros cambiados y la última respuesta |
| Al terminar la sesión | Solo cierra el registro de la sesión: Claude Code da a un plugin 1,5 s, así que nada sale de la máquina hasta el siguiente arranque |

Si MimirSynth no responde en `timeout`, no se inyecta nada y el prompt sigue; un token caducado o revocado se avisa.

### Comandos
| Comando | Qué hace |
|---|---|
| `/mimirsynth:setup` | Te dice cómo configurarlo |
| `/mimirsynth:status` | Conexión, brain, rol, alcance y caducidad de cada token, versión del servidor, modo de captura, borradores y otros hooks de memoria de esta máquina |
| `/mimirsynth:search <consulta>` | Recall a demanda, con más resultados |
| `/mimirsynth:remember [título]` | Claude redacta una memoria a partir de la conversación y la envía cuando estás de acuerdo; sin título, revisa los borradores que dejó la captura |

### Captura
Apagada por defecto; la decide `capture`, con las mismas reglas en todos los plugins ([[Configuración de los plugins de agente]]).

### Qué escribe en tu máquina
- `~/.config/mimirsynth/config.json`, la configuración compartida (lo escribe `setup`).
- Con la captura encendida: un fichero por sesión en la carpeta de datos del plugin (`$CLAUDE_PLUGIN_DATA/sessions`), o en `~/.config/mimirsynth/state/sessions/`, legible solo por ti, que se borra a los 14 días.

Si otro plugin u hook inyecta memoria también, el inicio de sesión lo dice; no bloquea nada, y los bloques de MimirSynth van marcados para distinguirlos.

### Actualizar y quitar
- Actualizar: `claude plugin marketplace update mimirsynth`, después `claude plugin update mimirsynth@mimirsynth` (o **Update now** en `/plugin` → Installed), después `/reload-plugins`.
- Quitar: `/plugin uninstall mimirsynth@mimirsynth`.

## Por MCP
1. Crea un token del brain con el rol **Colaborador** en [[Mi cuenta]] → **Tokens de API** ([[Conectar agentes]]). Con un token de **Lector** Claude solo puede leer.
2. Añade el servidor:
   ```bash
   claude mcp add --transport http mimirsynth "https://mimirsynth.ejemplo.com/api/brains/mi-brain/mcp" --header "Authorization: Bearer mst_..."
   ```
   Añade `--scope user` para tenerlo en todos los proyectos, no solo en el actual. Para un segundo brain, añade otro servidor con otro nombre y su propio token.
3. En Claude Code, `/mcp` debería mostrar `mimirsynth` conectado, con sus herramientas.

Qué hacen las herramientas principales (la lista completa está en [[Conectar agentes]]):
- **`recall`**: Claude le hace una pregunta a la memoria y recibe los hechos vigentes (y algunos invalidados), fragmentos de episodios y pasajes de documentos, con su procedencia. Si otros brains prestan a este, también llega su contenido, marcado con su origen.
- **`remember`**: Claude propone algo que merece guardarse (una decisión, un cambio de configuración, la causa de un fallo). Con un token de colaborador entra en **cuarentena** hasta que lo aprueba un curador o el decisor ([[Propuestas]]); con uno de curador se aprueba al instante. Los secretos se enmascaran o se bloquean según la política del brain.

Las descripciones de las herramientas siguen las reglas de idioma de [[Conectar agentes]] (sin cabecera `Accept-Language`, el idioma que eligió la persona dueña del token). Para que Claude las use con constancia, díselo en tu `CLAUDE.md` o en las instrucciones del proyecto, por ejemplo: «Antes de responder sobre decisiones, configuración o historia de este proyecto, usa `recall`. Cuando aprendas algo que deba perdurar, proponlo con `remember`.» Pautas de redacción en [[Escribir buena memoria]].

## Migrar desde el hook suelto
Antes del plugin, el hook de recall era un script suelto, `mimirsynth_recall.py`, que se añadía a mano a `~/.claude/settings.json`, con `mimirsynth_remember.py` para proponer desde la línea de comandos. Los dos siguen en [`integrations/claude-code`](https://github.com/mimirsynth/mimirsynth/tree/main/integrations/claude-code) y siguen funcionando, pero el plugin hace lo mismo y más:
1. Instala el plugin. Tu `~/.config/mimirsynth/config.json` sigue valiendo, con las mismas claves.
2. Quita el hook `mimirsynth_recall.py` de `~/.claude/settings.json`, o el contexto se inyecta dos veces. `/mimirsynth:status` avisa mientras siga ahí.
3. `mimirsynth_remember.py` puede quedarse para scripts. Dentro de Claude Code, `/mimirsynth:remember` hace lo mismo.

## Comprobar que funciona
- **Plugin:** `/mimirsynth:status` comprueba cada token contra el servidor; después pregunta algo que el brain sepa y la respuesta debería usarlo.
- **MCP:** `/mcp` en Claude Code muestra el servidor y sus herramientas; pregunta algo que el brain sepa y Claude debería llamar a `recall`.
- En [[Auditoría]] y en [[Mi cuenta]] verás el **último uso** del token.

## Solución de problemas
| Síntoma | Qué hacer |
|---|---|
| No hay memoria antes de los prompts | `/mimirsynth:status`: faltan `url`, `brain` o `token`, o `recall` está apagado |
| «python3: command not found» en los hooks | Instala Python 3 y ponlo en el `PATH` |
| El contexto aparece dos veces | El hook suelto `mimirsynth_recall.py` sigue en `settings.json`: quítalo |
| No llega nada | Revisa la URL (sin barra final), el slug del brain y que el token sea de ese mismo brain. Por MCP, un `401` significa que falta la cabecera o que el token no es válido |
| «token caducado» o «revocado» | Crea o rota el token ([[Conectar agentes]]) y vuelve a ejecutar `setup` |

Todos los detalles: [el README del plugin](https://github.com/mimirsynth/mimirsynth/blob/main/integrations/claude-code/README.es.md).

## Otros agentes
Codex, OpenCode, Hermes Agent y OpenClaw tienen plugins nativos propios, con la misma configuración: ver [2. Elige tu agente](Conectar-agentes#2-elige-tu-agente). Cualquier otro cliente MCP se conecta a la misma dirección; el resto usa la API HTTP de [[Conectar agentes]].
