[English](Memory-health) · **Español**

# Salud de la memoria

Una memoria que solo acumula acaba siendo un registro de todo lo que se dijo alguna vez, no de lo que es cierto ahora. La **salud de la memoria** son unas pocas cifras por brain, medidas **una vez al día** y guardadas como serie temporal, que dicen si la memoria mejora o empeora: una versión nueva, otro modelo de embeddings o un cambio de umbral que estropea el recall se ve aquí antes de que un agente responda con un hecho desactualizado.

## Dónde verla
- En el [[Resumen]], en **Salud de la memoria**, para **curadores y superiores**: la última medición y, bajo cada cifra, la de una semana antes. **Medir ahora** vuelve a medir; las cifras de ese día se sustituyen al terminar.
- En el API: `GET /api/brains/{slug}/health?days=90` (las mediciones de los últimos días, de la más antigua a la más reciente, y la última terminada) y `POST /api/brains/{slug}/health/run`.
- En Prometheus, un gauge por cifra y brain (ver [[Métricas]]), para verla en el tiempo o avisar con ella.

## Las cifras
| Cifra | Qué es | Mejor |
|---|---|---|
| **Cobertura** | Proporción de los textos esperados de las [[Consultas de referencia]] del brain que el recall encuentra, contados como los cuenta una ejecución. Vacía si no hay consultas de referencia que esperen algo. | Más alta |
| **Resultados con algo desactualizado** | Proporción de las consultas de referencia cuyo recall trae algo marcado como posiblemente desactualizado: un hecho vigente pasado de la vida útil de su relación, o un fragmento de episodio o un pasaje de documento que afirma algo que ya no es cierto. Un hecho que ya no es cierto y que el recall muestra como historia no cuenta: va marcado como tal. | Más baja |
| **Ruido** | Elementos (hechos, fragmentos y pasajes) que el recall devuelve de media ante una pregunta vaga o fuera de tema: un conjunto integrado (un saludo, una sola palabra, «vale, sigue con lo que estábamos haciendo», en castellano e inglés) más las consultas de referencia que no esperan nada. La proporción que no devolvió nada y el tamaño del contexto están en el API. | 0 |
| **Redundancia** | Proporción de hechos vigentes que repiten otro hecho vigente **entre las mismas dos entidades**: el mismo texto, o embeddings muy cercanos (coseno de 0,93 o más) **con los mismos números e identificadores**. «La wiki usa PostgreSQL 14» y «… 16» son un cambio, no una repetición. Con más de 3.000 hechos candidatos se estima sobre los más recientes y lo dice. | Más baja |
| **Contradicciones abiertas** | Posibles contradicciones en las relaciones funcionales, como las cuenta [[Contradicciones]]. Vacía si ninguna relación es funcional. | Más baja |
| **Propuestas que se recuperan** | Proporción de las propuestas ingeridas en los últimos 30 días cuyos hechos nuevos salieron todos al hacerles su pregunta de control (ver [[Propuestas]] → Se recupera tras ingerirla). Vacía si no se comprobó ninguna. | Más alta |
| **Hechos a revisar** | Hechos vigentes pasados de la vida útil de su relación, como los cuenta [[Calidad del contenido]] → A revisar. Vacía si ninguna relación tiene vida útil. | Más baja |

## Cómo se mide
- **Una vez al día** por brain, poco después de medianoche UTC. El día es la clave de la medición en la base de datos: un reinicio nunca mide dos veces ni se salta un día, y una medición cortada por un reinicio se vuelve a lanzar.
- Corre como un trabajo ([[Trabajos]], «Medir la salud de la memoria»), un brain cada vez.
- La cobertura, lo desactualizado y el ruido salen de **recalls**, un embedding cada uno (las consultas de referencia y ocho preguntas vagas). No se registran para las valoraciones del recall. Un brain que ha llegado a su presupuesto de [[Consumo de IA]] no se prueba ese día; el resto de cifras se mide igual.
- Cada cifra se mide por su cuenta: la que falla queda vacía y se nombra bajo las cifras, y el resto se conserva.
- No se escribe nada en el grafo.
- Las mediciones se guardan 400 días.

## Aviso
Tras cada medición, el evento **health.degraded** de las [[Notificaciones]] salta cuando:
- **la cobertura baja** al menos *Salud de la memoria: avisar si la cobertura baja* (5 puntos por defecto) respecto a la medición anterior. Solo se comparan los textos esperados que están en las dos mediciones, así que añadir, editar o borrar una consulta de referencia nunca cuenta como bajada;
- o una cifra cruza su umbral: *cobertura mínima*, *resultados desactualizados máximos*, *ruido máximo* o *redundancia máxima*. Están desactivados (0) hasta que los fijas.

Los umbrales están en Administración → Ajustes → Notificaciones ([[Referencia de ajustes]]). El aviso dice qué cruzó y se cierra solo cuando una medición posterior vuelve a estar dentro.

## Cómo leerla
- **La cobertura baja** tras una actualización o un cambio de modelo: ejecuta las [[Consultas de referencia]] para ver qué textos esperados dejaron de salir, y simula un umbral.
- **Crecen los resultados desactualizados**: revisa [[Calidad del contenido]] → A revisar y las contradicciones; los hechos que dejaron de ser ciertos es mejor invalidarlos (o corregirlos) que dejarlos vigentes.
- **Ruido por encima de 0**: la similitud mínima del recall puede ser baja para tu modelo de embeddings ([[Recuerdo e ingesta]]).
- **Crece la redundancia**: los agentes escriben la misma lección con otras palabras; ver [[Escribir buena memoria]].
