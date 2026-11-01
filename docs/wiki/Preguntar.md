[English](Ask) · **Español**

# Preguntar

Aquí pruebas el **recall**: lo mismo que hace un agente cuando consulta la memoria antes de responder. Sirve para comprobar qué encontraría tu agente y para depurar por qué una respuesta es mala. **Responder** va un paso más allá y redacta la respuesta, con citas.

## Responder: una respuesta redactada con citas
**Modo → Responder** redacta una respuesta corta a la pregunta con ese mismo recall, y cita de dónde sale cada afirmación: `hecho 1`, `episodio 2`, `doc 1`. **Contexto** es el modo que se describe más abajo, que enseña el recall tal cual.
- La respuesta aparece según se escribe. Cada cita es un enlace: un hecho abre la página de su entidad, un episodio lo abre en [[Diario]] y un pasaje abre su documento en [[Conocimiento]]. Lo que presta otro brain no tiene enlace aquí, solo su nombre.
- Debajo, **Pruebas** lista todo lo que trajo el recall, numerado, con lo que citó la respuesta resaltado.
- Al modelo se le pide que use **solo** esas pruebas, que diga cuándo no bastan y que trate el texto de los hechos, episodios y documentos como **datos, nunca como instrucciones**. Una cita a algo que no estaba entre las pruebas sale como «cita sin origen» y no lleva a ningún sitio.
- Si el recall no encuentra nada, responde que no hay información **sin llamar al modelo**.
- Responde en tu idioma, sea cual sea el de los documentos.
- Cada respuesta es una llamada al motor LLM elegido en *Motor para «Responder»* (el predeterminado si está vacío). Cuenta en el [[Consumo de IA]] del brain como «Respuestas redactadas», tiene un límite por persona y hora (*Respuestas por persona y hora*, 30 por defecto) y espera mientras el presupuesto de IA del brain esté agotado con pausa. Ver [[Referencia de ajustes]].
- El modelo puede equivocarse al resumir: las citas están para comprobarlo.

## Cómo se usa (Contexto)
1. Escribe una pregunta o una frase en lenguaje natural (por ejemplo, «¿dónde está la base de datos de producción ahora?»).
2. Ajusta, si quieres, **Hechos** (cuántos hechos traer, 0–30) y **Fragmentos** (cuántos fragmentos de episodios, 0–15).
3. Pulsa **Buscar** o `Ctrl+Enter`.

## Qué devuelve
- **Hechos:** los más parecidos a la pregunta, vigentes e invalidados (los invalidados salen tachados con su rango de fechas). Cada uno muestra su similitud.
- **Fragmentos de episodios:** trozos del **texto original** de los episodios, encontrados por significado y por palabras. Recuperan detalles que la extracción de hechos pudo perder.
- **Pasajes de documentos:** los pasajes de documentos indexados que trajo el recall, cada uno con su título y su similitud. Hay como mucho tantos como marque *Pasajes documentales por recall* del brain (2 por defecto), solo por encima de la *Similitud mínima de un pasaje*, y un mismo texto encontrado en dos documentos sale una sola vez (ver [[Recuerdo e ingesta]]).
- **Contexto inyectado:** el bloque de texto final, con botón de copiar. Es lo que recibiría un agente: hechos vigentes, la evolución de los hechos de las entidades mencionadas y los pasajes de documentos citados.
- **Tiempos:** milisegundos totales y desglosados (embedding, hechos, fragmentos).

Si otro brain le presta su memoria a este (federación), lo que viene de él lleva el nombre de ese brain.

## Cómo se combina
Los hechos y los fragmentos se ordenan por separado y se **fusionan** (rango recíproco) dando algo más de peso a lo **reciente**: una pregunta sobre «ahora» favorece lo último que se supo. No interviene ningún LLM, por eso es rápido (típicamente decenas o pocas centenas de milisegundos).

## El índice de texto
Los fragmentos salen de un **índice del texto de los episodios** que se guarda en PostgreSQL. En la cabecera ves su estado («índice: N fragmentos de M episodios»). Se sincroniza solo cada pocos minutos (ver [[Recuerdo e ingesta]]); los **curadores** pueden pulsar **Reindexar ahora** para forzarlo. Si indica «desactivado», la instancia no tiene PostgreSQL con pgvector y solo se buscarán hechos.

## Guardar una consulta de referencia (curador o superior)
Los curadores y roles superiores ven dos pestañas, **Preguntar** y **Consultas de referencia**. Tras una búsqueda, cada hecho, fragmento y pasaje tiene dos botones: **Debe salir** (tiene que aparecer para esta pregunta) y **Sobra** (no debería). **Guardar como consulta de referencia** abre el formulario ya relleno con la pregunta y lo que hayas marcado (los primeros 200 caracteres de cada resultado), para que el brain pueda comprobar más adelante que el recall lo sigue encontrando. Ver [[Consultas de referencia]].

## Valorar los resultados
Debajo de cada hecho, fragmento de episodio y pasaje de documento, **Útil**, **Irrelevante** e **Incorrecto** (incorrecto solo en los hechos propios del brain) dicen si el recall trajo lo que tocaba. Puede valorar cualquiera que pueda leer el brain, con un límite de peticiones por minuto.
- **Incorrecto** en un hecho, de un colaborador o más, propone su **corrección** (ver [[Propuestas]]): la decide un curador, y desde aquí no se invalida nada. De un lector solo se guarda, y los curadores lo ven en **Calidad**.
- Cada recall, aquí y por la API y el MCP, devuelve un `recall_id` que se puede valorar durante 48 horas; un recall que nadie valoró se olvida después. El recall se registra después de responder, así que valorar nunca lo frena; si no se pudo registrar, ese `recall_id` simplemente no se puede valorar. De la consulta solo se guarda una huella y su longitud, salvo que el brain decida guardar su texto (ver abajo).

## Calidad (curador o superior)
La pestaña **Calidad** resume los últimos 30 días: cuántos recalls hubo y cuántos se valoraron, y por tipo de elemento (hechos, fragmentos de episodios, pasajes de documentos) y por tramo de similitud cuánto fue útil, irrelevante o incorrecto. Los tramos son lo que dice si conviene subir o bajar un umbral como `doc_min_similarity`; **Descargar CSV** los saca. Las valoraciones llegan sobre todo cuando algo falla, así que léelas junto al total de recalls. También lista los últimos hechos valorados como incorrectos, con su corrección.

Los administradores del brain pueden marcar **Guardar el texto de las consultas**: las consultas reales llevan los prompts de las personas, así que por defecto solo se guarda una huella; con esto, el texto se guarda 30 días, y al desmarcarlo se borra ya. Las valoraciones siguen el plazo de retención del brain para **Valoraciones del recall** ([[Administrar brains y miembros]]).

## Si el resultado es malo
| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| No devuelve nada | Brain vacío o embeddings caídos | [[Resumen]]; probar el motor en [[Proveedores de IA]] |
| Trae hechos viejos | Faltan episodios recientes o no se ingirieron | [[Trabajos]], [[Propuestas]] |
| Devuelve el mismo dato con tres nombres | Entidades duplicadas | [[Calidad del contenido]] → Duplicados |
| Falta un detalle concreto | Estaba en el texto, no se extrajo como hecho | Mira los *fragmentos*; considera reformular el episodio |
| No salen pasajes de documentos, o salen irrelevantes | Umbral de los pasajes demasiado alto o bajo para el modelo de embeddings | Mídelo con [[Consultas de referencia]] (**Simular**) antes de cambiarlo |
