<p><img src="web/public/mimirsynth-mark.svg" alt="MimirSynth" width="64" height="64" /></p>

# MimirSynth

[English](README.md) · **Español**

Memoria para agentes de IA basada en el marco cognitivo CoALA, construida sobre un grafo de conocimiento temporal (Graphiti) y con UI propia. Los hechos no se sobrescriben: se invalidan y se conserva el historial.

Estado: **en desarrollo activo** (0.x). Funciona de extremo a extremo, pero la API y el esquema pueden cambiar entre versiones.

## Qué ofrece
**Una memoria que conserva su historia**
- **Hechos temporales:** cada hecho tiene fechas de validez; cuando deja de ser cierto se invalida, nunca se sobrescribe, así que puedes preguntar qué se sabía en cualquier momento.
- **Brains:** dominios de conocimiento aislados, cada uno con su grafo, su ontología, sus miembros y sus tokens. Un brain puede **prestar acceso de lectura** a otro (federación), con caducidad y revocable en cualquier momento.
- **Paquetes de ontología** (general, infraestructura, proyectos de equipo, personal y familia, conocimiento de software), versionados y actualizables sin perder tus propios cambios.

**Lo que entra se revisa**
- **Cuarentena de propuestas:** lo que escriben los agentes espera a un curador o a un decisor automático que lo juzga según el ámbito del brain.
- **Detector de secretos:** las credenciales en propuestas y documentos se tapan, se bloquean o se señalan, según elija cada brain.
- **Herramientas de mantenimiento:** corrector de tipos, fusión de duplicados, alias de relaciones y **contradicciones** entre hechos vigentes en relaciones de un solo valor.

**Recall para agentes**
- **Recall híbrido** de hechos, texto de episodios y pasajes de documentos, listo para inyectarse en el prompt de un agente y en el idioma de quien pregunta.
- **Servidor MCP propio** (`recall` y `remember`), API REST e [integración con Claude Code](integrations/claude-code/README.es.md).
- **Consultas de referencia** por brain para medir la calidad del recall y detectar empeoramientos, por ejemplo al cambiar el modelo de embeddings, algo que se hace desde la interfaz.

**Documentos**
- Sube ficheros o conecta carpetas y wikis (Outline, Confluence, Notion) como fuentes; los duplicados se detectan y se indexan una sola vez.

**Interfaz web y administración**
- Explora el grafo (2D, radial, árbol y 3D, con halos que muestran de dónde vino cada conocimiento), haz preguntas, revisa propuestas y cura el vocabulario. En **castellano e inglés**.
- Cuentas propias con doble factor y **llaves de acceso** (passkeys), varios proveedores OIDC con roles por grupo, roles por brain y registro de auditoría.
- **Notificaciones** en la aplicación y por Telegram, ntfy, Gotify, webhook o correo; `update.sh` para hacer copia, actualizar y volver atrás en un paso.

**Guía de usuario completa en la [wiki](https://github.com/MimirSynth/mimirsynth/wiki/Inicio)**, en castellano y en inglés. Documentación técnica: [instalación](docs/es/INSTALL.md), [configuración](docs/es/CONFIGURATION.md), [conectar agentes](docs/es/AGENTS.md), [arquitectura](docs/es/ARCHITECTURE.md), [ontología](docs/es/ONTOLOGY.md), [memoria documental](docs/es/DOCUMENTS.md), [federación](docs/es/FEDERATION.md) y [notificaciones](docs/es/NOTIFICATIONS.md).

## Inicio rápido
¿Empiezas con agentes de IA? **[Tus primeros 15 minutos](https://github.com/MimirSynth/mimirsynth/wiki/Tus-primeros-15-minutos)** te lleva de un equipo vacío a un agente que recuerda, con cada paso explicado.

Necesitas Docker y dos endpoints compatibles con OpenAI: uno para embeddings y otro para el LLM de extracción ([qué modelo](docs/es/CONFIGURATION.md#elegir-el-modelo-de-extracción)). El instalador puede arrancar un Ollama incluido para los embeddings. Sin LLM la instancia arranca, pero las propuestas aprobadas no se convierten en memoria.

Un comando instala MimirSynth, lo arranca y abre el navegador en el asistente de primer arranque. En Linux o macOS:
```bash
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash
```
En Windows, en PowerShell, con Docker Desktop:
```powershell
irm https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.ps1 | iex
```
En Linux ofrece instalar Docker si falta; en macOS y Windows instala antes [Docker Desktop](https://docs.docker.com/desktop/). Pregunta si arrancar un FalkorDB incluido o usar tu propio FalkorDB o Neo4j, y si arrancar un Ollama incluido para los embeddings; genera los secretos y muestra la dirección y el código de primer arranque. Opciones sin preguntas, sumas de comprobación e instalación manual: [docs/es/INSTALL.md](docs/es/INSTALL.md).

En el navegador, el asistente de configuración sigue desde ahí: la cuenta de administrador (con el código), la base de datos del grafo, los embeddings y el LLM (cada uno con su prueba de conexión), el primer brain, un token para tu agente y su conexión.

### Conecta tu primer agente
El último paso del asistente, también en **Administración → Brain → Conectar un agente**, da lo que hay que pegar para Claude Code, Codex, OpenCode, Hermes Agent, OpenClaw o cualquier cliente MCP, ya con el servidor, el brain y un token, y se pone en verde con la primera llamada del agente. A mano, con un token de **Colaborador** de **Mi cuenta → Tokens de API** (solo se muestra una vez) y Claude Code por MCP:
```bash
claude mcp add --transport http mimirsynth "http://localhost:8000/api/brains/mi-brain/mcp" --header "Authorization: Bearer mst_..."
```
El agente ya puede leer la memoria (`recall`) y proponer hechos nuevos (`remember`). Lo que propone un colaborador queda en cuarentena, en **Propuestas**, hasta que lo aprueba un curador o el decisor. Otros agentes, la API HTTP y el hook de recall de Claude Code: [docs/es/AGENTS.md](docs/es/AGENTS.md).

En producción, apunta un monitor externo a `/api/health`: los avisos de la propia instancia no pueden informar de la caída de PostgreSQL ([vigilancia](docs/es/INSTALL.md#vigilar-la-instancia)).

## Configuración
El entorno solo lleva lo necesario para arrancar y conectar (tabla de abajo). Todo lo demás —límites de documentos, recall, retención de trabajos, proveedores de IA, carpetas— se cambia en **Administración** y se aplica sin reiniciar; si una de esas variables existe, solo hace de valor por defecto.

### Variables de entorno
| Variable | Por defecto | Descripción |
|---|---|---|
| `MIMIRSYNTH_GRAPH_BACKEND`, `MIMIRSYNTH_FALKOR_HOST`, `MIMIRSYNTH_NEO4J_URI` | _(vacío)_ | Una base de datos de grafos existente. Vacías: la guardada en Administración → Base de datos del grafo o el FalkorDB incluido ([detalles](docs/es/CONFIGURATION.md#base-de-datos-de-grafos)) |
| `MIMIRSYNTH_FALKOR_PORT` | `6379` | Puerto de un FalkorDB existente |
| `MIMIRSYNTH_DATABASE_URL` | SQLite local | Plano de control (PostgreSQL en producción) |
| `MIMIRSYNTH_BOOTSTRAP_GRAPHS` | _(vacío)_ | Grafos existentes a adoptar como brains |
| `MIMIRSYNTH_AUTH_MODE` | `local` | `local` (cuentas propias, más OIDC si se configura). `off` solo para desarrollo: sin inicio de sesión |
| `MIMIRSYNTH_STATIC_DIR` | _(vacío)_ | Directorio del build de la web (lo fija la imagen Docker) |

## El nombre
Mímir es el guardián del pozo del conocimiento (Mímisbrunnr) en la mitología nórdica. Según la Ynglinga saga, Odín conserva su cabeza y la consulta para pedirle consejo: una memoria externa que se consulta. «Synth» alude a la memoria sintética y a la síntesis: el sistema consolida episodios en conocimiento. No tiene relación con Grafana Mimir ni con otros proyectos llamados Mimir.

## Licencia
Apache-2.0. Ver [LICENSE](LICENSE) y [NOTICE](NOTICE). Las dependencias tienen sus propias licencias; FalkorDB, por ejemplo, es *source-available* (SSPL): ver [docs/ARCHITECTURE.md](docs/es/ARCHITECTURE.md#dependencias-y-licencias).

## Contribuir
Lee [CONTRIBUTING.md](docs/es/CONTRIBUTING.md). El proyecto trabaja en inglés, pero puedes abrir *issues* y *discussions* en castellano: alguien del equipo añadirá el título en inglés. Para vulnerabilidades, [SECURITY.md](docs/es/SECURITY.md).
