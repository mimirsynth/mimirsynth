[English](Overview) · **Español**

# Resumen

Pantalla de inicio. Muestra el estado del **brain activo** de un vistazo: cuánto conocimiento tiene, cómo ha evolucionado y qué es lo más importante en él. Salvo los bloques **Para empezar**, **Por revisar** y **Movimiento**, es de solo lectura.

## Para empezar
Hasta que hayas probado las partes principales de MimirSynth, la pantalla de inicio empieza con la lista **Para empezar**. Cada paso se marca solo cuando ocurre en cualquiera de tus brains (en todos, para un administrador de la instancia), sin que nadie lo marque, y muestra el día en que ocurrió:

| Paso | Se marca cuando | Se explica en |
|---|---|---|
| Un agente hace su primer recall | un agente hace un recall con un token de API | [[Conectar agentes]] |
| Llega la primera propuesta de un agente | un agente envía una propuesta | [[Propuestas]] |
| Se aprueba la primera propuesta | la aprueba un curador, el decisor o un nivel de autoaprobación (la de un curador, aprobada tal como la envía, no cuenta) | [[Propuestas]] |
| Añades el primer documento o carpeta | un brain tiene un documento, o una carpeta, una wiki o un repositorio como fuente | [[Conocimiento]] |
| Haces tu primera pregunta en Preguntar | buscas o pides tú una respuesta en [[Preguntar]] | [[Preguntar]] |
| Conectas un segundo agente o invitas a otra persona | un brain tiene dos tokens de API vigentes o dos miembros (para un administrador, la instancia tiene dos usuarios) | [[Administrar brains y miembros]] |

Cada paso pendiente enlaza con la pantalla donde se hace y con su página de esta wiki. Un paso marcado no se desmarca aunque después desaparezca lo que lo mostró (un token revocado, un registro de recall pasado su retención). La lista desaparece cuando todos los pasos están hechos; **Cerrar la lista** la oculta para siempre, quede lo que quede. La lista es tuya: cada persona ve la suya.

## Por revisar
Los curadores y superiores ven primero lo que **espera la decisión de una persona** en el brain, con el total arriba. Cada línea lleva su número, una nota de qué es y un botón a la herramienta donde se decide:

| Línea | Botón | Dónde se decide |
|---|---|---|
| Propuestas esperando una decisión (con la fecha de la más antigua) | Revisar | [[Propuestas]], filtradas a pendientes |
| Correcciones pendientes, de agentes o de valoraciones «incorrecto» | Revisar | [[Propuestas]], filtradas a correcciones pendientes |
| Propuestas cuya ingesta falló | Ver | [[Propuestas]] → Decididas, filtradas a fallidas |
| Resúmenes de entidades por aprobar | Revisar | [[Calidad del contenido]] → Resúmenes |
| Grupos de posibles duplicados | Fusionar | [[Calidad del contenido]] → Duplicados |
| Posibles contradicciones | Resolver | [[Calidad del contenido]] → Contradicciones |
| Hechos a revisar, pasados de su vida útil | Revisar | [[Calidad del contenido]] → A revisar |
| Tipos dudosos con un cambio propuesto (solo administradores) | Corregir | [[Calidad del contenido]] → Tipos dudosos |
| Consultas de referencia que empeoraron en la última ejecución | Ver | [[Preguntar]] → Consultas de referencia |

Las líneas a cero no salen, y cuando no hay nada pendiente dice «Nada necesita tu atención». Las propuestas pendientes y lo que espera en Calidad del contenido salen también como contador junto a **Propuestas** y **Calidad del contenido** en el menú lateral. Los contadores son los mismos que calcula cada página y se guardan un minuto para que el inicio sea rápido. Cualquier cambio hecho en el brain (decidir una propuesta, fusionar, resolver una contradicción, confirmar un hecho…) los recalcula, así que se ve al momento; lo que cambia solo (un hecho que pasa su vida útil, un agente que propone por MCP, una ingesta que falla) se ve antes de un minuto. En un brain grande, la primera lectura tras un cambio es más lenta, porque es cuando se hacen los recorridos.

## Movimiento
Al lado, para las mismas personas, **Movimiento** dice qué se ha movido en el brain en las **últimas 24 horas**, los **últimos 7 días** o los **últimos 30 días** (a elegir): hechos nuevos, hechos invalidados, propuestas recibidas y decididas, y documentos añadidos. Cada cifra lleva una minigráfica del periodo (por horas en 24 horas, por días en los demás) y la comparación con el periodo anterior de la misma duración, y abre su página. Son los mismos recuentos del resumen por correo de [[Mi cuenta]], que se los envía a quien los quiera sin abrir la aplicación.

## Qué sabe el brain
Para todos los que pueden leer el brain:
- **Totales:** hechos vigentes, invalidados (los que **dejaron de ser ciertos**, que se conservan como historia), entidades, episodios y documentos, cada uno con enlace a su página, y desde cuándo hay episodios.
- **Actividad semanal:** hechos aprendidos, episodios y hechos invalidados por semana, en las últimas **12 semanas**, **26 semanas** o **1 año**. Sirve para ver si el brain «está vivo» y si hay picos de cambios.
- **Entidades más conectadas:** los nodos con más hechos, que suelen ser los temas centrales del brain; cada uno abre su página de entidad.
- **Entidades por tipo:** las 6 clases con más entidades. Muchas «sin tipo» o genéricas indican que conviene trabajar la ontología ([[Vocabulario]]).
- **Documentos:** cuántos hay indexados y en cuántos trozos, y los que están en cola, indexándose o con error. Los documentos se gestionan en [[Conocimiento]].

## Salud de la memoria
Debajo, para los curadores y superiores, **Salud de la memoria** muestra la última medición diaria del brain: cobertura de las consultas de referencia, resultados con algo desactualizado, ruido, redundancia, contradicciones abiertas, propuestas que se recuperan y hechos a revisar, cada una con el valor de una semana antes. Lo que no se puede medir en este brain (por ejemplo, la cobertura sin consultas de referencia) no ocupa una tarjeta: va en una sola frase, «Sin medir», que dice por qué. **Medir ahora** vuelve a medir. Qué significa cada cifra está en [[Salud de la memoria]].

## Uso de IA
Al lado, solo para los administradores del brain, lo que el brain lleva gastado **este mes** en motores de IA: frente a su presupuesto mensual cuando lo tiene (con la marca del aviso del 80 %), a dónde llegará a fin de mes a este ritmo, en qué se va (extracción de hechos, resúmenes, respuestas…, en porcentaje de los tokens) y cuántas respuestas 429 dio el proveedor. **Ver el detalle** abre Administración → Consumo de IA, donde también se pone el presupuesto ([[Proveedores de IA]]).

## Primeros pasos (instancia nueva)
Un administrador de la instancia que abre la página de inicio cuando **todavía no existe ningún brain** ve en su lugar **Primeros pasos**. El botón **Crea tu primer brain** abre el diálogo para crearlo en Administración ([[Administrar brains y miembros]]), y una breve lista enlaza con cada pantalla:
1. **Crea un brain:** un dominio de conocimiento aislado, con su grafo, su ontología, sus miembros y sus tokens.
2. **Configura los modelos de IA:** un LLM para extraer los hechos y un motor de embeddings, y pruébalos ([[Proveedores de IA]]). Sin ellos las propuestas no se ingieren y el recall no devuelve nada.
3. **Crea un token de API:** uno por agente, para el brain que vaya a usar y con el rol Colaborador ([[Mi cuenta]]).
4. **Conecta un agente:** lee la memoria (recall) y propone hechos por la API o por MCP ([[Conectar agentes]]).

Cualquier otra persona sin acceso a ningún brain ve un mensaje que le pide que un administrador la añada.

## Consejos
- Si todo está a cero, aún no se ha ingerido nada: crea una propuesta ([[Propuestas]]).
- Si los episodios suben pero los hechos no, la extracción no está funcionando: revisa el LLM en [[Proveedores de IA]] y los [[Trabajos]] fallidos.
