[English](../DOCUMENTS.md) · **Español**

# Memoria documental (diseño)

Estado: **implementada** (subidas, carpetas y wikis; fases D1 a D5, ver «Fases»). Esta página nació como el diseño de la memoria documental y sigue recogiendo las decisiones tomadas y las alternativas descartadas; donde la implementación acabó apartándose del primer diseño, el texto describe lo que hace hoy el código y lo indica.

## Qué es y qué no es

MimirSynth tiene memoria **episódica y semántica** (el grafo temporal) y un índice de texto de los episodios. La memoria documental añade la memoria de **lo que dicen los documentos**: manuales, páginas de wiki, notas, políticas, READMEs. Es el *conocimiento* del modelo CoALA, consultado por recuperación (RAG), no destilado en hechos.

Principios:

1. **El documento es la fuente de verdad.** Se indexa y se cita; no se convierte en hechos del grafo. Así se evitan el ruido, los duplicados y el coste de pasar por un LLM un texto que ya está curado.
2. **Siempre con procedencia.** Cada pasaje que se devuelve lleva fuente, título, enlace o ruta, sección y fecha de la última sincronización. Sin cita no hay respuesta.
3. **Por brain.** Los documentos pertenecen a un brain igual que los hechos: mismos roles, mismo aislamiento, mismo registro de auditoría.
4. **El contenido es dato, no instrucciones.** Un documento puede contener texto que parezca una orden para el agente; el recall lo marca como cita de una fuente y nunca como instrucción.
5. **Agnóstico del entorno.** Nada de nombres, direcciones ni sistemas concretos en el código: las fuentes se configuran.

## Fuentes

Una fuente es un conector que sabe **listar** documentos (con un identificador estable y una marca de cambio) y **traer su contenido**. Hay tres tipos:

| Tipo | Qué es | Configuración |
|---|---|---|
| **Wiki por API** | Cualquier wiki con API de lectura. Están implementadas Outline, Confluence y Notion (ver «Wikis»); el conector es un adaptador con una interfaz pequeña, para sumar otras sin tocar el resto | Depende del adaptador (normalmente una URL y un token, con los secretos cifrados con el `secretbox`) más las colecciones que se indexan |
| **Carpeta de archivos** | Una carpeta montada **en solo lectura** con ficheros `.md`, `.markdown`, `.txt`, `.rst`, `.log`, `.html`, `.htm` y `.pdf`, en subcarpetas. Los originales se **referencian donde están**, no se copian | Una raíz autorizada y una subcarpeta dentro de ella (ver «Carpetas y cola de trabajos») |
| **Subida desde la UI** | Ficheros arrastrados al navegador, de cualquier tamaño (subida por partes) | Ninguna; cada brain tiene una fuente «Subidas» y el original va al almacén de ficheros |

Más adelante, sin cambiar el diseño: repositorio Git, rastreo de una URL, almacenamiento de objetos.

## Modelo de datos

Plano de control (PostgreSQL, migraciones Alembic):

- `doc_sources`: `id`, `brain_id`, `kind` (`wiki` | `directory` | `upload`), `name` (único por brain), `config` (JSON; los secretos van cifrados), `enabled` (una fuente se puede pausar), `sync_interval` (minutos, vacío = solo manual), `status`, `last_sync_at`, `last_error`, `created_by`.
- `documents`: `id`, `brain_id`, `source_id`, `external_id` (la ruta relativa en una carpeta, el id de la página en una wiki), `title`, `filename`, `url`, `mime`, `size`, `sha256`, `norm_hash` (huella del texto extraído, para detectar duplicados), `storage_ref` (dónde está el original, ver «Almacén de ficheros»), `text_ref` (el texto normalizado al que apuntan los trozos), `source_updated_at`, `status` (`pending` | `indexing` | `active` | `duplicate` | `error`), `error`, `chunks`, `meta` (colección, secretos detectados, el original de un duplicado…), `first_seen_at`, `last_seen_at`. Único por `(source_id, external_id)`.
- El trabajo en segundo plano va a la tabla general `jobs` (ver «Carpetas y cola de trabajos»). *La tabla `doc_jobs` del primer diseño no llegó a crearse.*

Índice (igual que `episode_chunks`: tablas pgvector creadas por el módulo de índice, con la misma dimensión de embedding):

- `doc_chunks`: `document_id`, `brain_id`, `chunk_idx`, `heading_path` (la ruta de títulos, p. ej. «Instalación › Requisitos»), `char_start` y `char_end` (la posición del trozo dentro del texto normalizado), `page` (si la fuente tiene páginas, como un PDF), `text`, `content_hash`, `embedding`, `tsv` (texto completo). Índices GIN y HNSW.

**La base de datos no contiene los ficheros.** Guarda la referencia al original, el texto troceado y sus vectores, y cada trozo apunta con su posición al documento completo. Quien recibe un pasaje puede pedir el contexto que lo rodea o el fichero entero.

## Almacén de ficheros

Los originales viven en un **volumen del stack** que monta la aplicación (`MIMIRSYNTH_DOC_STORE`, por defecto `/data/documents`), no en PostgreSQL. Así no hay tope práctico de tamaño y la base se mantiene pequeña.

```
<almacén>/<brain>/<fuente>/<documento>/
    <sha256>.<ext>        el fichero original (subidas) o la instantánea de la página (wikis), inmutable
    <sha256>.norm.txt     el texto normalizado al que apuntan char_start/char_end
```

- **Rutas generadas por el servidor** a partir de ids, nunca de un nombre que mande el usuario: el nombre original se guarda solo como metadato.
- **Subida por partes:** el navegador envía el fichero en trozos (como mucho 64 MB por petición, ajustable a la baja, porque los proxies delante de la aplicación suelen limitar el cuerpo) que el servidor escribe a disco en flujo, sin cargarlo en memoria. El tamaño máximo de un fichero se fija en Administración → Límites (por defecto `MIMIRSYNTH_DOC_MAX_MB`, 2048 MB). Las subidas que se quedan a medias se borran a las 24 horas. Subir un fichero idéntico (mismo `sha256`) a uno que ya está en el brain devuelve el documento existente en lugar de guardarlo dos veces.
- **Carpeta:** no se copia nada. El original se lee de su ruta dentro de la raíz montada en solo lectura; en el almacén solo se escribe el texto normalizado. Si el fichero desaparece, el siguiente escaneo saca el documento del índice.
- **Wiki:** se guarda una instantánea de cada página (en Markdown, o en HTML para las wikis que lo entregan así), para poder volver a trocearla sin pedirla de nuevo y citarla aunque la wiki no responda.
- **Cambio de contenido:** la versión nueva se escribe y se indexa primero; solo entonces se borra la anterior, de modo que un documento nunca se queda sin original.
- **Integridad:** el `sha256` se calcula al subir y cada vez que cambia un fichero de una carpeta. *El primer diseño preveía un trabajo de mantenimiento que detectara ficheros huérfanos y filas sin fichero; todavía no existe.* Un documento cuyo original ha desaparecido responde 404 al descargarlo.
- **Reconstruible:** el índice (`doc_chunks`) se puede regenerar entero desde el almacén, igual que el de episodios desde el grafo. **El volumen es la fuente de verdad y entra en las copias de seguridad junto con PostgreSQL.**
- **`docker compose`:** un volumen con nombre para el almacén y un único bind de solo lectura para las carpetas que se quieran indexar (ver «Carpetas y cola de trabajos»).

## Canalización de ingesta

1. **Descubrir:** el conector lista los documentos de la fuente.
2. **Comparar:** se decide qué es nuevo, qué ha cambiado, qué sigue igual y qué ha desaparecido. Una carpeta compara tamaño y fecha de modificación y solo calcula el `sha256` de lo que cambió; una wiki compara la fecha de modificación y el título de cada página. Lo que sigue igual no se toca.
3. **Extraer:** de Markdown, texto, HTML, RST y PDF a texto normalizado, conservando la estructura de títulos (se guarda junto al original). El PDF necesita `pypdf`, el extra opcional `pdf`, que la imagen del contenedor ya incluye; un PDF escaneado sin capa de texto no se indexa. Un documento cuyo texto supera el máximo configurado (100 MB por defecto, en Administración → Límites) no se indexa.
4. **Secretos:** antes de trocear, el detector de secretos enmascara lo que tiene forma de credencial, o deja el documento sin indexar si el brain las bloquea (ver «Seguridad»).
5. **Trocear:** por títulos y párrafos (~900 caracteres con un solape de 120, como los episodios), guardando la ruta de títulos y la posición de cada trozo en el texto.
   - **Duplicados:** si el texto extraído (sin contar mayúsculas ni espacios, la misma regla con la que el recall descarta pasajes repetidos) ya está indexado en otro documento del brain, el documento queda como `duplicate`, apunta al más antiguo y no se trocea ni se calculan sus embeddings. Aparece en Conocimiento con su propio filtro de estado y un enlace al original. Si el original se borra, desaparece de su fuente, cambia su texto o no se puede indexar, el duplicado más antiguo se indexa en su lugar. La deduplicación es por brain; entre brains ya marca el origen la federación. Si dos copias se indexan a la vez, o se reindexa una más antigua, gana siempre la más antigua. **Buscar duplicados** (administradores del brain) revisa los documentos indexados antes de que esto existiera, desde su texto normalizado y sin volver a extraerlos, como un trabajo con progreso; en el origen no se borra nada.
6. **Embeber:** por lotes, con el motor de embeddings configurado y respetando su límite de tasa.
7. **Sustituir:** los trozos de un documento cambiado se reemplazan en una sola transacción, así una consulta nunca ve un documento a medio indexar.
8. **Retirar:** un documento que ya no está en la fuente sale del índice y de la base de datos, junto con su texto guardado; el trabajo del escaneo anota cuántos se retiraron. *El primer diseño conservaba el registro como `deleted` para el historial; la implementación lo elimina.*

Es idempotente y reanudable: si falla a mitad, la siguiente pasada continúa. Corre en segundo plano con el progreso a la vista (ver «Carpetas y cola de trabajos»). Cambiar de modelo de embeddings obliga a reindexar de forma explícita (Administración → Embeddings).

## Recuperación

- **Búsqueda propia:** `GET /api/brains/{slug}/docs/search?q=…`, híbrida (texto completo + vectores, fusión RRF) como el recall de episodios. Devuelve pasajes con su cita.
- **Integración en el recall, sin encarecerlo:** el contexto de los agentes gana una sección «Documentos», pero solo cuando aporta.
  - **Presupuesto duro:** como máximo 2 pasajes (ajustable en Administración → Recuerdo) de ~1.000 caracteres (unos 600 tokens en total), siempre citados.
  - **Solo si hay relevancia:** por debajo de un umbral de similitud (0,66 por defecto, calibrado con `nomic-embed-text`; depende del modelo de embeddings) no se añade nada, salvo que el pasaje se quede cerca y además coincida en al menos dos términos de la consulta. Una consulta que no trata de documentos no gasta tokens.
  - **Sin repeticiones:** un pasaje con el mismo texto que otro ya elegido (el mismo contenido en dos documentos, o en un origen que presta sus documentos) se salta, de modo que el presupuesto se reparte entre pasajes distintos.
  - **Sin lentitud:** la búsqueda documental corre en paralelo con la de hechos y episodios y tiene su propio tiempo máximo (0,6 s por defecto); si se pasa, se omite la sección en lugar de retrasar la respuesta.
  - **Desactivable** por petición (`docs: 0` en `recall`), y el agente puede pedir después el documento completo o el contexto ampliado de un pasaje, solo cuando lo necesite (`GET /docs/{id}/context?chunk=…`, `GET /docs/{id}/file`).
  - Hechos, fragmentos de episodios y documentos se muestran por separado: son tipos de evidencia distintos.
- **Sin mezclar con el grafo** salvo dos puentes opcionales, ambos implementados en la fase D5 (ver «Puentes con el grafo»):
  - **Enlace a entidades:** qué entidades del grafo menciona cada documento (por coincidencia de nombre, sin LLM), para ir de una entidad a sus documentos y al revés.
  - **Promover a memoria:** desde un pasaje, un botón crea una **propuesta en cuarentena** (la cola de siempre) para que, si merece ser un hecho, entre por el camino normal de ingesta.

## Permisos y auditoría

| Acción | Rol mínimo |
|---|---|
| Buscar y leer documentos, descargar el original, ver los trabajos | lector |
| Subir ficheros; promover un pasaje a memoria | colaborador |
| Borrar un documento subido | quien lo subió, o un administrador del brain |
| Cancelar o reintentar un trabajo | curador |
| Añadir, editar, pausar, escanear o quitar fuentes; reindexar un documento; buscar duplicados | administrador del brain |
| Registrar raíces de carpetas; conectar una wiki o cambiar su conexión y sus colecciones | administrador de la instancia (no con un token de API) |

Solo los documentos subidos se pueden borrar de uno en uno: un documento de una carpeta o de una wiki volvería en el siguiente escaneo, así que se quita en su origen o quitando la fuente. Todo queda en la auditoría (qué fuente, quién, cuántos documentos). Quitar una fuente pide confirmación y elimina del índice sus documentos y sus trozos; los ficheros de la carpeta y las páginas de la wiki no se tocan.

La **federación** ([FEDERATION.md](FEDERATION.md)) trata los documentos como un recurso que se concede aparte del grafo («solo grafo», «solo documentos», «ambos»).

## Seguridad

- **Carpeta:** el administrador de la instancia registra las raíces en Administración → Carpetas, siempre bajo el bind de solo lectura `/sources`; un administrador de brain solo elige una raíz y una subcarpeta dentro de ella. Nunca una ruta arbitraria, y no se siguen los enlaces simbólicos que salen de la carpeta.
- **Wiki:** solo los administradores de la instancia configuran la URL y las credenciales, porque el servidor hace peticiones a la dirección que se le da. Las redes privadas se permiten (es lo normal en un autoalojado). *El interruptor para prohibirlas que mencionaba el primer diseño no existe.*
- **Subidas:** tope de tamaño; solo se aceptan las extensiones admitidas, y un fichero de texto cuyo contenido resulta ser binario se rechaza al extraerlo; el HTML se reduce a texto. El original solo se devuelve a quien tiene permiso de lectura en el brain, con `Content-Disposition: attachment` y `X-Content-Type-Options: nosniff`; nada se ejecuta ni se sirve como página.
- **Secretos:** cifrados con el mismo `secretbox` que las claves de los motores; nunca se devuelven por la API (solo dice cuáles están puestos).
- **Credenciales dentro de un documento:** antes de trocear, el detector de secretos enmascara lo que tiene forma de credencial en el texto que se indexa, o deja el documento sin indexar (en `error`) si el brain las bloquea. El original no se modifica. Ver «Secretos» en [ARCHITECTURE.md](ARCHITECTURE.md).

## Interfaz

Una pestaña **Conocimiento**, hecha solo con el kit de componentes:

- Barra de búsqueda con resultados (pasaje resaltado, cita y enlace).
- Tabla de **fuentes**: tipo, estado, último escaneo, número de documentos, «Escanear», editar, pausar, quitar.
- Tabla de **documentos**: título, fuente, actualizado, trozos, estado (duplicados incluidos, con enlace al original) y el error si lo hay; filtros por texto, fuente, estado y carpeta.
- Zona de **subida** (arrastrar y soltar) con progreso por fichero.
- Detalle de documento con sus trozos y su ruta de títulos, el texto completo, el original, las entidades que menciona y las relaciones entre ellas, y «Promover a memoria».

## Fases

1. **D1 — Subida y búsqueda (hecha, 2026-10-23).** Esquema, subida desde la UI, extracción, troceado, embeddings, búsqueda híbrida y la pestaña mínima. La rebanada más pequeña que ya sirve de punta a punta, sin conectores.
2. **D2 — Recall (hecha, 2026-10-23).** La sección «Documentos» en el contexto de los agentes y en el hook.
3. **D3 — Carpeta (hecha, 2026-10-23).** Fuentes de tipo carpeta con reescaneo, y la cola general de trabajos (ver «Carpetas y cola de trabajos»).
4. **D4 — Wiki (hecha, 2026-10-23).** La interfaz del adaptador (`wikis.py`) y la implementación para Outline, con sincronización incremental por fecha de modificación (ver «Wikis»). Confluence y Notion llegaron después, en la 0.7.0.
5. **D5 — Puentes con el grafo (hecha, 2026-10-23).** Entidades mencionadas, documentos que mencionan una entidad y «promover a memoria» (ver «Puentes con el grafo»).

## Decisiones

Tomadas el 2026-10-23:

1. **Originales:** en un volumen del stack, nunca en PostgreSQL. La base guarda la referencia, el texto troceado y los vectores.
2. **Formatos de la primera versión:** Markdown, texto, HTML y RST; PDF como extra opcional. *Hoy el PDF se lee siempre que esté instalado `pypdf`, como en la imagen del contenedor.*
3. **Documentos en el recall por defecto:** sí, con presupuesto duro, umbral de relevancia y tiempo máximo (ver «Recuperación»).
4. **Sincronización:** manual por ahora, con intervalo opcional por fuente más adelante. *El intervalo ya existe: 5 minutos o más, o vacío para solo manual.*
5. **Versiones anteriores de los trozos:** no se conservan; solo se puede consultar el documento vigente.

Estudiada, sin implementar:

6. **Importar el contenido de un servicio de memoria anterior** (por ejemplo, otro servicio de memoria para agentes). Lo que guarda un servicio así suelen ser notas cortas de agentes, no documentos con fichero o URL. Se trataría como una fuente más de tipo «notas» (cada nota, un documento pequeño), indexada solo con embeddings, sin pasar por la extracción del LLM, y etiquetada como archivo con su fecha para que el recall le dé menos peso que a lo vigente.

## Carpetas y cola de trabajos

**Cola general (`jobs`).** Todo lo que la aplicación hace en segundo plano se registra en una tabla `jobs` (tipo, estado, progreso, registro, resultado, intentos, quién lo lanzó) y se ejecuta en un pool acotado por tipo. Tipos actuales: `proposal.ingest`, `doc.index`, `doc.scan`, `doc.dedupe`, `retype.scan`, `conflicts.scan`, `refquery.run`, `embedding.reindex` y `embedding.switch`. Estados: en cola, en marcha, terminado, fallido, cancelado. La pantalla **Trabajos** (lector o superior) lista, filtra y muestra el detalle; un curador o superior puede cancelar y reintentar. Al arrancar, lo que estaba a medias se marca como interrumpido y los tipos idempotentes (`doc.index`, `doc.scan`, `embedding.reindex`) se relanzan solos. Los trabajos terminados se conservan 60 días, y los reescaneos programados que acabaron sin incidencias, 7 (ambos plazos se ajustan en Administración → Ingesta y trabajos). Los manejadores se registran con `@jobs.register(kind, label, limit, resume)` y reciben un `JobCtx` (`progress`, `note`, `retrying`, `check` para cancelar). Quedan fuera por ahora la sincronización periódica del índice de episodios (cada 10 min, no es una acción del usuario) y el triaje del decisor (instantáneo).

**Fuente de carpeta.** El compose monta un único bind de solo lectura (`MIMIRSYNTH_SOURCES_DIR` del host → `/sources`, con propagación `rslave`: lo que se monte debajo en el host aparece sin reiniciar). El administrador de la instancia registra las raíces en Administración → Carpetas (tabla `doc_roots`); solo valen rutas bajo `/sources`. Nunca se escribe en ellas. Una fuente es una raíz más una subcarpeta (que no puede salir de la raíz). Los originales **no se copian**: la base guarda la ruta relativa (`external_id`) y el almacén solo el texto normalizado. Se ignoran los ficheros y carpetas ocultos, los enlaces simbólicos que salen de la carpeta, los ficheros vacíos y lo que no sea un formato admitido o supere el tamaño máximo. El reescaneo compara tamaño y fecha, solo calcula el `sha256` de lo que cambió, indexa lo nuevo y lo modificado y retira lo desaparecido.

Protección: si la carpeta no está disponible, el escaneo falla sin borrar nada; si aparece vacía teniendo documentos, el escaneo programado también falla (podría ser un volumen desmontado) y solo uno manual, que es una orden explícita, vacía el índice. Un documento de carpeta no se borra suelto (volvería a aparecer): se quita la fuente, y los ficheros de la carpeta no se tocan. Reescaneo automático con intervalo por fuente (mínimo 5 min) o manual.

## Wikis

Una fuente de tipo `wiki` lee las páginas de una wiki por su API, en solo lectura, y las trata como cualquier otro documento (troceado, índice, recall, cola de trabajos). Las implementaciones son Outline (`wikis.Outline`, medida contra una instancia real), Confluence (Cloud y Data Center) y Notion (`wikis.Confluence`, `wikis.Notion`). Estas dos últimas están escritas contra el formato documentado de cada API y cubiertas por tests con respuestas simuladas, **sin validar aún contra una instancia real**: si usas una, revisa el primer escaneo y avisa de cualquier problema. Docmost no tiene todavía una API pública documentada en la que apoyarse y queda sin escribir.

- **Conexión:** los campos que declara cada adaptador (en Outline, la URL de la instancia y una clave de API). Los secretos se guardan cifrados (`secretbox`) y no se devuelven nunca por la API. En Outline se recomienda una clave limitada a `documents.list` y `collections.list`. Las colecciones que se indexan se eligen tras comprobar la conexión y se pueden cambiar después en Conocimiento → Fuentes → Editar con las credenciales guardadas; dejar vacío un campo secreto conserva el guardado.
- **Solo el administrador de la instancia** conecta o cambia una wiki (nunca con un token de API): el servidor hace peticiones a la URL que se le da.
- **Sincronización incremental:** se comparan la fecha de modificación y el título de cada página; solo lo que cambió se descarga, se le calcula el hash y se reindexa. Las páginas borradas, archivadas o despublicadas se retiran. El «original» es una instantánea de la página (con su título como encabezado) guardada en el almacén; el documento conserva la URL de la página para abrirla en la wiki. Una página vacía no se indexa.
- **Protección:** si la wiki falla a mitad (clave caducada, caída, límite de tasa), la excepción corta el escaneo y no se borra nada. Si devuelve cero páginas teniendo documentos, el escaneo programado falla; solo uno manual vacía el índice. Los reintentos por límite de tasa (429) respetan `Retry-After`.
- **Medido contra una instancia real de Outline** (durante el diseño): 170 páginas, 527.000 caracteres (~1.200 trozos), listadas en 1,4 s.

### Cómo añadir otra wiki

Un adaptador es una clase en `wikis.py` registrada con `@register`. Se describe a sí mismo y la interfaz construye el formulario a partir de esa descripción: no hay que tocar la UI.

```python
@register
class Confluence(Adapter):
    id, label, collection_label = "confluence", "Confluence", "Espacios"
    fields = [Field("base_url", "URL"), Field("email", "Email"), Field("token", "Token de API", secret=True)]
    def collections(self): ...            # [{id, name, description}]
    def documents(self, ids): ...         # yield WikiDoc(id, title, content, updated_at, url, collection, format="markdown"|"html")
```

El `content` de un `WikiDoc` puede ser una función en vez de un texto: el escaneo la llama solo para las páginas nuevas o cambiadas, así los adaptadores cuyo contenido cuesta una petición por página (Notion) no lo descargan todo en cada escaneo.

Reglas del contrato: solo lectura; sin estado; `updated_at` es la fecha de última modificación de la página (es lo que decide si se reindexa); `format` es `markdown` o `html` (el extractor lee ambos, así que Confluence puede devolver su HTML tal cual); un error de conexión o de permisos se lanza como `WikiError` con un mensaje legible, y cortar la lista a mitad nunca borra nada. Lo demás (cifrado de los campos `secret`, elección de colecciones, sincronización incremental, instantánea del original, progreso en Trabajos, protección contra vaciados) es común. La configuración se guarda como `{adapter, settings, secrets (cifrados), collection_ids}`.

**Estado de los adaptadores**
- **Outline:** hecho y probado con una instancia real.
- **Obsidian:** no necesita adaptador. Un vault es una carpeta de Markdown: se usa como fuente de carpeta. El extractor entiende sus convenciones: quita el frontmatter YAML (usando su `title:`), deja el texto de los `[[enlaces]]` y `[[destino|alias]]`, y descarta `![[incrustaciones]]`, `%%comentarios%%` y marcas `^bloque`, también con saltos de línea de Windows. `.obsidian/` se ignora por ser oculta.
- **Confluence (Cloud y Data Center) y Notion:** escritos contra el formato documentado de cada API y cubiertos por tests con respuestas simuladas; **sin validar aún contra una instancia real**. Confluence usa la API REST v1 (`/rest/api`): Cloud con correo + token de API, Data Center con un token de acceso personal sin correo; las colecciones son los espacios y las páginas llegan como HTML (`body.storage`). Notion no tiene espacios: las colecciones son las bases de datos compartidas con la integración más «Páginas sueltas»; los bloques de cada página se convierten a Markdown y su contenido solo se pide cuando cambió la fecha de modificación.
- **Docmost:** sin escribir; su API pública no está documentada de forma estable. Se añadirá cuando lo esté o cuando haya una instancia de prueba.

## Puentes con el grafo

El documento sigue siendo la fuente de verdad; enlazar es señalar, y no se escribe nada en el grafo.

- **Entidades mencionadas** (`GET /docs/{id}/entities`): se buscan en el texto del documento los nombres y alias de las entidades vivas del grafo (palabra completa, sin distinguir mayúsculas; las fusionadas no cuentan, y su nombre antiguo funciona como alias de la que queda). Sin LLM ni tablas nuevas: la lista de entidades se guarda un minuto en caché y las coincidencias se calculan al abrir el documento, así que siempre están al día. Se ignoran los nombres de menos de 4 caracteres (salvo siglas de 3 letras en mayúsculas) y los numéricos. En Conocimiento, cada entidad del detalle lleva al Grafo centrado en ella (`/grafo?nodo=<uuid>`).
- **Relaciones entre ellas** (misma ruta): el grafo ya sabe cómo se relacionan las entidades mencionadas. Con una sola consulta (`MATCH (a)-[r:RELATES_TO]->(b)` entre las entidades detectadas, sin LLM ni embeddings) el visor muestra «A —relación→ B» con el hecho y la fecha desde la que vale. Por defecto solo los vigentes; `expired=true` añade los que dejaron de ser ciertos (`expired_count` dice cuántos hay) y `relations=N` limita cuántos se devuelven (`total` cuenta los que cumplen el filtro). Los alias de relación del brain se aplican al nombre. Solo el grafo del propio brain: lo que prestan otros brains (ver [FEDERATION.md](FEDERATION.md)) no entra aquí. Si el grafo falla, el visor sigue mostrando las entidades.
- **Documentos que mencionan una entidad** (`GET /docs/mentions?entity=<uuid>`): búsqueda de frase en el índice de texto completo con el nombre y los alias; devuelve el documento, cuántos pasajes coinciden y el mejor fragmento resaltado. Aparece en el panel de una entidad en la pantalla Grafo, con enlace al documento (`/conocimiento?doc=<id>`).
- **Promover a memoria** (`POST /docs/{id}/promote`): convierte un pasaje (tal cual o editado por quien lo promueve) en una propuesta con su procedencia («Fuente: título, sección, URL»), confianza 0,7 y, como fecha de referencia, la de la página o el fichero. Pasa por el flujo normal: un colaborador la deja en cuarentena, un curador la aprueba y se extraen hechos con Graphiti. No se puede promover dos veces el mismo pasaje (409 con la propuesta existente).
