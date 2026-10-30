[English](Claude-Code-integration) · **Español**

# Integración con Claude Code

Hay dos formas de conectar [Claude Code](https://claude.com/claude-code) a un brain, y se pueden combinar:

| Forma | Qué da | Cuándo |
|---|---|---|
| **Servidor MCP** (recomendada) | Claude recibe las herramientas `recall` y `remember` y decide cuándo leer la memoria y cuándo proponer algo | Siempre: una orden y nada que instalar |
| **Hook de recall** | Antes de **cada** prompt, un script consulta el recall e inyecta el contexto, sin que Claude tenga que pedirlo | Cuando quieres la memoria presente en cada turno |

## Por MCP (recomendada)
1. Crea un token del brain con el rol **Colaborador** en [[Mi cuenta]] → **Tokens de API** ([[Conectar agentes]]). Con un token de **Lector** Claude solo puede usar `recall`.
2. Añade el servidor:
   ```bash
   claude mcp add --transport http mimirsynth "https://mimirsynth.ejemplo.com/api/brains/mi-brain/mcp" --header "Authorization: Bearer mst_..."
   ```
   Añade `--scope user` para tenerlo en todos los proyectos, no solo en el actual. Para un segundo brain, añade otro servidor con otro nombre y su propio token.
3. En Claude Code, `/mcp` debería mostrar `mimirsynth` conectado, con sus dos herramientas.

Qué hacen las herramientas:
- **`recall`**: Claude le hace una pregunta a la memoria y recibe los hechos vigentes (y algunos invalidados), fragmentos de episodios y pasajes de documentos, con su procedencia. Si otros brains prestan a este, también llega su contenido, marcado con su origen.
- **`remember`**: Claude propone algo que merece guardarse (una decisión, un cambio de configuración, la causa de un fallo). Con un token de colaborador entra en **cuarentena** hasta que lo aprueba un curador o el decisor ([[Propuestas]]); con uno de curador se aprueba al instante. Los secretos se enmascaran o se bloquean según la política del brain.

Las descripciones de las herramientas siguen las reglas de idioma de [[Conectar agentes]] (sin cabecera `Accept-Language`, el idioma que eligió la persona dueña del token). Para que Claude las use con constancia, díselo en tu `CLAUDE.md` o en las instrucciones del proyecto, por ejemplo: «Antes de responder sobre decisiones, configuración o historia de este proyecto, usa `recall`. Cuando aprendas algo que deba perdurar, proponlo con `remember`.» Pautas de redacción en [[Escribir buena memoria]].

## Hook de recall
El repositorio incluye, en [`integrations/claude-code`](https://github.com/MimirSynth/mimirsynth/tree/main/integrations/claude-code), dos scripts de Python (sin dependencias; solo necesitas Python 3 y acceso a tu servidor):

| Script | Qué hace |
|---|---|
| `mimirsynth_recall.py` | **Hook de lectura.** Antes de cada prompt consulta el recall e **inyecta el contexto** (hechos, fragmentos y pasajes de documentos) |
| `mimirsynth_remember.py` | **Escritura.** Envía un aprendizaje como **propuesta** desde la línea de órdenes |

### Configuración
1. Crea los tokens del brain ([[Conectar agentes]]):
   - uno de **lector**, para el hook de lectura;
   - uno de **colaborador**, para escribir (así lo que se escribe pasa por revisión). Si ya usas MCP con un token de colaborador, no necesitas el script de escritura.
2. Guarda la configuración en `~/.config/mimirsynth/config.json`:
   ```json
   {
     "url": "https://mimirsynth.ejemplo.com",
     "token": "mst_… (lector)",
     "write_token": "mst_… (colaborador)",
     "brain": "mi-brain"
   }
   ```
   Alternativamente, variables de entorno `MIMIRSYNTH_URL`, `MIMIRSYNTH_TOKEN`, `MIMIRSYNTH_WRITE_TOKEN` y `MIMIRSYNTH_BRAIN`. Protege el fichero (`chmod 600`).
3. Copia los scripts a tu máquina y añade el hook en `~/.claude/settings.json`:
   ```json
   {
     "hooks": {
       "UserPromptSubmit": [
         { "hooks": [ { "type": "command", "command": "python3 /ruta/a/mimirsynth_recall.py" } ] }
       ]
     }
   }
   ```

### Cómo se comporta el hook
- Se lanza con cada prompt y consulta el recall del brain (6 hechos, 3 fragmentos, hasta 4000 caracteres).
- **No se activa** con prompts de menos de 12 caracteres ni con órdenes que empiezan por `/`.
- **Falla en abierto:** si el servidor no responde en 4 segundos (`MIMIRSYNTH_TIMEOUT`), no inyecta nada y tu prompt sigue su curso.
- El contexto llega a Claude como información de apoyo, con los documentos marcados como **citas de fuente** (dato, no instrucciones).

### Escribir memoria desde la línea de órdenes
```bash
python3 mimirsynth_remember.py \
  --title "Base de datos migrada a db02" \
  --content "El 19-oct la base de datos de producción pasó al servidor db02" \
  --confidence 0.8
```
- Usa el `write_token` (colaborador): la propuesta entra en **cuarentena** y la revisa un curador o el decisor ([[Propuestas]]). Sin `write_token` usa `token`, que se rechaza (403) si es de lector.
- Con un token de curador queda aprobada y se ingiere al momento.
- `--source text|message|json` indica el tipo de contenido; `--dry-run` muestra la petición sin enviarla.

## Comprobar que funciona
- **MCP:** `/mcp` en Claude Code muestra el servidor y sus herramientas; pregunta algo que el brain sepa y Claude debería llamar a `recall`.
- **Hook:** ejecuta `echo '{"prompt": "¿dónde corre la base de datos de producción?"}' | python3 mimirsynth_recall.py` y deberías ver el contexto.
- En [[Auditoría]] y en [[Mi cuenta]] verás el **último uso** del token.
- Si no llega nada: revisa la URL (sin barra final), el slug del brain y que el token sea de ese mismo brain. Por MCP, un `401` significa que falta la cabecera o que el token no es válido.

## Otros agentes
Cualquier otro cliente MCP se conecta a la misma dirección; el resto usa las llamadas HTTP de [[Conectar agentes]].
