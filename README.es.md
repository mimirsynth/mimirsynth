<p><img src="web/public/mimirsynth-mark.svg" alt="MimirSynth" width="64" height="64" /></p>

# MimirSynth

[English](README.md) · **Español**

Memoria para agentes de IA basada en el marco cognitivo CoALA, construida sobre un grafo de conocimiento temporal (Graphiti) y con UI propia. Los hechos no se sobrescriben: se invalidan y se conserva el historial.

Estado: **en desarrollo activo** (0.x). Funciona de extremo a extremo, pero la API y el esquema pueden cambiar entre versiones.

## Qué ofrece
- **Memoria temporal:** hechos con fechas de validez, historial y línea temporal; nada se sobrescribe.
- **Brains:** dominios de conocimiento aislados, cada uno con su grafo, su ontología, sus miembros y sus tokens.
- **Cuarentena de propuestas:** lo que escriben los agentes lo revisa un curador (o un decisor automático) antes de entrar al grafo.
- **Recall híbrido** (hechos, texto de episodios y documentos) pensado para inyectarse en el prompt de un agente.
- **Memoria documental:** subida de ficheros, carpetas y wikis (Outline) como fuentes, con búsqueda semántica.
- **Usuarios:** cuentas propias con doble factor, invitaciones y recuperación por correo; OIDC opcional; roles por brain; auditoría.
- **Interfaz web** para explorar el grafo, curar el vocabulario, revisar propuestas y administrar la instancia.
- **Integración con Claude Code:** hook de recall y escritura como propuesta ([`integrations/claude-code`](integrations/claude-code/README.es.md)).

**Guía de usuario completa en la [wiki](https://github.com/MimirSynth/mimirsynth/wiki/Inicio).** Resumen técnico: [instalación](docs/es/INSTALL.md), [configuración](docs/es/CONFIGURATION.md), [conectar agentes](docs/es/AGENTS.md), [arquitectura](docs/es/ARCHITECTURE.md) y [memoria documental](docs/es/DOCUMENTS.md).

## Inicio rápido
Necesitas Docker con Compose y un endpoint compatible con OpenAI para embeddings (p. ej. Ollama con `nomic-embed-text`) y otro para el LLM de extracción.
```bash
git clone https://github.com/MimirSynth/mimirsynth.git && cd mimirsynth
cp .env.example .env     # define POSTGRES_PASSWORD y MIMIRSYNTH_SESSION_SECRET (openssl rand -hex 32)
docker compose --profile bundled up -d --build    # incluye FalkorDB; sin el perfil, apunta MIMIRSYNTH_FALKOR_HOST a uno tuyo
docker compose logs mimirsynth | grep -A3 "FIRST START"    # código del asistente de instalación
```
Abre `http://localhost:8000`, introduce el código y crea la cuenta de administrador. Después configura los proveedores de IA en **Administración**.

## Configuración
El entorno solo lleva lo necesario para arrancar y conectar (tabla de abajo). Todo lo demás —límites de documentos, recall, retención de trabajos, proveedores de IA, carpetas— se cambia en **Administración → Ajustes** (y las demás pestañas) y se aplica sin reiniciar; si una de esas variables existe, solo hace de valor por defecto.

### Variables de entorno
| Variable | Por defecto | Descripción |
|---|---|---|
| `MIMIRSYNTH_FALKOR_HOST` | `localhost` | Host de FalkorDB |
| `MIMIRSYNTH_FALKOR_PORT` | `6379` | Puerto |
| `MIMIRSYNTH_DATABASE_URL` | SQLite local | Plano de control (PostgreSQL en producción) |
| `MIMIRSYNTH_BOOTSTRAP_GRAPHS` | _(vacío)_ | Grafos existentes a adoptar como brains |
| `MIMIRSYNTH_AUTH_MODE` | `local` | `local` (cuentas propias, más OIDC si se configura). `off` solo para desarrollo: sin inicio de sesión |
| `MIMIRSYNTH_STATIC_DIR` | _(vacío)_ | Directorio del build de la web (lo fija la imagen Docker) |

## Desarrollo
```bash
cd api && uv venv && uv pip install -e . && .venv/bin/uvicorn mimirsynth.main:app --port 8010
cd web && npm install && npm run dev      # http://localhost:5173 (proxy /api -> :8010)
```

## El nombre
Mímir es el guardián del pozo del conocimiento (Mímisbrunnr) en la mitología nórdica. Según la Ynglinga saga, Odín conserva su cabeza y la consulta para pedirle consejo: una memoria externa que se consulta. «Synth» alude a la memoria sintética y a la síntesis: el sistema consolida episodios en conocimiento. No tiene relación con Grafana Mimir ni con otros proyectos llamados Mimir.

## Licencia
Apache-2.0. Ver [LICENSE](LICENSE) y [NOTICE](NOTICE). Las dependencias tienen sus propias licencias; FalkorDB, por ejemplo, es *source-available* (SSPL): ver [docs/ARCHITECTURE.md](docs/es/ARCHITECTURE.md#dependencias-y-licencias).

## Contribuir
Lee [CONTRIBUTING.md](docs/es/CONTRIBUTING.md). Para vulnerabilidades, [SECURITY.md](docs/es/SECURITY.md).
