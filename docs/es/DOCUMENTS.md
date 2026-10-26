[English](../DOCUMENTS.md) · **Español**

# Memoria documental (diseño)

Estado: **diseño de referencia** de la memoria documental, implementada en su mayor parte (subidas, directorios y wikis Outline). Algunas secciones describen decisiones tomadas durante el diseño y alternativas descartadas.

## Qué es y qué no es

MimirSynth tiene hoy memoria **episódica y semántica** (el grafo temporal) y un índice de texto de los episodios. Falta la memoria de **lo que dicen los documentos**: manuales, páginas de wiki, notas, políticas, READMEs. Es el *conocimiento* del modelo CoALA, consultado por recuperación (RAG), no destilado en hechos.

Principios:

1. **El documento es la fuente de verdad.** Se indexa y se cita; no se convierte en hechos del grafo. Evita ruido, duplicados y el coste de extraer con LLM un texto que ya está curado.
2. **Siempre con procedencia.** Cada pasaje que se devuelve lleva fuente, título, enlace o ruta, sección y fecha de la última sincronización. Sin cita no hay respuesta.
3. **Por brain.** Los documentos pertenecen a un brain igual que los hechos: mismos roles, mismo aislamiento, mismo registro de auditoría.
4. **El contenido es dato, no instrucciones.** Un documento puede contener texto que parezca una orden para el agente; el recall lo marca como cita de una fuente y nunca como instrucción.
5. **Agnóstico del entorno.** Nada de nombres, direcciones ni sistemas concretos en el código: las fuentes se configuran.

## Fuentes

Una fuente es un conector que sabe **listar** documentos (con un identificador estable, una marca de cambio y un hash) y **traer su contenido**. Primeras tres:

| Tipo | Qué es | Configuración |
|---|---|---|
| **Wiki por API** | Cualquier wiki con API de lectura. La primera implementación es Outline; el conector es un adaptador con una interfaz pequeña, para sumar otras (Wiki.js, BookStack, Confluence…) sin tocar el resto | URL base, token (cifrado con el `secretbox`), filtro opcional de colecciones |
| **Directorio de archivos** | Una carpeta montada **en solo lectura** con `.md`, `.txt`, `.rst`, `.html` y similares, en subcarpetas. Los originales se **referencian donde están**, no se copian | Ruta relativa a una raíz permitida, patrones de exclusión |
| **Subida desde la UI** | Ficheros arrastrados al navegador, de cualquier tamaño (subida por partes) | Ninguna; cada subida queda en una fuente «Subidas» del brain y el original va al almacén de ficheros |

Más adelante, sin cambiar el diseño: repositorio Git, rastreo de una URL, almacenamiento de objetos.

## Modelo de datos

Plano de control (Postgres, migración Alembic):

- `doc_sources`: `id`, `brain_id`, `kind` (`wiki` | `directory` | `upload`), `name`, `config` (JSON; los secretos van cifrados), `enabled`, `sync_interval` (minutos, vacío = solo manual), `status`, `last_sync_at`, `last_error`, `created_by`.
- `documents`: `id`, `brain_id`, `source_id`, `external_id`, `title`, `url`, `mime`, `size`, `sha256`, `storage_ref` (dónde está el original, ver «Almacén de ficheros»), `text_ref` (el texto normalizado sobre el que se trocea), `source_updated_at`, `status` (`active` | `deleted` | `error`), `metadata` (colección, etiquetas), `first_seen_at`, `last_seen_at`, `deleted_at`. Único por `(source_id, external_id)`.
- `doc_jobs`: trabajos de sincronización con progreso (`total`, `done`, `errors`), para mostrarlos en la UI.

Índice (igual que `episode_chunks`: tablas pgvector creadas por el módulo de índice, con la misma dimensión de embedding):

- `doc_chunks`: `document_id`, `brain_id`, `chunk_idx`, `heading_path` (la ruta de títulos, p. ej. «Instalación › Requisitos»), `char_start` y `char_end` (posición del trozo dentro del texto normalizado), `page` (si la fuente tiene páginas), `text`, `content_hash`, `embedding`, `tsv` (texto completo). Índices GIN y HNSW.

**La base de datos no contiene los ficheros.** Guarda la referencia al original, el texto troceado y sus vectores, y cada trozo apunta con su posición al documento completo. Quien recibe un pasaje puede pedir el contexto que lo rodea o el fichero entero.

## Almacén de ficheros

Los originales viven en un **volumen del stack** que monta la aplicación (`MIMIRSYNTH_DOC_STORE`, por defecto `/data/documents`), no en Postgres. Así no hay tope práctico de tamaño y la base se mantiene pequeña.

```
<almacén>/<brain>/<fuente>/<documento>/
    <sha256>.<ext>      el fichero original, inmutable
    <sha256>.txt        el texto normalizado sobre el que apuntan char_start/char_end
```

- **Rutas generadas por el servidor,** nunca a partir de un nombre que mande el usuario: se guarda el nombre original solo como metadato.
- **Subida por partes:** el navegador envía el fichero en trozos (hasta 64 MB (ajustable) por petición, porque los proxies delante de la aplicación suelen limitar el cuerpo) que el servidor escribe a disco en flujo, sin cargarlo en memoria. Hay un tope total configurable en Administración → Ajustes (por defecto, `MIMIRSYNTH_DOC_MAX_MB`).
- **Directorio de archivos:** no se copia nada. `storage_ref` apunta a la ruta dentro de la raíz montada en solo lectura; solo se escribe el texto normalizado cuando el formato lo requiere (HTML, PDF…). Si el fichero desaparece, el documento pasa a `deleted`.
- **Wiki:** se guarda una instantánea en Markdown de cada página, para poder volver a trocear sin pedirla de nuevo y para citar aunque la wiki no responda.
- **Cambio de contenido:** la versión nueva se escribe y se indexa primero; solo entonces se borra la anterior, de modo que nunca se queda un documento sin original.
- **Integridad:** el `sha256` se comprueba al indexar. Un trabajo de mantenimiento detecta ficheros huérfanos (sin fila en la base) y filas con el fichero ausente, que pasan a `error`.
- **Reconstruible:** el índice (`doc_chunks`) se puede regenerar entero desde el almacén, igual que el de episodios desde el grafo. **El volumen es la fuente de verdad y entra en las copias de seguridad junto con Postgres.**
- **`docker compose`:** un volumen con nombre para el almacén y, opcionalmente, montajes de solo lectura para los directorios que se quieran indexar.

## Canalización de ingesta

1. **Descubrir:** el conector lista los documentos de la fuente.
2. **Comparar:** por `source_updated_at` y `content_hash` se decide qué es nuevo, cambiado, igual o desaparecido. Lo igual no se toca.
3. **Extraer:** de Markdown, texto, HTML y RST a texto normalizado conservando la estructura de títulos (se guarda junto al original). PDF solo como extra opcional (sin dependencia obligatoria).
4. **Trocear:** por títulos y párrafos (~900 caracteres con solape, como los episodios), guardando la ruta de títulos y la posición de cada trozo en el texto.
5. **Embeber:** por lotes, con el motor de embeddings configurado y respetando su límite de tasa.
6. **Sustituir:** los trozos de un documento cambiado se reemplazan en una sola transacción, así una consulta nunca ve un documento a medias.
7. **Retirar:** un documento que ya no está en la fuente pasa a `deleted` y sus trozos salen de la búsqueda; el registro se conserva para el historial.

Es idempotente y reanudable: si falla a mitad, la siguiente pasada continúa. Corre en segundo plano con progreso visible (patrón de trabajos del corrector de tipos). Cambiar de modelo de embeddings obliga a una acción explícita «reindexar todo».

## Recuperación

- **Búsqueda propia:** `GET /api/brains/{slug}/docs/search?q=…`, híbrida (texto completo + vectores, fusión RRF) como el recall de episodios. Devuelve pasajes con su cita.
- **Integración en el recall, sin encarecerlo:** el contexto de los agentes gana una sección «Documentos», pero solo cuando aporta.
  - **Presupuesto duro:** como máximo 2 pasajes de ~1.000 caracteres (unos 600 tokens en total), siempre citados.
  - **Solo si hay relevancia:** por debajo de un umbral de puntuación no se añade nada, de modo que una consulta que no trata de documentos no gasta tokens.
  - **Sin lentitud:** la búsqueda documental corre en paralelo con la de hechos y episodios y tiene su propio tiempo máximo; si se pasa, se omite la sección en lugar de retrasar la respuesta.
  - **Desactivable** por petición, y el agente puede pedir después el documento completo o el contexto ampliado de un pasaje solo cuando lo necesite (`GET /docs/{id}/context?chunk=…`, `GET /docs/{id}/file`).
  - Hechos, fragmentos de episodios y documentos se muestran por separado: son tipos de evidencia distintos.
- **Sin mezclar con el grafo** salvo dos puentes opcionales, ambos para una fase posterior:
  - **Enlace a entidades:** marcar qué entidades del grafo menciona cada pasaje (por coincidencia de nombre, sin LLM) para navegar de una entidad a sus documentos.
  - **Promover a memoria:** desde un pasaje, un botón crea una **propuesta en cuarentena** (la misma cola de hoy) para que, si merece ser un hecho, entre por el camino normal de ingesta.

## Permisos y auditoría

| Acción | Rol mínimo |
|---|---|
| Buscar y leer documentos | lector |
| Subir ficheros | colaborador |
| Sincronizar una fuente a mano | curador |
| Crear, editar o borrar fuentes; reindexar | administrador del brain |

Todo queda en la auditoría (qué fuente, quién, cuántos documentos). Borrar una fuente pide confirmación escrita y elimina sus documentos y trozos, como el borrado de un brain.

La **federación** futura tratará los documentos como un recurso concedible aparte del grafo («solo grafo», «solo documentos», «ambos»). Por eso conviene tener el módulo antes de implementarla.

## Seguridad

- **Directorio:** el administrador de la instancia registra las raíces en Administración → Carpetas, siempre bajo el bind de solo lectura `/sources`; un administrador de brain solo elige una raíz y una subruta dentro de ella. Nunca una ruta arbitraria, ni siguiendo enlaces simbólicos fuera de la raíz.
- **Wiki:** solo administradores configuran URL y token. Las redes privadas se permiten (es lo normal en un autoalojado) con un interruptor para prohibirlas en despliegues de empresa.
- **Subidas:** tope de tamaño, tipo comprobado por contenido y no por extensión, HTML reducido a texto. El original solo se devuelve a quien tiene permiso de lectura en el brain, con `Content-Disposition: attachment`; nada se ejecuta ni se sirve como página.
- **Secretos:** cifrados con el mismo `secretbox` que las claves de los motores; nunca se devuelven por la API.

## Interfaz

Una pestaña nueva, **Conocimiento**, hecha solo con el kit de componentes:

- Barra de búsqueda con resultados (pasaje resaltado, cita y enlace).
- Tabla de **fuentes**: estado, última sincronización, número de documentos, «Sincronizar ahora», editar, borrar.
- Tabla de **documentos**: título, fuente, actualizado, trozos, estado y error si lo hay.
- Zona de **subida** (arrastrar y soltar) con progreso por fichero.
- Detalle de documento con sus trozos y su ruta de títulos.

## Fases

1. **D1 — Subida y búsqueda (hecha, 2026-10-23).** Esquema, subida desde la UI, extracción, troceado, embeddings, búsqueda híbrida y la pestaña mínima. Es la rebanada más pequeña que ya sirve de punta a punta, sin conectores.
2. **D2 — Recall (hecha, 2026-10-23).** La sección «Documentos» en el contexto de los agentes y en el hook.
3. **D3 — Directorio (hecha, 2026-10-23).** Fuente de tipo carpeta con reescaneo, y la cola general de trabajos (ver «Directorio y cola de trabajos»).
4. **D4 — Wiki (hecha, 2026-10-23).** Interfaz del adaptador (`wikis.py`) y la implementación para Outline, con sincronización incremental por fecha de modificación (ver «Wikis»).
5. **D5 — Puentes con el grafo (hecha, 2026-10-23).** Entidades mencionadas, documentos que mencionan una entidad y «promover a memoria» (ver «Puentes con el grafo»).

## Decisiones

Tomadas el 2026-10-23:

1. **Originales:** en un volumen del stack, nunca en Postgres. La base guarda la referencia, el texto troceado y los vectores.
2. **Formatos de la primera versión:** Markdown, texto, HTML y RST; PDF como extra opcional.
3. **Documentos en el recall por defecto:** sí, con presupuesto duro, umbral de relevancia y tiempo máximo (ver «Recuperación»).
4. **Sincronización:** manual por ahora, con intervalo opcional por fuente más adelante.
5. **Versiones anteriores de los trozos:** no se conservan; solo es consultable el documento vigente.

Estudiada:

6. **Importar el contenido de un servicio de memoria anterior** (por ejemplo, otro servicio de memoria para agentes). Lo que contiene un servicio así suele ser notas cortas de agentes, no documentos con fichero o URL. Se tratará como una fuente más de tipo «notas» (cada nota, un documento pequeño), indexada solo con embeddings, sin pasar por la extracción del LLM, y etiquetada como archivo con su fecha para que el recall pueda darle menos peso que a lo vigente.

## Directorio y cola de trabajos

**Cola general (`jobs`).** Todo lo que la aplicación hace en segundo plano se registra en una tabla `jobs` (tipo, estado, progreso, registro, resultado, intentos,
quién lo lanzó) y se ejecuta en un pool acotado por tipo. Tipos actuales: `proposal.ingest`, `doc.index`, `doc.scan`, `retype.scan`. Estados: en cola, en marcha,
terminado, fallido, cancelado. La pantalla «Trabajos» (lector o superior) lista, filtra y detalla; curador o superior puede cancelar y reintentar.
Al arrancar, lo que estaba a medias se marca como interrumpido y los tipos idempotentes (`doc.index`, `doc.scan`) se relanzan solos. Se conservan 60 días.
Los manejadores se registran con `@jobs.register(kind, label, limit, resume)` y reciben un `JobCtx` (`progress`, `note`, `retrying`, `check` para cancelar).
Quedan fuera por ahora: la sincronización periódica del índice de episodios (cada 10 min, no es una acción del usuario) y el triaje del decisor (instantáneo).

**Fuente de directorio.** El compose monta un único bind de solo lectura (`MIMIRSYNTH_SOURCES_DIR` del host → `/sources`, con propagación `rslave`: lo que se monte debajo en el host aparece sin reiniciar).
El administrador de la instancia registra las raíces en Administración → Carpetas (tabla `doc_roots`); solo valen rutas bajo `/sources`. Nunca se escribe en ellas.
Una fuente es una raíz más una subcarpeta (que no puede salir de la raíz). Los originales **no se copian**: la base guarda la ruta relativa (`external_id`) y el almacén
solo el texto normalizado. Se ignoran los ocultos, los enlaces simbólicos que salen de la carpeta y lo que no sea un formato admitido o supere el máximo.
El reescaneo compara tamaño y fecha; solo calcula el sha256 de lo que cambió, indexa lo nuevo y lo modificado y retira lo desaparecido.
Protección: si la carpeta no está disponible, el escaneo falla sin borrar nada; si aparece vacía teniendo documentos, el escaneo programado también falla (podría ser un volumen desmontado) y solo uno manual, que es una orden explícita, vacía el índice.
Un documento de carpeta no se borra suelto (reaparecería): se quita la fuente, y los ficheros de la carpeta no se tocan. Reescaneo automático con intervalo por fuente (mínimo 5 min) o manual.

## Wikis

Una fuente de tipo `wiki` lee las páginas de una wiki por su API, en solo lectura, y las trata como cualquier otro documento (troceado, índice, recall, cola de trabajos).
Las implementaciones son Outline (`wikis.Outline`, medida contra una instancia real), Confluence (Cloud y Data Center) y Notion (`wikis.Confluence`, `wikis.Notion`). Estas dos están escritas contra el formato documentado de cada API y cubiertas por tests con respuestas simuladas, **sin validar aún contra una instancia real**: si usas una, revisa el primer escaneo y avisa de cualquier problema. Docmost no tiene todavía una API pública documentada en la que apoyarse y queda sin escribir.
- **Conexión:** URL de la instancia y clave de API. La clave se guarda cifrada (`secretbox`) y no se devuelve nunca por la API. Se recomienda una clave de Outline limitada a
  `documents.list` y `collections.list`. Se eligen las colecciones a indexar tras comprobar la conexión.
- **Solo el administrador de la instancia** conecta o cambia una wiki (nunca un token): el servidor hace peticiones a la URL que se le da.
- **Sincronización incremental:** se compara la fecha `updatedAt` y el título de cada página; solo lo que cambió recalcula el hash y se reindexa.
  Las páginas borradas, archivadas o despublicadas se retiran. El «original» es una instantánea Markdown de la página (con su título como `#`) guardada en el almacén;
  el documento conserva la URL de la página para abrirla en la wiki.
- **Protección:** si la wiki falla a mitad (clave caducada, caída, límite de tasa), la excepción corta el escaneo y no se borra nada. Si devuelve cero páginas teniendo documentos,
  el escaneo programado falla; solo uno manual vacía el índice. Los reintentos por límite de tasa (429) respetan `Retry-After`.
- **Medido contra una instancia real de Outline:** 170 páginas, 527.000 caracteres (~1.200 trozos), listadas en 1,4 s.

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

Reglas del contrato: solo lectura; sin estado; `updated_at` es la fecha de última modificación de la página (es lo que decide si se reindexa); `format` es `markdown` o `html`
(el extractor ya lee ambos, así que Confluence puede devolver su HTML tal cual); un error de conexión o de permisos se lanza como `WikiError` con un mensaje legible,
y cortar la lista a mitad nunca borra nada. Lo demás (cifrado de los campos `secret`, elección de colecciones, sincronización incremental, instantánea del original,
progreso en Trabajos, protección contra vaciados) es común. La configuración se guarda como `{adapter, settings, secrets (cifrados), collection_ids}`.

**Estado de los adaptadores**
- **Outline:** hecho y probado con una instancia real.
- **Obsidian:** no necesita adaptador. Un vault es una carpeta de Markdown: se usa como fuente de directorio. El extractor entiende sus convenciones: quita el frontmatter YAML
  (usa su `title:`), deja el texto de los `[[enlaces]]` y `[[destino|alias]]`, y descarta `![[incrustaciones]]`, `%%comentarios%%` y marcas `^bloque`. `.obsidian/` se ignora por ser oculta.
- **Confluence (Cloud y Data Center) y Notion:** escritos contra el formato documentado de cada API y cubiertos por tests con respuestas simuladas; **sin validar aún contra una instancia real**.
  Confluence usa la API REST v1 (`/rest/api`): Cloud con correo + token de API, Data Center con un token de acceso personal sin correo; las colecciones son los espacios y las páginas llegan como HTML (`body.storage`).
  Notion no tiene espacios: las colecciones son las bases de datos compartidas con la integración más «Páginas sueltas»; los bloques de cada página se convierten a Markdown y el contenido solo se pide cuando cambió la fecha de modificación.
- **Docmost:** sin escribir; su API pública no está documentada de forma estable. Se añadirá cuando lo esté o haya una instancia de prueba.

## Puentes con el grafo

El documento sigue siendo la fuente de verdad; enlazar es señalar, no escribe nada en el grafo.
- **Entidades mencionadas** (`GET /docs/{id}/entities`): se buscan en el texto del documento los nombres y alias de las entidades vivas del grafo (palabra completa, sin
  distinguir mayúsculas; las fusionadas no cuentan, y su nombre antiguo funciona como alias de la principal). Sin LLM ni tablas nuevas: la lista de entidades se cachea un minuto y se
  calcula al abrir el documento, así que siempre está al día. Se ignoran los nombres de menos de 4 caracteres (salvo siglas en mayúsculas de 3, como PBS) y los numéricos.
  En Conocimiento, cada entidad del detalle lleva al Grafo centrado en ella (`/grafo?nodo=<uuid>`).
- **Documentos que mencionan una entidad** (`GET /docs/mentions?entity=<uuid>`): búsqueda de frase en el índice de texto completo con el nombre y los alias; devuelve el documento,
  cuántos pasajes coinciden y el mejor fragmento resaltado. Aparece en el panel de una entidad del Grafo, con enlace al documento (`/conocimiento?doc=<id>`).
- **Promover a memoria** (`POST /docs/{id}/promote`): convierte un pasaje (tal cual o editado por quien promueve) en una propuesta con su procedencia («Fuente: título, sección, URL»),
  confianza 0,7 y fecha de referencia la de la página o fichero. Pasa por el flujo normal: un colaborador la deja en cuarentena, un curador la aprueba y se extraen hechos con Graphiti.
  No se puede promover dos veces el mismo pasaje (409 con la propuesta existente).
