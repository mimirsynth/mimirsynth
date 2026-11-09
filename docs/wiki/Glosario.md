[English](Glossary) · **Español**

# Glosario

| Término | Significado |
|---|---|
| **Agente** | Programa que usa un modelo de IA para trabajar por ti: Claude Code, Codex, OpenCode, Hermes Agent, OpenClaw, un bot, un script. Se conecta a un brain con un **token de API**, hace recall antes de responder y propone lo que aprende. Ver [[Conectar agentes]] |
| **Alias** | Regla que dice «esta relación se lee como esta otra». Se aplica al leer; no cambia el grafo. Ver [[Relaciones y alias]] |
| **Asistente de configuración** | Las pantallas que guían el primer arranque: cuenta de administrador, base de datos del grafo, modelos de IA, primer brain, token y conexión de un agente. Retoma donde lo dejaste. Ver [[Tus primeros 15 minutos]] |
| **Aviso** | Notificación de un problema de la instancia (modelo de IA o grafo que no responde, ingesta o trabajo fallido…). Se ve en la campana y puede enviarse por canales (correo, Telegram, ntfy, Gotify, webhook). Nunca incluye contenido de la memoria |
| **Brain** | Dominio de conocimiento aislado: su grafo, su ontología, sus documentos, sus miembros. Ver [[Conceptos]] |
| **Bi-temporal** | Que guarda dos fechas por dato: cuándo ocurrió y cuándo se registró |
| **Captura** | Lo que hace un plugin nativo de agente con lo que aprendió una sesión, si la activas: `off` (por defecto), `draft` (se guarda en tu máquina para que lo revises) o `send` (una propuesta en cuarentena por sesión, al siguiente arranque). Nunca la transcripción. Ver [[Configuración de los plugins de agente]] |
| **Colaborador** | Rol que puede proponer memoria y subir documentos, pero cuyos aportes pasan por revisión. Un **token de colaborador** es un token de API con este rol: lo que un agente envía con él espera en cuarentena, y por eso los agentes y sus plugins deben proponer con uno |
| **CoALA** | Marco cognitivo para agentes (memoria episódica, semántica, procedimental…) en el que se inspira el diseño |
| **Consulta de referencia** | Pregunta guardada en un brain con lo que su recall debe traer y lo que no; al ejecutarlas se mide si el recall mejora o empeora. Están en Preguntar → Consultas de referencia |
| **Contexto inyectado** | El bloque de texto que devuelve el recall, listo para ponerlo en el prompt de un agente |
| **Contradicción** | Dos o más hechos vigentes con el mismo sujeto y una relación de un solo valor, pero con valores distintos. Un curador decide cuál se queda en Calidad del contenido → Contradicciones |
| **Cuarentena** | Estado de una propuesta pendiente de revisión, antes de entrar al grafo |
| **Curador** | Rol que aprueba o rechaza propuestas y corrige hechos: la persona que decide qué entra en la memoria de un brain. También es el nombre de la revisión diaria que convierte lo que encuentra en propuestas, ver [[Curador]] |
| **Decisor** | Modelo de decisión cerrada que triaja propuestas según el ámbito del brain y sugiere tipos; nunca rechaza por su cuenta |
| **Detector de secretos** | Revisión que busca credenciales en las propuestas y los documentos antes de guardarlos y, según la política del brain, las enmascara, bloquea el contenido o solo avisa |
| **Docker** | Herramienta que ejecuta MimirSynth y sus bases de datos en **contenedores**, pequeñas máquinas aisladas, sin cambiar nada más de tu equipo. *Docker Compose* las arranca juntas a partir de `docker-compose.yml`. En Windows y macOS viene con Docker Desktop |
| **Duplicado (documento)** | Documento cuyo texto repite el de otro ya indexado en el brain; queda marcado y no se indexa dos veces |
| **Embedding** | Lista de números que representa el significado de un texto, de modo que textos que dicen cosas parecidas reciben números parecidos: así se busca en la memoria por significado y no solo por palabras. Lo calcula un **modelo de embeddings**, y cada modelo da listas de una longitud fija, su **dimensión** (768 en `nomic-embed-text`). Cambiar de modelo recalcula toda la memoria, ver [[Proveedores de IA]] |
| **Entidad** | Una «cosa» del grafo: persona, servidor, aplicación, proyecto… |
| **Episodio** | Un texto tal cual se contó; es inmutable y de él se extraen los hechos |
| **FalkorDB** | Base de datos de grafos donde se guarda el conocimiento |
| **Federación** | Préstamo de lectura de un brain a otro mediante una **concesión** (alcance: grafo, documentos o ambos; caducidad opcional). El recall del brain que recibe incluye lo prestado, marcado con su origen. Solo lectura, en un sentido y de un salto |
| **Graphiti** | Librería que extrae entidades y hechos de los textos y mantiene el grafo temporal |
| **Halo** | En el [[Grafo]], zona translúcida del color de un origen que envuelve los nodos que ese origen respalda; un nodo con varios orígenes queda donde se solapan sus halos |
| **Hecho** | Afirmación entre dos entidades, con fechas de validez |
| **Ingesta** | Proceso por el que una propuesta aprobada se convierte en entidades y hechos |
| **Instalador** | El script (`install.sh`, o `install.ps1` en Windows) que comprueba Docker, pregunta dónde vive el grafo y si arrancar Ollama, escribe la configuración con secretos generados y arranca MimirSynth. Volver a ejecutarlo no cambia nada. Ver [[Instalación]] |
| **Invalidar** | Marcar un hecho como que ya no es cierto, conservando su historia |
| **Instancia** | Una instalación completa de MimirSynth, con todos sus brains |
| **Llave de acceso** | Credencial WebAuthn (*passkey*) guardada en tu dispositivo: entras con huella, cara o PIN. Cuenta como doble factor y solo funciona en el dominio de la instancia, con HTTPS |
| **LLM** | Modelo de lenguaje grande: un modelo de IA que lee y escribe texto, como el que hay detrás de tu agente. Aquí, el que lee cada propuesta aprobada y extrae sus entidades y hechos; su tamaño decide la calidad del grafo. El recall no lo usa, ver [[Proveedores de IA]] |
| **MCP** | Model Context Protocol: la forma estándar de dar herramientas extra a un agente de IA. Cada brain tiene su propio servidor MCP, y un agente conectado a él recibe herramientas como `recall` (leer la memoria) y `remember` (proponer algo que guardar). Ver [[Conectar agentes]] |
| **Neo4j** | Base de datos de grafos que MimirSynth puede usar en lugar de FalkorDB, cuando ya tienes una (5.26 o posterior). Todos los brains comparten entonces una base de datos. Ver [[Instalación]] |
| **OIDC** | Estándar de inicio de sesión con un proveedor de identidad externo |
| **Ollama** | Programa que ejecuta modelos de IA en tu propio equipo, gratis y sin cuenta. El instalador puede arrancar uno para los embeddings (`nomic-embed-text`); desde el contenedor es `http://ollama:11434/v1`, o `http://host.docker.internal:11434/v1` cuando corre en tu equipo |
| **Ontología** | Lista de tipos de entidad y de relación (y reglas entre ellos) que guía la extracción |
| **Origen** | De dónde viene una entidad o un hecho: el tipo de fuente, el documento, la persona que lo propuso o el token del agente. Se puede agrupar por cualquiera de ellos en el [[Grafo]] |
| **Propuesta** | Aportación de memoria pendiente de aprobar |
| **pgvector** | Extensión de PostgreSQL para guardar y buscar vectores |
| **Plugin (de agente)** | Complemento de MimirSynth que se instala en un agente (Claude Code, Codex, OpenCode, Hermes Agent, OpenClaw) y hace recall antes de cada prompt, trae lo que cambió al empezar la sesión y añade comandos, sin que el modelo tenga que pedirlo. Todos comparten un mismo fichero de configuración. Ver [[Conectar agentes]] |
| **Perfil (Compose)** | Servicio opcional de `docker-compose.yml` que solo arranca si se nombra: `bundled` (FalkorDB), `ollama` (embeddings), `ocr`. `COMPOSE_PROFILES` en `.env` dice cuáles arrancar. Ver [[Variables de entorno]] |
| **Promover a memoria** | Convertir un pasaje de un documento en una propuesta |
| **Recall** | Búsqueda que combina hechos, textos de episodios y documentos para dar contexto a un agente |
| **Relación de un solo valor** | Tipo de relación marcado en la ontología («Un solo valor a la vez») que solo puede tener un valor vigente por sujeto; es lo que permite detectar contradicciones |
| **Relleno en sombra** | Primer paso de un cambio de modelo de embeddings: calcula todos los vectores con el modelo nuevo sin tocar los que se usan; después se intercambian |
| **RRF** | «Fusión por rango recíproco»: forma de mezclar varias listas ordenadas |
| **Slug** | Identificador corto de un brain, usado en las direcciones de la API |
| **SMTP** | Protocolo de envío de correo |
| **TOTP** | Código de 6 dígitos que cambia cada 30 segundos (doble factor con una app) |
| **Token de API** | La credencial con la que un agente llega a un brain: un secreto largo que empieza por `mst_` y se muestra **una sola vez**, al crearlo. Su **rol** dice qué puede hacer el agente (un **lector** consulta; un **colaborador** además propone, y lo que propone espera en cuarentena) y puede caducar. Uno por agente, para revocar cada uno por separado. Ver [[Conectar agentes]] |
| **Vigente** | Hecho que sigue siendo cierto (no invalidado) |
