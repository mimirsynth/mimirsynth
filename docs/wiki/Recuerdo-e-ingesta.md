[English](Recall-and-ingestion) · **Español**

# Recuerdo e ingesta

Dos secciones del grupo **Sistema** de la administración (solo el administrador de la instancia).

## Recuerdo (recall)
Controla cómo se mezclan los **documentos** en el recall que reciben los agentes, y el índice de texto.

| Ajuste | Por defecto | Rango | Qué hace |
|---|---|---|---|
| **Similitud mínima de un pasaje** | 0,66 | 0–1 | Coseno mínimo para que un pasaje documental entre en el recall |
| **Pasajes documentales por recall** | 2 | 0–10 | Máximo de pasajes de documentos que acompañan a los hechos. **0 desactiva** los documentos en el recall |
| **Tiempo máximo de la búsqueda documental** | 0,6 s | 0,1–10 | Si tarda más, el recall responde **sin documentos** (los hechos no se retrasan) |
| **Sincronización del índice de texto** | 10 min | 0–1440 | Cada cuánto se copia el texto de los episodios al índice. **0 = desactivada** |

### Calibrar la similitud
La similitud depende del **modelo de embeddings**. Con `nomic-embed-text` funciona bien 0,66. Si cambias de modelo ([[Proveedores de IA]]), recalíbrala:
- Muy baja → entran pasajes poco relacionados («ruido»).
- Muy alta → no entra casi ninguno.

Prueba con preguntas reales en [[Preguntar]] y mira si los **Pasajes de documentos** que lista son pertinentes. Para medir en lugar de adivinar, guarda **consultas de referencia** del brain ([[Consultas de referencia]], curadores y superiores): preguntas con lo que su recall debe traer y lo que no. **Ejecutar** cuenta los esperados encontrados y los falsos positivos, y **Simular** repite la medida con otros umbrales (por ejemplo `0.68 0.70 0.72`) **sin cambiar este ajuste**.

### Presupuesto del recall documental
Los pasajes se limitan en **número** (2 por defecto), en **tamaño** (~600 tokens en total) y en **tiempo**. Cuando el mismo texto aparece en dos documentos (la misma nota en dos fuentes, o en el brain y en un brain que le presta sus documentos), solo se queda la primera copia, así que los pasajes son los mejores *distintos*. Un agente puede pedir `docs: 0` en una petición concreta para no recibirlos.

### Memoria prestada
Si otros brains le prestan su memoria a este ([[Federación]]), el recall también los consulta y mezcla lo que devuelven con los resultados propios del brain, marcando cada elemento prestado con su origen. Un origen que falla se queda fuera sin romper la consulta. Un agente puede pedir `federated: false` para recibir solo la memoria propia del brain.

### El índice de texto de episodios
Copia el texto de los episodios de FalkorDB a PostgreSQL, troceado, con vectores y búsqueda de texto completo. Se mantiene al día solo con la sincronización periódica; los curadores pueden forzarlo con **Reindexar ahora** en [[Preguntar]]. Se puede **reconstruir** siempre desde el grafo.

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

La purga corre al arrancar y cada hora. Más sobre la cola en [[Trabajos]]. El cambio de modelo de embeddings en sí se explica en [[Proveedores de IA]].

> La **concurrencia** de las llamadas al LLM durante una ingesta se fija con una variable de entorno al arrancar (no se cambia en caliente). Ver [[Variables de entorno]].
