[English](Recall-and-ingestion) · **Español**

# Recuerdo e ingesta

Dos secciones del grupo **Sistema** de la administración (solo el administrador de la instancia).

## Recuerdo (recall)
Controla cuánto tiene que parecerse a la pregunta un hecho, un fragmento de episodio o un pasaje para entrar en el recall que reciben los agentes, cómo se mezclan los **documentos** y el índice de texto.

| Ajuste | Por defecto | Rango | Qué hace |
|---|---|---|---|
| **Similitud mínima de un hecho o un fragmento** | 0,55 | 0–1 | Coseno mínimo para que un hecho del grafo o un fragmento de episodio entre en el recall. Si no llega nada, el recall vuelve **vacío** en vez de rellenarse con lo menos lejano. **0 = sin umbral** |
| **Similitud mínima de un pasaje** | 0,66 | 0–1 | Coseno mínimo para que un pasaje documental entre en el recall |
| **Pasajes documentales por recall** | 2 | 0–10 | Máximo de pasajes de documentos que acompañan a los hechos. **0 desactiva** los documentos en el recall |
| **Tiempo máximo de la búsqueda documental** | 0,6 s | 0,1–10 | Si tarda más, el recall responde **sin documentos** (los hechos no se retrasan) |
| **Sincronización del índice de texto** | 10 min | 0–1440 | Cada cuánto se copia el texto de los episodios al índice. **0 = desactivada** |

### Calibrar la similitud
La similitud depende del **modelo de embeddings**. Con `nomic-embed-text` funciona bien 0,66 para los pasajes. Si cambias de modelo ([[Proveedores de IA]]), recalibra los dos umbrales:
- Muy baja → entran hechos o pasajes poco relacionados («ruido»), incluso con una pregunta de la que no hay nada en la memoria.
- Muy alta → no entra casi ninguno.

Prueba con preguntas reales en [[Preguntar]] y mira si los **Pasajes de documentos** que lista son pertinentes. Para medir en lugar de adivinar, guarda **consultas de referencia** del brain ([[Consultas de referencia]], curadores y superiores): preguntas con lo que su recall debe traer y lo que no. **Ejecutar** cuenta los esperados encontrados y los falsos positivos, y **Simular** repite la medida con otros umbrales, de los pasajes o de los hechos y fragmentos (por ejemplo `0,68 0,70 0,72`), **sin cambiar el ajuste**. Un agente también puede pedir su propio umbral en cada llamada (`min_similarity`, ver [[Conectar agentes]]).

### Presupuesto del recall documental
Los pasajes se limitan en **número** (2 por defecto), en **tamaño** (~600 tokens en total) y en **tiempo**. Cuando el mismo texto aparece en dos documentos (la misma nota en dos fuentes, o en el brain y en un brain que le presta sus documentos), solo se queda la primera copia, así que los pasajes son los mejores *distintos*. Un agente puede pedir `docs: 0` en una petición concreta para no recibirlos.

### Memoria prestada
Si otros brains le prestan su memoria a este ([[Federación]]), el recall también los consulta y mezcla lo que devuelven con los resultados propios del brain, marcando cada elemento prestado con su origen. Un origen que falla se queda fuera sin romper la consulta. Un agente puede pedir `federated: false` para recibir solo la memoria propia del brain.

### El índice de texto de episodios
Copia el texto de los episodios de FalkorDB a PostgreSQL, troceado, con vectores y búsqueda de texto completo. Se mantiene al día solo con la sincronización periódica; los curadores pueden forzarlo con **Reindexar ahora** en [[Preguntar]]. Se puede **reconstruir** siempre desde el grafo.

### Confianza y antigüedad
Cada hecho del JSON del recall dice su **nivel de confianza** (`trust`), según de dónde vino, de más a menos:
- **verified**: una sonda lo comprobó ([[Hechos verificables]]);
- **human**: lo aprobó una persona o lo escribió en la aplicación;
- **agent**: un agente decidió guardarlo (`origin: "agent"`);
- **auto**: se capturó de forma automática, o el cliente no lo dijo.

Un token fija lo máximo que pueden declarar sus propuestas (marcar *Para una captura automática* al crearlo lo deja en `auto`), y el `origin` que envía un cliente solo puede bajarlo. Los hechos anteriores a esto no tienen nivel.

Dos ajustes, los dos **desactivados por defecto** en Administración → Recuerdo (recall), cambian el orden:
- **Pesar los hechos por su origen**: un hecho de un agente pesa *Peso de un hecho escrito por un agente* (0,95) y uno automático *Peso de un hecho capturado automáticamente* (0,85).
- **Envejecer los hechos según su relación**: un hecho vigente de una relación con vida útil pierde peso poco a poco, hasta el *Peso de un hecho a revisar* al acabar su vida útil, en vez de todo de golpe al final.

Simúlalos con las [[Consultas de referencia]] antes de activarlos.

## Ingesta y trabajos
| Ajuste | Por defecto | Rango | Qué hace |
|---|---|---|---|
| **Reintentos de la ingesta** | 4 | 1–20 | Intentos cuando el modelo responde con límite de tasa o un error transitorio |
| **Lote al cambiar de modelo de embeddings** | 64 textos | 1–512 | Textos por lote al recalcular los vectores con otro modelo. Más pequeño reparte mejor la carga en el proveedor |
| **Pausa entre lotes al cambiar de modelo** | 0 s | 0–600 | Espera entre lotes para respetar el límite de tasa del proveedor. Con un 429 espera además lo que indique `Retry-After` |
| **Espera del cambio de modelo** | 60 s | 1–3600 | Cuánto espera el paso a un modelo de embeddings nuevo a que terminen las escrituras de vectores en curso (ingestas, indexaciones). Si no terminan, el cambio se aplaza y se reintenta; las escrituras nunca se cortan |
| **Avisar de un cambio de modelo parado** | 24 h | 0–8760 | Horas que un relleno en sombra puede estar fallido o parado, ocupando memoria, antes del aviso `reindex.orphan` ([[Notificaciones]]) |
| **Conservar trabajos terminados** | 60 días | 1–3650 | Pasado este plazo se borran los trabajos terminados, fallidos y cancelados |
| **Conservar reescaneos programados** | 7 días | 1–365 | Los reescaneos automáticos **sin incidencias** son ruido (uno cada pocos minutos): se borran antes |

A cada entidad que toca la ingesta, el LLM del brain le reescribe el **resumen**: incorpora lo que aporta el episodio y lo deja como estaba si no hay nada duradero nuevo. Sin esto, graphiti-core añadiría las frases de los hechos nuevos al resumen anterior sin preguntar al modelo hasta pasar de 2.000 caracteres, y por eso muchos resúmenes se leen como una lista de hechos. Cuesta una llamada por cada lote de entidades tocadas, que cuenta en el [[Consumo de IA]] como ingesta.

La purga corre al arrancar y cada hora. Más sobre la cola en [[Trabajos]]. El cambio de modelo de embeddings en sí se explica en [[Proveedores de IA]].

> La **concurrencia** de las llamadas al LLM durante una ingesta se fija con una variable de entorno al arrancar (no se cambia en caliente). Ver [[Variables de entorno]].
