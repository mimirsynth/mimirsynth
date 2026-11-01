[English](Glossary) · **Español**

# Glosario

| Término | Significado |
|---|---|
| **Alias** | Regla que dice «esta relación se lee como esta otra». Se aplica al leer; no cambia el grafo. Ver [[Relaciones y alias]] |
| **Aviso** | Notificación de un problema de la instancia (modelo de IA o grafo que no responde, ingesta o trabajo fallido…). Se ve en la campana y puede enviarse por canales (correo, Telegram, ntfy, Gotify, webhook). Nunca incluye contenido de la memoria |
| **Brain** | Dominio de conocimiento aislado: su grafo, su ontología, sus documentos, sus miembros. Ver [[Conceptos]] |
| **Bi-temporal** | Que guarda dos fechas por dato: cuándo ocurrió y cuándo se registró |
| **Colaborador** | Rol que puede proponer memoria y subir documentos, pero cuyos aportes pasan por revisión |
| **CoALA** | Marco cognitivo para agentes (memoria episódica, semántica, procedimental…) en el que se inspira el diseño |
| **Consulta de referencia** | Pregunta guardada en un brain con lo que su recall debe traer y lo que no; al ejecutarlas se mide si el recall mejora o empeora. Están en Preguntar → Consultas de referencia |
| **Contexto inyectado** | El bloque de texto que devuelve el recall, listo para ponerlo en el prompt de un agente |
| **Contradicción** | Dos o más hechos vigentes con el mismo sujeto y una relación de un solo valor, pero con valores distintos. Un curador decide cuál se queda en Calidad del contenido → Contradicciones |
| **Cuarentena** | Estado de una propuesta pendiente de revisión, antes de entrar al grafo |
| **Curador** | Rol que aprueba o rechaza propuestas y corrige hechos |
| **Decisor** | Modelo de decisión cerrada que triaja propuestas según el ámbito del brain y sugiere tipos; nunca rechaza por su cuenta |
| **Detector de secretos** | Revisión que busca credenciales en las propuestas y los documentos antes de guardarlos y, según la política del brain, las enmascara, bloquea el contenido o solo avisa |
| **Duplicado (documento)** | Documento cuyo texto repite el de otro ya indexado en el brain; queda marcado y no se indexa dos veces |
| **Embedding** | Representación numérica de un texto, usada para buscar por significado |
| **Entidad** | Una «cosa» del grafo: persona, servidor, aplicación, proyecto… |
| **Episodio** | Un texto tal cual se contó; es inmutable y de él se extraen los hechos |
| **FalkorDB** | Base de datos de grafos donde se guarda el conocimiento |
| **Federación** | Préstamo de lectura de un brain a otro mediante una **concesión** (alcance: grafo, documentos o ambos; caducidad opcional). El recall del brain que recibe incluye lo prestado, marcado con su origen. Solo lectura, en un sentido y de un salto |
| **Graphiti** | Librería que extrae entidades y hechos de los textos y mantiene el grafo temporal |
| **Halo** | En el [[Grafo]], zona translúcida del color de un origen que envuelve los nodos que ese origen respalda; un nodo con varios orígenes queda donde se solapan sus halos |
| **Hecho** | Afirmación entre dos entidades, con fechas de validez |
| **Ingesta** | Proceso por el que una propuesta aprobada se convierte en entidades y hechos |
| **Invalidar** | Marcar un hecho como que ya no es cierto, conservando su historia |
| **Instancia** | Una instalación completa de MimirSynth, con todos sus brains |
| **Llave de acceso** | Credencial WebAuthn (*passkey*) guardada en tu dispositivo: entras con huella, cara o PIN. Cuenta como doble factor y solo funciona en el dominio de la instancia, con HTTPS |
| **LLM** | Modelo de lenguaje grande; aquí, el que extrae los hechos |
| **MCP** | Model Context Protocol: protocolo para conectar herramientas a agentes de IA. Cada brain tiene su servidor MCP, con las herramientas `recall` y `remember`. Ver [[Conectar agentes]] |
| **OIDC** | Estándar de inicio de sesión con un proveedor de identidad externo |
| **Ontología** | Lista de tipos de entidad y de relación (y reglas entre ellos) que guía la extracción |
| **Origen** | De dónde viene una entidad o un hecho: el tipo de fuente, el documento, la persona que lo propuso o el token del agente. Se puede agrupar por cualquiera de ellos en el [[Grafo]] |
| **Propuesta** | Aportación de memoria pendiente de aprobar |
| **pgvector** | Extensión de PostgreSQL para guardar y buscar vectores |
| **Promover a memoria** | Convertir un pasaje de un documento en una propuesta |
| **Recall** | Búsqueda que combina hechos, textos de episodios y documentos para dar contexto a un agente |
| **Relación de un solo valor** | Tipo de relación marcado en la ontología («Un solo valor a la vez») que solo puede tener un valor vigente por sujeto; es lo que permite detectar contradicciones |
| **Relleno en sombra** | Primer paso de un cambio de modelo de embeddings: calcula todos los vectores con el modelo nuevo sin tocar los que se usan; después se intercambian |
| **RRF** | «Fusión por rango recíproco»: forma de mezclar varias listas ordenadas |
| **Slug** | Identificador corto de un brain, usado en las direcciones de la API |
| **SMTP** | Protocolo de envío de correo |
| **TOTP** | Código de 6 dígitos que cambia cada 30 segundos (doble factor con una app) |
| **Token de API** | Credencial para que un agente acceda a un brain |
| **Vigente** | Hecho que sigue siendo cierto (no invalidado) |
