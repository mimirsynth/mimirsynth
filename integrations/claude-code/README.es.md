[English](README.md) · **Español**

# MimirSynth para Claude Code

Claude Code se conecta a MimirSynth por el **servidor MCP** que expone cada brain: así el agente tiene `recall` y `remember` como herramientas. Esta carpeta añade el complemento, un **hook de recall** que inyecta la memoria en cada prompt sin que el agente tenga que pedirla, y un script para enviar aprendizajes como propuestas desde la línea de comandos. Tokens, roles y API, en [`docs/es/AGENTS.md`](../../docs/es/AGENTS.md).

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

Por MCP, el recall solo ocurre cuando el agente decide llamar a la herramienta. `mimirsynth_recall.py` es un hook `UserPromptSubmit` que consulta MimirSynth **antes de cada prompt** e inyecta el contexto relevante (entre etiquetas `<mimirsynth-memory>`), así el agente siempre empieza con él. Es de solo lectura: basta un token de *Lector*, y también sirve el del MCP.

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
