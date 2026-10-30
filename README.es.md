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
Necesitas Docker con Compose v2 y un endpoint compatible con OpenAI para embeddings (p. ej. Ollama con `nomic-embed-text`) y otro para el LLM de extracción ([qué modelo](docs/es/CONFIGURATION.md#elegir-el-modelo-de-extracción)). Sin esos dos endpoints la instancia arranca, pero no hay nada útil que ver.

En un servidor Linux vacío (Debian, Ubuntu), instala primero `curl` y Docker; en macOS o Windows, instala Docker Desktop. Si usas Ollama en el mismo host Linux, [prepáralo](docs/es/INSTALL.md#preparar-ollama) para que el contenedor llegue a él.
```bash
sudo apt-get update && sudo apt-get install -y curl openssl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER" && newgrp docker    # usar docker sin sudo
docker compose version    # debe responder v2.x
```
Después:
```bash
mkdir mimirsynth && cd mimirsynth
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/docker-compose.yml
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/env.example -o .env
# edita .env: define POSTGRES_PASSWORD y MIMIRSYNTH_SESSION_SECRET (openssl rand -hex 32)
docker compose --profile bundled up -d    # descarga la imagen publicada; incluye FalkorDB (sin el perfil, apunta MIMIRSYNTH_FALKOR_HOST a uno tuyo)
docker compose logs mimirsynth | grep -A3 "FIRST START"    # código del asistente de instalación
```
Abre `http://localhost:8000`, introduce el código y crea la cuenta de administrador. Después, en **Administración**, añade los motores de IA (**Modelo LLM** y **Embeddings**, con «Probar» para comprobarlos) y crea un brain (**Acceso al brain → Crear brain**).

### Conecta tu primer agente
En **Mi cuenta → Tokens de API**, crea un token para ese brain con el rol **Colaborador** (solo se muestra una vez). Con Claude Code, por MCP:
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
| `MIMIRSYNTH_FALKOR_HOST` | `localhost` | Host de FalkorDB |
| `MIMIRSYNTH_FALKOR_PORT` | `6379` | Puerto |
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
