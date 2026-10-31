[English](AI-consumption) · **Español**

# Consumo de IA

Lo que cada brain gasta en motores de IA, para que un origen de documentos grande o un reindexado no disparen la factura sin que nadie lo vea, y para poder explicar una ingesta lenta.

## Qué se cuenta
Cada llamada que MimirSynth hace a un motor, en el punto donde la hace:

| Uso | Motor | Cuándo |
|---|---|---|
| Extracción de hechos | LLM y embeddings | Al ingerir una propuesta (Graphiti) |
| Decisor | Decisor | Al hacer el triaje de una propuesta |
| Corrector de tipos | Decisor | Al buscar tipos de entidad equivocados |
| Recall | Embeddings | En cada recall, también por MCP, y en la búsqueda de documentos |
| Índice de documentos / de episodios | Embeddings | Al indexar documentos y episodios |
| Edición de hechos | Embeddings | Al editar el texto de un hecho |
| Importación | Embeddings | Al calcular los vectores de un brain importado |
| Cambio de modelo | Embeddings | El relleno en sombra de un cambio de modelo (no en nombre de un brain) |

De cada llamada se guardan los **tokens** (de entrada y de salida) que la respuesta da en su campo `usage`; si una respuesta no lo trae, se estima la entrada (4 caracteres por token) y la llamada se marca como estimada. También se cuentan las respuestas **429** (el proveedor limita el ritmo) y las **5xx**, y el **ritmo**: peticiones por minuto en este momento y el pico del día. Solo se guardan contadores por día, brain, motor y uso, nunca las llamadas ni su texto.

## Dónde se ve
- **Administración → Acceso al brain → Consumo de IA** (administradores del brain): los últimos 30 días del brain, por uso y motor, y su presupuesto.
- **Administración → Modelos de IA → Consumo** (administrador de la instancia): cada motor con sus peticiones por minuto ahora, su pico, sus errores y su precio, y cada brain. Se actualiza cada 15 segundos.

## Coste estimado
Pon un **precio por millón de tokens**, de entrada y de salida, a cada modelo (Consumo → **Precio**). Un modelo sin precio sale como tal y no cuenta en el coste. Con un motor local (Ollama), déjalo a cero: ahí lo que importa es el tiempo.

## Presupuesto mensual
Opcional, por brain, en **tokens** o en **coste estimado**:
- Al **80 %** y al **100 %** sale el aviso `ai.budget`, una vez por mes y nivel (ver [[Notificaciones]]).
- Con **Pausar la ingesta al agotarlo**, al 100 % el brain deja de ingerir propuestas. Una propuesta aprobada espera, marcada «en pausa», sin perderse; sigue sola al subir el presupuesto o al cambiar de mes (se comprueba cada diez minutos). El recall, el decisor y la indexación de documentos no se pausan.

Los cambios de presupuesto y de precios quedan en la auditoría (`brain.ai_budget`, `ai.price`).

## API
`GET /api/brains/{slug}/ai-usage?days=30` y `PUT /api/brains/{slug}/ai-budget` (`{"limit", "unit": "tokens" | "cost", "pause"}`; un `limit` vacío lo quita), para administradores del brain. `GET /api/ai-usage?days=30`, `PUT /api/ai-usage/prices` (`{"kind", "model", "price_in", "price_out"}`) y `DELETE /api/ai-usage/prices?kind=&model=`, para el administrador de la instancia. Ver [[API REST]].
