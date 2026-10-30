[English](Jobs) · **Español**

# Trabajos

La **cola de trabajos**: todo lo que la aplicación hace **en segundo plano** en el brain activo. Sirve para ver si algo va lento, falla o espera, y para reintentar o cancelar. La ve cualquiera con acceso al brain (lector o superior).

## Qué es un trabajo
Cualquier tarea que tarda lo suficiente como para no hacerse en la propia petición. El filtro **Tipo** usa estos nombres:

| Tipo | Qué hace | Quién lo lanza |
|---|---|---|
| **Ingesta al grafo** | El LLM extrae entidades y hechos de una propuesta aprobada | Aprobar una propuesta |
| **Indexar documento** | Trocea un documento y calcula sus embeddings | Subir o reindexar un documento, o un escaneo que encuentra cambios |
| **Sincronizar fuente** | Escanea una carpeta o sincroniza una wiki | Una persona, o el reescaneo programado de la fuente |
| **Corrector de tipos** | Analiza las entidades sin tipo o con un tipo que no encaja en la ontología | Un administrador del brain, desde Vocabulario ([[Corrector de tipos]]) |
| **Buscar documentos duplicados** | Revisa los documentos ya indexados y saca del índice los repetidos; no se borra nada del origen | Un administrador del brain, con **Buscar duplicados** en [[Conocimiento]] |
| **Consultas de referencia** | Ejecuta las consultas de referencia del brain, o las simula con otros umbrales de similitud | Un curador, desde Preguntar; también solas antes y después de un cambio de modelo de embeddings |
| **Buscar contradicciones entre hechos** | Comprobación diaria de las relaciones de un solo valor; si encuentra posibles contradicciones, genera un aviso | El sistema, en los brains que han marcado alguna relación como de un solo valor |

El **cambio de modelo de embeddings** (*Cambio de modelo de embeddings (relleno en sombra)* e *(intercambio)*) también corre como trabajos, pero abarca todos los brains a la vez: su progreso, Cancelar, Reintentar y Descartar están en Administración → Embeddings, no en esta pantalla ([[Proveedores de IA]]).

## La lista
Cada trabajo muestra su **tipo**, su **título**, su **estado**, su **progreso** (hecho / total, con barra), quién lo lanzó (o «sistema» si fue automático) y las fechas.

| Estado | Significado |
|---|---|
| En cola | Esperando turno («esperando turno») |
| En curso | Ejecutándose, con su progreso |
| Terminado | Acabó bien |
| Fallido | Acabó con error (se ve el motivo) |
| Cancelado | Lo paraste tú |

Filtros: **Estado** (con contadores), **Tipo** y una búsqueda por título. Cada columna se puede ordenar y filtrar.

## Reescaneos agrupados
Los reescaneos programados de las carpetas se repiten sin cesar y casi nunca encuentran nada. Para no llenar la lista de ruido, las ejecuciones **seguidas e idénticas** que acabaron bien, lanzadas por el sistema, se **pliegan en una sola fila**: «Escaneo programado de carpeta · 20 ejecuciones seguidas sin incidencias», con el rango de fechas. Pulsa **Mostrar N** para desplegarlas y **Ocultar** para plegarlas. Los trabajos fallidos, los reintentos y lo que lanza una persona **siempre se muestran sueltos**.

## Detalle de un trabajo
Al pulsarlo se abre un panel con:
- Fechas de creación, inicio y fin, y **duración**.
- Quién lo lanzó y, si es un reintento, de cuál.
- Los **parámetros** con los que se lanzó.
- El **registro** paso a paso con la hora de cada línea.
- El **error** si falló.

## Acciones
- **Cancelar:** para un trabajo en cola o en curso (se detiene en el siguiente punto seguro).
- **Reintentar:** lanza un trabajo nuevo con los mismos parámetros. Aparece como «reintento de #N».

Para cancelar o reintentar necesitas el rol de **curador** (o superior) en el brain.

## Retención
Para no llenar la base de datos:
- Los reescaneos programados terminados **sin incidencias** se borran a los **7 días**.
- El resto de trabajos terminados, fallidos y cancelados se conservan **60 días**.
La purga corre al arrancar y cada hora. Ambos plazos se cambian en [[Recuerdo e ingesta]].

## Si algo se atasca
- Un trabajo «En curso» durante mucho tiempo suele estar esperando al LLM (límite de peticiones del proveedor): se reintenta solo varias veces antes de fallar. Revisa [[Proveedores de IA]].
- Si el servicio se reinicia con trabajos a medias, al arrancar se marcan como **fallidos («interrumpido por un reinicio del servicio»)** y los reanudables (indexar un documento, sincronizar una fuente y el relleno en sombra de embeddings) se relanzan solos; los demás puedes reintentarlos a mano.
- Un trabajo fallido genera un aviso en la campana y, si están configurados, en los canales de notificación.
- Muchos fallos seguidos con el mismo error: mira el registro del trabajo y [[Solución de problemas]].
