[English](Knowledge) · **Español**

# Conocimiento

La **memoria documental**: ficheros y páginas de wikis que el brain conserva, trocea y permite buscar **por significado y por texto**. A diferencia de los episodios, los documentos **no se convierten en hechos**: se citan con su procedencia. Para entender el diseño, ver [[Memoria documental]].

La pantalla tiene dos pestañas: **Documentos** y **Fuentes**.

## Pestaña Documentos

### Buscar
La barra de búsqueda de arriba acepta una frase en lenguaje natural o palabras clave. Los resultados son **pasajes** con su cita (documento › sección), un indicador de similitud y tres acciones:
- **Ver contexto:** los trozos vecinos del mismo documento.
- **Original:** descarga el fichero.
- **Promover a memoria:** convierte el pasaje en una [propuesta](Propuestas) (ver abajo).

Sin búsqueda, ves la **tabla de documentos**.

### Subir ficheros
Arrastra ficheros a la zona de subida o pulsa **Elegir ficheros**. Formatos: **Markdown, texto (`.md`, `.markdown`, `.txt`, `.rst`, `.log`), HTML (`.html`, `.htm`) y PDF**. Se necesita al menos rol **colaborador**.
- Las subidas se envían **por partes** y puedes subir varios a la vez; verás el estado de cada una y un botón **Limpiar lista**.
- El tamaño máximo de un fichero y de cada parte lo fija el administrador ([[Carpetas y límites]]).
- Si subes un fichero **idéntico** a otro ya subido, no se guarda de nuevo.

### La tabla de documentos
Columnas: **Documento** (título y nombre de fichero), **Fuente**, **Tamaño**, **Trozos**, **Estado** y **Actualizado**. Puedes ordenar por título, tamaño, trozos y fecha, filtrar por título o nombre de fichero, y filtrar por fuente (y, en una carpeta o una wiki, por **Carpeta**). Encima de la tabla, el selector **Estado** tiene un contador por estado:

| Estado | Significado |
|---|---|
| Indexado | Listo para buscar |
| Indexando | Se está troceando y calculando embeddings |
| En cola | Esperando turno |
| Error | Falló (el motivo aparece en el detalle) |
| Duplicado | Mismo texto que otro documento del brain: no se indexa otra vez (ver abajo) |

### Documentos duplicados
La misma nota puede llegar dos veces: desde dos carpetas, desde una carpeta y una wiki, o subida con otro nombre. Cuando el texto extraído de un documento coincide con el de otro ya indexado en el brain (sin contar mayúsculas ni espacios), queda como **Duplicado**: no se trocea ni se calculan sus embeddings, y el recall usa el original.
- El filtro de estado **Duplicado** los lista, y el detalle de un duplicado tiene **Ver el original**.
- Si el original se borra, desaparece de su fuente, cambia o no se puede indexar, se indexa en su lugar el **duplicado más antiguo**. Si dos copias se indexan a la vez, gana siempre la más antigua.
- **Buscar duplicados** (administradores del brain), junto a los filtros, revisa los documentos indexados antes de que existiera esta comprobación y saca del índice los repetidos. Corre como un trabajo con progreso ([[Trabajos]]) e indica cuántos ha sacado. **No se borra nada del origen.**

### Detalle de un documento
Al pulsar un documento se abre su panel:
- Estado, tamaño y número de trozos; nombre de fichero, hash (sha256) y fecha de subida.
- **Secretos detectados**, si el detector de secretos encontró credenciales al indexar (ver abajo).
- **Descargar original**, **Ver texto completo** (hasta el primer megabyte) y, en wikis, **Abrir en la wiki**.
- **Entidades mencionadas**: las entidades del grafo cuyo nombre aparece en el texto. Cada una abre el [[Grafo]] centrado en ella.
- **Relaciones**: los hechos del grafo que unen a esas entidades («A —relación→ B», con el hecho y la fecha desde la que vale). Por defecto, solo los vigentes; **Incluir hechos que dejaron de ser ciertos** añade los invalidados, marcados «ya no es cierto». **Mostrar más** carga más.
- La lista de **trozos** (`#0`, `#1`…), cada uno con su sección y un botón para **promoverlo a memoria**.
- **Reindexar** (administradores del brain): vuelve a trocear y calcular los vectores.
- **Borrar** (administradores del brain, o quien lo subió): quita el original, el texto y los trozos; no se puede deshacer. Aquí solo se borran documentos subidos: los de una carpeta o una wiki se quitan en su origen y desaparecen en el siguiente escaneo.

### Secretos en los documentos
Antes de trocear un documento, el **detector de secretos** busca credenciales en su texto (claves de nube y de proveedores de IA, tokens, claves privadas, contraseñas en URLs…). Lo que pasa depende de la política del brain (Administración → Acceso al brain → **Secretos**):
- **Enmascarar** (por defecto): los secretos seguros se sustituyen en el texto indexado, así que nunca llegan a los trozos, a los vectores ni al recall.
- **Bloquear**: el documento no se indexa y queda en **Error**, indicando qué tipo de secreto contiene.
- **Solo avisar**: no se cambia nada, solo se informa de lo encontrado.

El panel de detalle enumera lo que se encontró. **El original que se descarga nunca se modifica**: conserva el valor tal cual.

### Promover a memoria
Un pasaje relevante de un documento puede convertirse en **conocimiento del grafo**:
1. Pulsa **Promover a memoria** en un trozo.
2. Edita el **texto a recordar**: conviene que sea una afirmación **autocontenida**.
3. Opcional: ponle título.
4. **Enviar propuesta.** Si eres curador, se aprueba y se extraen los hechos al grafo; si no, entra en cuarentena.
El documento no cambia; la propuesta lleva la procedencia (documento y sección).

## Pestaña Fuentes
Una **fuente** es de dónde salen los documentos. Hay tres tipos: **Subidas** (la fuente automática de los ficheros que subes), **Carpeta** y **Wiki**. Cada fuente muestra su tipo, su origen, sus documentos por estado, su estado y su última sincronización, con acciones según tu rol.

### Carpetas (administrador del brain)
Una carpeta es un directorio del servidor, montado **en solo lectura**, cuyos ficheros se indexan sin copiarlos.
1. **Añadir carpeta.**
2. Elige la **raíz autorizada**. Las raíces las registra el administrador de la instancia ([[Carpetas y límites]]); si no hay ninguna, el botón está desactivado y verás un aviso.
3. Opcional: una **subcarpeta** dentro de la raíz. Se recorre entera, subcarpetas incluidas; se ignoran los ficheros ocultos.
4. **Reescanear cada (minutos):** mínimo 5; vacío = solo cuando pulses **Escanear**.
Qué hace un escaneo: detecta ficheros **nuevos, cambiados** (por tamaño, fecha y hash) y **desaparecidos**, e indexa solo lo necesario. Un escaneo *programado* que encuentra la carpeta vacía **falla sin borrar nada** (por si el volumen se desmontó); uno *manual* sí vacía el índice.

Un almacén de Obsidian es una carpeta de Markdown: añádelo como carpeta. Se entienden sus convenciones (frontmatter, enlaces internos, incrustados, comentarios).

### Wikis (administrador de la instancia)
Conecta una wiki por su API, **en solo lectura**, y sus páginas se indexan con una instantánea y un enlace a la página original.
1. **Añadir wiki.**
2. Elige el **Tipo de wiki**:
   - **Outline:** la URL de la wiki y una **clave de API de solo lectura**. Las colecciones son las de Outline.
   - **Confluence** (Cloud y Data Center): la URL de Confluence (en Cloud termina en `/wiki`), el correo de la cuenta que creó el token (solo Cloud; en Data Center se deja vacío) y un **token de API** (Cloud) o un **token de acceso personal** con permiso de lectura (Data Center). Las colecciones son los **espacios**.
   - **Notion:** el token de una **integración interna** con permiso solo de lectura de contenido, compartida con las páginas o bases de datos que quieras indexar. Las colecciones son las **bases de datos** compartidas con la integración, más una de **páginas sueltas** que no están en ninguna base de datos.
3. Claves y tokens se guardan **cifrados** y no se vuelven a mostrar.
4. **Conectar**: se comprueba la conexión y aparece la lista de colecciones.
5. Marca las colecciones a indexar (al menos una), ponle nombre y un intervalo de **resincronización** (vacío = manual).

> Los adaptadores de Confluence y Notion siguen el formato documentado de cada API y tienen tests, pero **aún no se han validado contra una instancia real**. Si usas uno, revisa el resultado del primer escaneo e informa de cualquier problema. Docmost todavía no está soportado.

En cada sincronización solo se reindexa lo que cambió: las páginas se comparan por fecha de modificación y solo se **descargan** las nuevas o cambiadas (importa en Notion, donde cada página cuesta una petición). Las páginas borradas o archivadas, y las de colecciones que desmarques, se retiran. Si la wiki falla a mitad (clave caducada, caída, límite de tasa), el escaneo **se corta sin borrar nada**.

### Acciones sobre una fuente
- **Escanear**: ahora.
- **Editar**: nombre e intervalo; la subcarpeta de una carpeta. En una wiki, un administrador de la instancia puede además cambiar **qué colecciones se indexan** (la lista se obtiene con las credenciales guardadas; al menos una) y sustituir la clave (vacío = conservar la guardada; una nueva se comprueba antes de guardar).
- **Pausar** / **Reanudar**: detiene y reanuda los escaneos programados.
- **Quitar**: borra la fuente y sus documentos indexados; los ficheros de la carpeta y las páginas de la wiki no se tocan.

## Cómo aparece en el recall
Si un pasaje es realmente relevante (similitud suficiente), [[Preguntar]] y la API incluyen hasta **2 pasajes** citados en una sección «Documentos», con un tope de tamaño y de tiempo. Un texto repetido cuenta una sola vez, así que los pasajes son siempre **distintos**. Se puede desactivar por petición. Ver [[Recuerdo e ingesta]].

> El contenido de los documentos es **dato, no instrucciones**. Un documento puede contener texto que parezca una orden para el agente; el recall lo marca como cita de una fuente y tu agente debe tratarlo como tal.
