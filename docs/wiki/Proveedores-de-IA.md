[English](AI-providers) · **Español**

# Proveedores de IA

Tres secciones de la administración: **Modelo LLM**, **Embeddings** y **Decisor**. Cada una es una tabla de **motores**: un motor es la combinación de un *endpoint*, una clave y un modelo. MimirSynth habla con cualquier servicio **compatible con la API de OpenAI** (Ollama, vLLM, LM Studio, OpenAI, OpenRouter, un gateway propio…).

## Estado y Comprobar
La cabecera de cada sección muestra el **Estado** de su proveedor («OK · nombre», «sin configurar», «caído · …» o «por variables de entorno») y un botón **Comprobar**. **Comprobar** hace una llamada real al motor en uso, también al que viene de las variables `MIMIRSYNTH_LLM_*` / `MIMIRSYNTH_EMBEDDING_*`, y deja el resultado junto al botón hasta la siguiente comprobación: «Responde · modelo · 120 ms» o el error, con la hora en que se comprobó.

La instancia hace además esta comprobación por su cuenta cada pocos minutos y avisa si un motor deja de responder ([[Notificaciones]]).

## Para qué sirve cada uno
| Motor | Obligatorio | Qué hace |
|---|---|---|
| **LLM** | Sí, para ingerir | Lee las propuestas aprobadas y **extrae entidades y hechos** (usa la librería Graphiti). Sin él, las propuestas aprobadas se quedan en «Aprobadas». |
| **Embeddings** | Sí, para buscar | Convierte textos en vectores para el **recall**, el índice de texto y la búsqueda de documentos. |
| **Decisor** | No | Modelo de **decisión cerrada** (elige entre opciones con probabilidad): triaje automático de propuestas y [[Corrector de tipos]]. Sin él, todo pasa por un curador. |

## Añadir un motor
Botón **Añadir motor**. Campos:
- **Endpoint (base URL):** la dirección de la API, normalmente terminada en `/v1` (`http://ollama:11434/v1`, `https://api.openai.com/v1`…).
- **Clave de API:** se guarda **cifrada**. Para un servicio local sin autenticación suele valer cualquier texto. Al editar, vacío = conservar la actual.
- **Cargar modelos:** pide al endpoint la lista de modelos disponibles. Si el endpoint no la ofrece, escribe el nombre a mano.
- **Modelo:** el modelo a usar. En un motor de embeddings no se puede cambiar después de guardarlo (ver más abajo).
- **Modelo pequeño (solo LLM, opcional):** para tareas ligeras; por defecto el mismo.
- **Umbral de confianza (solo Decisor):** entre 0,50 y 0,99 (por defecto 0,80). Por debajo, la propuesta va a revisión humana.
- **Nombre** y **Activado**.
Pulsa **Guardar**. Después **Probar** hace una llamada real: el resultado («OK…» o el error) aparece bajo el motor.

## La tabla
Columnas: nombre, endpoint, modelo (con la dimensión en embeddings y el umbral en decisores) y **estado** (*por defecto*, *desactivado*, *sin clave*). Acciones por fila: **Probar**, **Por defecto**, **Editar**, **Borrar** y, en un motor de embeddings cuyo modelo no es el que está en uso, **Reindexar**.

Puede haber **varios motores** de cada tipo; el marcado como **Por defecto** es el que se usa. Al **borrar** un motor, los brains que lo usaban pasan al motor por defecto, o a las variables de entorno si no hay otro.

## Variables de entorno como respaldo
Si aún no hay ningún motor en la interfaz, MimirSynth usa `MIMIRSYNTH_LLM_*` y `MIMIRSYNTH_EMBEDDING_*` ([[Variables de entorno]]); cambiarlas exige reiniciar el servicio. Añade aquí el mismo motor para gestionarlo desde la interfaz: un motor añadido aquí tiene prioridad sobre las variables.

## Cambiar el modelo de embeddings
Los vectores guardados dependen del modelo, y vectores de modelos distintos no son comparables. Por eso **el modelo y la dimensión de un motor de embeddings no se pueden editar**: para cambiar de modelo, añade un **motor nuevo** con el modelo nuevo y pasa todo a él con **Reindexar**. Nada de lo que está en uso cambia hasta que confirmas el cambio.

1. **Añade** el motor de embeddings nuevo (sin hacerlo por defecto).
2. Pulsa **Reindexar** en su fila. El diálogo muestra una **estimación**: cuántos elementos del grafo y trozos se recalculan, unas cuántas llamadas al motor, la memoria que hace falta en FalkorDB frente a la libre y el espacio extra en PostgreSQL (el disco libre compruébalo tú). Si FalkorDB no tiene memoria libre suficiente, no empieza.
3. **Calcular en sombra** recalcula con el motor nuevo todos los vectores de todos los brains y los guarda aparte. Un panel muestra el progreso, con **Cancelar**. Puede tardar y consume llamadas al motor.
4. Al terminar, el panel dice que los vectores están **listos en sombra** y que el modelo en uso aún no ha cambiado. Pulsa **Cambiar al modelo nuevo** y marca **He hecho una copia de seguridad de FalkorDB y PostgreSQL**. El cambio completa lo que haya cambiado entretanto, pausa un momento las escrituras de vectores (ingesta, índice, documentos) e intercambia todo de una vez; el motor nuevo pasa a ser el por defecto. Si algo falla, todo sigue con el motor anterior y puedes volver a intentarlo. **Descartar**, en cambio, borra los vectores en sombra.
5. Después, **recalibra la similitud mínima de un pasaje** del recall ([[Recuerdo e ingesta]]): el valor del modelo anterior no vale para el nuevo. Los agentes que escriben directamente en Graphiti siguen con el modelo anterior hasta que los cambies también.

Conviene saber:
- Un cálculo en sombra sin terminar (fallido o cancelado a medias) sigue ocupando memoria: el panel ofrece **Reintentar** (solo calcula lo que falta) y **Descartar**. Si sigue así más horas de las configuradas, salta el aviso `reindex.orphan`.
- Los brains que tienen consultas de referencia ([[Consultas de referencia]]) las ejecutan solos antes del relleno (con el modelo anterior) y después del cambio, y el aviso `refquery.regressed` te dice si el recall ha empeorado.
- El tamaño del lote, la pausa entre lotes, cuánto espera el cambio a las escrituras en curso y cuándo avisar de un cambio parado se ajustan en **Ingesta y trabajos** ([[Referencia de ajustes]]).
- Tu `.env` conserva los valores antiguos de `MIMIRSYNTH_EMBEDDING_*`. Solo importan en una instalación nueva o cuando no hay ningún motor registrado aquí: si dependes de ellos, actualízalos al modelo y la dimensión nuevos.
- Si otro Graphiti escribe en el mismo FalkorDB, **debe usar el mismo modelo** que el motor por defecto.
- Elige un modelo de calidad desde el principio: cambiar después se puede, pero lo recalcula todo. `nomic-embed-text` (768 dimensiones) es una opción local y ligera.

Detalles técnicos: [docs/es/CONFIGURATION.md](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/CONFIGURATION.md).

## Consejos para el LLM
- Para extraer bien hechos conviene un modelo **capaz** (no el más pequeño).
- **Modelos «razonadores»:** algunos devuelven el razonamiento en lugar del JSON y la extracción falla con respuestas vacías. Si ocurre, usa un proxy que desactive el *thinking* o un modelo no razonador.
- **Límites de peticiones:** si tu proveedor limita, la ingesta reintenta varias veces (ver *Reintentos de la ingesta* en [[Recuerdo e ingesta]]) y reduce la concurrencia.
- Un proveedor en la nube recibe el **texto de tus propuestas y episodios**. Si es información sensible, usa un modelo local.

## Consejos para el decisor
- Juzga cada propuesta frente al **ámbito del brain**: su descripción y los tipos de entidad y de relación de su ontología. Rellena la descripción del brain ([[Administrar brains y miembros]]); sin descripción ni ontología solo comprueba que la propuesta sea una afirmación factual. No da por hecho ningún dominio concreto.
- Funciona bien con modelos pequeños (responde pocas opciones).
- Empieza con un **umbral alto (0,9)** para que apruebe solo lo evidente; bájalo si ves que deriva demasiado a revisión.
- Nunca rechaza por su cuenta: lo dudoso o lo que no encaja va a un curador.

## Consumo
**Consumo**, en esta misma sección, enseña lo que gasta cada motor y cada brain: llamadas, tokens, peticiones por minuto y errores 429/5xx, con un coste estimado a partir de un precio por millón de tokens de cada modelo. Ver [[Consumo de IA]].
