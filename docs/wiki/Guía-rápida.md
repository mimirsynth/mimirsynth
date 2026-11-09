[English](Quick-start) · **Español**

# Guía rápida

De una máquina vacía a una memoria funcionando con un agente conectado, en unos 15 minutos, para quien conoce Docker. Si los agentes, Docker o los tokens son nuevos para ti, sigue mejor [[Tus primeros 15 minutos]]: el mismo camino, con cada paso explicado.

**Necesitas:**
- **Docker con Compose v2.** En Linux el instalador se ofrece a instalarlo; en macOS y Windows, instala antes [Docker Desktop](https://docs.docker.com/desktop/).
- Un endpoint **compatible con OpenAI** para **embeddings** y otro para el **LLM** que extrae los hechos. Pueden ser locales o de un proveedor en la nube, y son independientes: embeddings en local y un LLM por API es una combinación válida. El instalador puede arrancar un Ollama incluido para los embeddings. Sin LLM la instancia arranca, pero las propuestas aprobadas no se ingieren.

## 1. Instala
En Linux o macOS:
```bash
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash
```
En Windows, en PowerShell, con Docker Desktop en marcha:
```powershell
irm https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.ps1 | iex
```
Comprueba Docker, pregunta si arrancar un FalkorDB incluido o usar tu propio FalkorDB o Neo4j, y si arrancar un Ollama incluido para los embeddings (con `nomic-embed-text`). Escribe `docker-compose.yml` y `.env` con secretos generados en `~/mimirsynth`, arranca la pila, muestra la dirección y el **código de inicio** y abre el navegador. Sin preguntas: `… | bash -s -- --yes --ollama`. Todas las opciones, las sumas de comprobación y la instalación manual: [[Instalación]].

**Si los modelos van en tu propio Ollama**, descárgalos antes (`ollama pull nomic-embed-text` y un modelo de extracción, ver el paso 2). Con Ollama en el **mismo host Linux**, haz que escuche en todas las interfaces para que el contenedor llegue a él: ver [Preparar Ollama](Instalaci%C3%B3n#preparar-ollama).

## 2. Sigue el asistente de configuración
<!-- TODO(#361): contrastado con el código del asistente; comparar con el apartado «For the wiki guide (#365)» del PR de #361 cuando se fusione. -->
En el navegador, introduce el código de inicio y crea la cuenta de administrador. La **Configuración inicial** (`/configuracion`) recorre después el resto y retoma donde lo dejaste, desde cualquier dispositivo:
1. **Tu cuenta** (ya hecha).
2. **Base de datos del grafo:** la página de Administración → Base de datos del grafo, con su prueba de conexión, el cambio de conexión y la adopción de grafos existentes. No se puede saltar: **Siguiente** solo pasa con la prueba superada.
3. **Embeddings:** **Ollama en local** (lo busca, lista sus modelos y puede descargar `nomic-embed-text`) o **Un servicio compatible con OpenAI** (URL base, clave, modelo). No se puede saltar. El modelo tiene que coincidir con la dimensión del índice (768 por defecto); para otro, el paso te manda a **Reindexar**.
4. **Modelo LLM:** los mismos dos tipos de endpoint. Se puede saltar, con un recordatorio en el inicio hasta que haya uno.
5. **Decisor** (opcional).
6. **Tu primer brain:** un nombre (el slug sale de él), o un brain que ya existe o que adoptaste.
7. **Token de API:** rol Colaborador, válido 90 días, ya puesto en el paso siguiente.
8. **Conecta tu agente** (el paso 3 de abajo): se pone en verde tras el primer recall del agente, y **Terminar** lleva al inicio con o sin él.

**Configurar a mano** cierra el asistente del todo; el botón **Asistente de configuración**, arriba en Administración, lo vuelve a abrir.

Qué modelo de extracción: en local, un modelo *instruct* de unos **14B parámetros o más** (p. ej. `qwen2.5:14b-instruct`, unos 10 GB de memoria); por API, un modelo pequeño y barato con salida estructurada. Los de 4B o menos bastan para probar la instalación, no para una memoria que quieras conservar: espera entidades mal formadas o que se pierden. Evita los modelos que «razonan» por defecto, salvo que lo desactives. Ver [[Proveedores de IA]].

> **Elige con cuidado el modelo de embeddings.** Se puede cambiar después (**Reindexar** en Administración → Embeddings), pero eso recalcula todos los vectores de todos los brains. El índice de texto se crea con 768 dimensiones salvo que `MIMIRSYNTH_EMBEDDING_DIM` diga otra cosa antes del primer arranque: ver [La dimensión de los embeddings no coincide](Soluci%C3%B3n-de-problemas#la-dimensi%C3%B3n-de-los-embeddings-no-coincide).

Al terminar el asistente aparece un **recorrido guiado** de ocho pasos por la navegación, el selector de brain, las propuestas, el grafo, Preguntar y la administración. Sale una vez por persona; se cierra con Escape o con **Saltar recorrido**, y el **menú de ayuda** (el signo de interrogación abajo en la barra lateral) lo vuelve a poner.

## 3. Conecta tu primer agente
**Administración → Brain → Conectar un agente** (el último paso del asistente) da, para Claude Code, Codex, OpenCode, Hermes Agent, OpenClaw o cualquier cliente MCP, lo que hay que pegar, ya con el servidor, el brain y un token, y se pone en verde con la primera llamada del agente. A mano, con Claude Code por MCP y un token de **Colaborador** de **Mi cuenta → Tokens de API**:
```bash
claude mcp add --transport http mimirsynth "http://localhost:8000/api/brains/mi-brain/mcp" --header "Authorization: Bearer mst_..."
```
El agente ya puede leer la memoria (`recall`) y proponer hechos nuevos (`remember`). Lo que propone un colaborador queda en cuarentena en **Propuestas** hasta que lo aprueba un curador o el decisor. Otros agentes y la API HTTP: [[Conectar agentes]]; las opciones de Claude Code: [[Integración con Claude Code]].

## 4. Primera memoria y primera pregunta
Pide al agente que recuerde un dato concreto, con nombres y fechas exactas («El 12 de octubre migramos la base de datos de producción al servidor db02»), o escríbelo tú en **Propuestas → nueva propuesta** (como administrador se aprueba al enviarla). Aprueba la propuesta del agente en **Propuestas → Por revisar**; la ingesta corre en **Trabajos**, y después los hechos están en **Hechos**, **Diario** y **Grafo**. En **Preguntar**, escribe «¿dónde está la base de datos de producción?» para ver los hechos, los fragmentos de los textos originales y el bloque de contexto que recibiría un agente ([[Preguntar]]).

La lista **Para empezar** de la pantalla de inicio marca cada uno de estos pasos cuando ocurre y sugiere los siguientes.

## 5. (Opcional) Producción, documentos, usuarios y correo
- Ponlo detrás de HTTPS ([[HTTPS y proxy inverso]]) y apunta un monitor externo a `/api/health`: los avisos integrados no pueden avisar de que se ha caído PostgreSQL ([Vigilar la instancia](Instalaci%C3%B3n#vigilar-la-instancia)).
- Sube ficheros o conecta una carpeta o wiki en **Conocimiento** ([[Conocimiento]], [[Memoria documental]]).
- Invita a más personas en **Administración → Usuarios** ([[Administrar usuarios]]); configura el correo SMTP para que reciban la invitación ([[Correo SMTP]]).
- Exige el doble factor o entra con llaves de acceso ([[Seguridad y doble factor]]).

Si algo falla por el camino: [Primer arranque](Soluci%C3%B3n-de-problemas#primer-arranque).
