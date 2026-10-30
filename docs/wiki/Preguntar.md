[English](Ask) · **Español**

# Preguntar

Aquí pruebas el **recall**: lo mismo que hace un agente cuando consulta la memoria antes de responder. Sirve para comprobar qué encontraría tu agente y para depurar por qué una respuesta es mala.

## Cómo se usa
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

## Si el resultado es malo
| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| No devuelve nada | Brain vacío o embeddings caídos | [[Resumen]]; probar el motor en [[Proveedores de IA]] |
| Trae hechos viejos | Faltan episodios recientes o no se ingirieron | [[Trabajos]], [[Propuestas]] |
| Devuelve el mismo dato con tres nombres | Entidades duplicadas | [[Vocabulario]] → Duplicados |
| Falta un detalle concreto | Estaba en el texto, no se extrajo como hecho | Mira los *fragmentos*; considera reformular el episodio |
| No salen pasajes de documentos, o salen irrelevantes | Umbral de los pasajes demasiado alto o bajo para el modelo de embeddings | Mídelo con [[Consultas de referencia]] (**Simular**) antes de cambiarlo |
