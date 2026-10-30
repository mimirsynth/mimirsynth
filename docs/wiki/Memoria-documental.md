[English](Document-memory) · **Español**

# Memoria documental

Además de la memoria «destilada» (episodios → hechos), MimirSynth guarda **documentos**: manuales, notas, páginas de wiki, PDF. Esta página explica cómo funciona por dentro y cómo sacarle partido. La parte de uso está en [[Conocimiento]].

## Principios
1. **El documento es la fuente de verdad.** Se indexa y se **cita**, pero **no se convierte en hechos** del grafo. Evita ruido, duplicados y el coste de extraer con un LLM un texto largo.
2. **Siempre con procedencia.** Cada pasaje que se devuelve lleva su fuente, título, sección, enlace o ruta y fecha de sincronización.
3. **Por brain.** Los documentos pertenecen a un brain: mismos roles, mismo aislamiento, misma auditoría.
4. **El contenido es dato, no instrucciones.** El recall marca los pasajes como citas.

## Cómo se indexa un documento
1. Se **guarda el original** en el volumen del almacén (o, en una carpeta, se referencia sin copiar).
2. Se **extrae el texto** (Markdown, texto plano, HTML, PDF).
3. El **detector de secretos** busca credenciales en el texto y, según la política del brain, las enmascara o deja el documento sin indexar (ver abajo).
4. Si el mismo texto (sin contar mayúsculas ni espacios) **ya está indexado** en otro documento del brain, el documento queda como **duplicado** y se para aquí (ver abajo).
5. Se **trocea por títulos y secciones**, conservando la ruta de títulos («Instalación › Requisitos»).
6. Se calculan los **embeddings** de cada trozo y se guardan junto con el texto para la búsqueda de texto completo.
7. Cuando el documento cambia, los trozos se **reemplazan de una sola vez**: nunca queda un documento sin índice.
Todo corre en segundo plano como un [trabajo](Trabajos).

## Cómo se busca
La búsqueda es **híbrida**: mezcla la similitud por significado (vectores) con la coincidencia de palabras (texto completo) y fusiona ambas listas. Funciona con preguntas en lenguaje natural y con términos exactos (códigos, nombres).

## Qué recibe el agente en el recall
En el **recall** de los agentes (API REST y herramienta `recall` del MCP), los pasajes documentales van en una sección «Documentos» aparte con un presupuesto pequeño (2 pasajes, ~600 tokens, 0,6 s) para no desplazar a los hechos:
- **Solo si es relevante:** por debajo de un umbral de similitud no se añade nada, así que una pregunta que no tiene que ver con documentos no gasta tokens.
- **Sin pasajes repetidos:** cuando el mismo texto aparece en dos documentos (la misma nota en dos fuentes), o en el brain y en otro brain que le presta sus documentos ([federación](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/FEDERATION.md)), solo se queda la primera copia. El presupuesto se dedica siempre a pasajes **distintos**.
- **Nunca más lento:** la búsqueda en documentos corre en paralelo con la de hechos, con su propio tiempo máximo; si se pasa, la sección se omite.
- **Se puede desactivar** por petición (`docs=0`), y el agente puede pedir después más contexto de un pasaje o el fichero original. Ver [[Conectar agentes]].

El presupuesto y el umbral se ajustan en [[Recuerdo e ingesta]].

## Documentos duplicados
Un documento cuyo texto extraído coincide con el de otro ya indexado en el brain queda como **duplicado**: no se trocea ni se calculan sus embeddings, así que el mismo contenido nunca ocupa dos sitios en el índice ni en el recall. Las reglas:
- Se indexa la copia **más antigua**. Si se borra, desaparece de su fuente, cambia o no se puede indexar, se indexa en su lugar el duplicado más antiguo.
- La deduplicación es **por brain**. Entre brains, la federación ya indica de dónde viene cada pasaje.
- Los documentos indexados antes de que existiera esta comprobación se revisan con **Buscar duplicados** en [[Conocimiento]] (administradores del brain). No se borra nada del origen.

## Secretos en los documentos
Antes de trocear, el detector de secretos busca credenciales: claves de nube y de proveedores de IA, tokens de GitHub, GitLab, Slack, npm y Hugging Face, claves privadas PEM, JWT, cabeceras `Authorization`, contraseñas en URLs… Un valor de aspecto aleatorio asignado a `password`, `secret` o `token` cuenta solo como secreto **posible** y únicamente se marca. La política del brain (Administración → Acceso al brain → **Secretos**) decide qué pasa con los seguros:
- **Enmascarar** (por defecto): se sustituyen en el texto indexado, así que nunca llegan a los trozos, a los vectores ni a los agentes.
- **Bloquear**: el documento no se indexa y muestra un error.
- **Solo avisar**: no se cambia nada.

El **original que se descarga nunca se modifica**. El valor detectado no se guarda nunca en la auditoría, en los registros ni en las respuestas de la API. Las excepciones y **Analizar lo ya guardado** están en la misma sección de Administración.

## Almacén de ficheros
Los originales viven en un **volumen del stack** (`MIMIRSYNTH_DOC_STORE`), **no** en PostgreSQL: la base solo guarda la referencia, el texto troceado y los vectores. Las rutas las genera el servidor (nunca a partir de un nombre que mande el usuario). El volumen **debe entrar en las copias de seguridad**; el índice de PostgreSQL se puede regenerar desde él ([[Actualización y copias de seguridad]]).

## Tipos de fuente
| Fuente | Qué es | Quién la gestiona |
|---|---|---|
| **Subidas** | Ficheros arrastrados en la web | Colaborador o superior |
| **Carpeta** | Directorio montado **en solo lectura**; se reescanea cada N minutos | Administrador del brain (raíces: administrador de la instancia) |
| **Wiki** | Una wiki por su API, en solo lectura: Outline, Confluence o Notion | Administrador de la instancia |

### Escaneo de carpetas
Detecta **nuevos, cambiados y desaparecidos** por tamaño, fecha y hash. Si la carpeta aparece vacía en un escaneo programado, falla sin borrar nada (protección contra volúmenes desmontados). Un almacén de Obsidian no necesita adaptador: úsalo como carpeta.

### Wikis y adaptadores
Una wiki se conecta mediante un **adaptador**: una pequeña clase que lista las colecciones y devuelve las páginas. El formulario de conexión se construye solo a partir de los campos que declara el adaptador.

| Adaptador | Colecciones | Estado |
|---|---|---|
| **Outline** | Colecciones | Probado contra una instancia real |
| **Confluence** (Cloud y Data Center) | Espacios | Escrito sobre la API documentada y cubierto por tests; **aún no validado contra una instancia real** |
| **Notion** | Bases de datos compartidas con la integración, más las páginas sueltas | Escrito sobre la API documentada y cubierto por tests; **aún no validado contra una instancia real** |

Docmost no está soportado: todavía no tiene una API pública documentada. Si usas Confluence o Notion, revisa el primer escaneo e informa de cualquier problema.

La sincronización es **incremental**: las páginas se comparan por fecha de modificación y solo se descargan las nuevas o cambiadas, lo que abarata los reescaneos aunque cada página cueste una petición (Notion). Si la wiki falla a mitad, el escaneo se corta sin borrar nada. Para escribir un adaptador nuevo (de solo lectura y sin estado), mira «Cómo añadir otra wiki» en [`docs/es/DOCUMENTS.md`](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/DOCUMENTS.md).

## Permisos
| Acción | Rol |
|---|---|
| Buscar, abrir, ver contexto, descargar el original | lector |
| Subir ficheros, promover un pasaje a memoria, borrar los ficheros que subiste | colaborador |
| Reindexar, borrar cualquier documento subido, buscar duplicados, gestionar fuentes de carpeta | administrador del brain |
| Añadir wikis, cambiar sus colecciones y credenciales | administrador de la instancia |
Toda acción queda en la [[Auditoría]].

## De documento a memoria
Cuando un pasaje contiene algo que quieres que el sistema **recuerde y razone** (no solo cite), usa **Promover a memoria**: crea una [propuesta](Propuestas) con el texto (que puedes editar) y su procedencia. Si eres curador se ingiere; si no, entra en cuarentena. El documento no cambia.

## Límites y consejos
- PDF **escaneados** (solo imagen) no tienen texto que indexar.
- Documentos muy largos están acotados por *Texto máximo extraído* ([[Carpetas y límites]]).
- Los documentos con mucha basura (menús, cabeceras repetidas) empeoran la búsqueda: limpia la fuente si puedes.
- Cambiar el modelo de embeddings (Administración → Embeddings, ver [[Proveedores de IA]]) recalcula también los vectores de los documentos.
