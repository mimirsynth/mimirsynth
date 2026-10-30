[English](Writing-good-memory) · **Español**

# Escribir buena memoria

La calidad de lo que recuerda MimirSynth depende de lo que le cuentas. Un modelo extrae hechos de tus textos: si el texto es claro, concreto y fechado, el grafo sale limpio; si es vago, sale ruido. Estas pautas valen para personas y para agentes.

## Las reglas de oro
1. **Un hecho concreto por idea, con nombres propios exactos.** «El 12 de octubre la base de datos de producción pasó del servidor db01 al servidor db02» es mucho mejor que «migramos la base de datos».
2. **Pon la fecha.** Si lo que cuentas ocurrió antes, indícalo en el texto (o en `reference_time` si lo envías por API). Así los hechos se ordenan en el tiempo y los antiguos se invalidan bien.
3. **Usa siempre el mismo nombre para la misma cosa.** «Servidor db02», no «el nuevo», «la máquina de bases de datos» y «db-2» en tres textos distintos: se crearían entidades duplicadas.
4. **Cuenta el cambio, no solo el estado.** «Ahora X corre en Y (antes corría en Z)» deja claro qué se invalida. Si un valor antiguo sigue vigente junto al nuevo y la relación está marcada como de un solo valor, aparece en Vocabulario → **Contradicciones** para que un curador lo resuelva.
5. **Escribe afirmaciones autocontenidas.** Cada párrafo debe entenderse sin el contexto de la conversación («eso» y «lo de antes» no sirven).
6. **Incluye el porqué cuando importa.** Las decisiones valen más con su motivo: «Elegimos PostgreSQL porque…».

## Qué conviene recordar (y qué no)
| Sí | No |
|---|---|
| Decisiones y su motivo | Conversación trivial o saludos |
| Cambios de configuración y de infraestructura | Datos que cambian cada minuto (cifras en directo) |
| Causas de fallos y cómo se arreglaron | Secretos: contraseñas, claves, tokens |
| Procedimientos que se repetirán | Información personal ajena sin necesidad |
| Preferencias y reglas del equipo | Texto copiado en bloque de un documento largo (mejor súbelo a [[Conocimiento]]) |

> **Nunca guardes secretos.** Todo lo que entra al grafo se envía al LLM de extracción (que puede ser de un tercero) y queda en la base de datos. Escribe **dónde** está una credencial («en el gestor de contraseñas del equipo»), no su valor. El detector de secretos del brain enmascara o bloquea lo que parece una credencial, y una propuesta con un posible secreto siempre espera a un curador, pero es una red de seguridad, no un permiso.

## Tamaño
- Una propuesta de **unos pocos párrafos** (hasta ~50.000 caracteres de máximo técnico) es lo ideal. Para textos largos, **documentos**.
- Mejor varias propuestas pequeñas y claras que una enorme.

## La confianza
El campo **confianza** (0–1) indica cuánto te fías del dato. Úsalo con honestidad: un agente que no está seguro debería poner 0,5, no 1. El revisor y el decisor lo tienen en cuenta.

## Para agentes
- Escribe **solo lo aprendido** que valga la pena conservar, no un registro de todo lo que ocurre. Por MCP es la herramienta `remember`; di al agente en sus instrucciones cuándo usarla ([[Integración con Claude Code]]).
- Pon un **título descriptivo** y un **texto autocontenido**.
- Comprueba antes con el recall si ya consta, para no repetir.
- Usa un token de **colaborador**: si te equivocas, un curador lo rechaza.

## Documentos o propuestas
- ¿Es **una afirmación breve y concreta** que quieres que el sistema recuerde y razone? → **Propuesta**.
- ¿Es **un texto largo** de referencia (un manual, una página de wiki)? → **Documento** ([[Conocimiento]]). Si un pasaje concreto es importante, **promuévelo a memoria**.

## Después de escribir
Mira el resultado en [[Hechos]] y en el informe de la propuesta ([[Propuestas]]): ¿se extrajo lo que esperabas? Si el sistema crea muchas entidades duplicadas o relaciones raras, el problema suele estar en el vocabulario (ver [[Vocabulario]]) o en un modelo de extracción demasiado pequeño ([[Proveedores de IA]]). Para comprobar con el tiempo que las preguntas importantes siguen trayendo las respuestas correctas, guarda unas cuantas **consultas de referencia** (Preguntar → Consultas de referencia).
