[English](Overview) · **Español**

# Resumen

Pantalla de inicio. Muestra el estado del **brain activo** de un vistazo: cuánto conocimiento tiene, cómo ha evolucionado y qué es lo más importante en él. Salvo los bloques **Para empezar**, **Necesita tu atención** y **Lo que ha cambiado**, es de solo lectura.

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

## Necesita tu atención
Los curadores y superiores ven primero una lista corta de lo que **espera la decisión de una persona** en el brain, cada línea con su número y un enlace a la herramienta donde se decide:

| Línea | Dónde se decide |
|---|---|
| Propuestas esperando una decisión | [[Propuestas]], filtradas a pendientes |
| Correcciones pendientes, de agentes o de valoraciones «incorrecto» | [[Propuestas]], filtradas a correcciones pendientes |
| Propuestas cuya ingesta falló (reintentar o rechazar) | [[Propuestas]] → Decididas, filtradas a fallidas |
| Grupos de posibles duplicados | [[Calidad del contenido]] → Duplicados |
| Posibles contradicciones | [[Calidad del contenido]] → Contradicciones |
| Hechos a revisar, pasados de su vida útil | [[Calidad del contenido]] → A revisar |
| Tipos dudosos con un cambio propuesto (solo administradores) | [[Calidad del contenido]] → Tipos dudosos |
| Consultas de referencia que empeoraron en la última ejecución | [[Preguntar]] → Consultas de referencia |

Las líneas a cero no salen, y cuando no hay nada pendiente dice «Nada necesita tu atención». Los contadores son los mismos que calcula cada página y se guardan un minuto para que el inicio sea rápido. Cualquier cambio hecho en el brain (decidir una propuesta, fusionar, resolver una contradicción, confirmar un hecho…) los recalcula, así que se ve al momento; lo que cambia solo (un hecho que pasa su vida útil, un agente que propone por MCP, una ingesta que falla) se ve antes de un minuto. En un brain grande, la primera lectura tras un cambio es más lenta, porque es cuando se hacen los recorridos.

## Lo que ha cambiado
Al lado, para las mismas personas, **Lo que ha cambiado** dice qué se ha movido en el brain en las **últimas 24 horas** o en los **últimos 7 días** (a elegir): hechos nuevos, hechos invalidados, documentos añadidos y propuestas recibidas y decididas. Cada línea abre su página. Son los mismos recuentos del resumen por correo de [[Mi cuenta]], que se los envía a quien los quiera sin abrir la aplicación. Las líneas a cero no salen.

## Salud de la memoria
Debajo, para las mismas personas, **Salud de la memoria** muestra la última medición diaria del brain: cobertura de las consultas de referencia, resultados con algo desactualizado, ruido, redundancia, contradicciones abiertas y hechos a revisar, cada una con el valor de una semana antes. **Medir ahora** vuelve a medir. Qué significa cada cifra está en [[Salud de la memoria]].

## Primeros pasos (instancia nueva)
Un administrador de la instancia que abre la página de inicio cuando **todavía no existe ningún brain** ve en su lugar **Primeros pasos**. El botón **Crea tu primer brain** abre el diálogo para crearlo en Administración ([[Administrar brains y miembros]]), y una breve lista enlaza con cada pantalla:
1. **Crea un brain:** un dominio de conocimiento aislado, con su grafo, su ontología, sus miembros y sus tokens.
2. **Configura los modelos de IA:** un LLM para extraer los hechos y un motor de embeddings, y pruébalos ([[Proveedores de IA]]). Sin ellos las propuestas no se ingieren y el recall no devuelve nada.
3. **Crea un token de API:** uno por agente, para el brain que vaya a usar y con el rol Colaborador ([[Mi cuenta]]).
4. **Conecta un agente:** lee la memoria (recall) y propone hechos por la API o por MCP ([[Conectar agentes]]).

Cualquier otra persona sin acceso a ningún brain ve un mensaje que le pide que un administrador la añada.

## Tarjetas de cifras
| Cifra | Significado |
|---|---|
| **Episodios** | Textos guardados tal cual (notas, mensajes, propuestas aprobadas). Debajo, cuántos se añadieron esta semana. |
| **Entidades** | Cosas distintas que el grafo conoce (servidores, personas, aplicaciones…). |
| **Hechos** | Afirmaciones entre entidades, vigentes e invalidadas. Debajo, los aprendidos esta semana. |
| **Invalidados** | Hechos que **dejaron de ser ciertos**: se conservan como historia. |
| **Comunidades** | Grupos de entidades muy relacionadas entre sí (solo si se han calculado). |

El texto de cabecera indica además el **último episodio** y cuándo llegó.

## Gráficos
- **Actividad semanal (últimas 26 semanas):** hechos aprendidos, episodios y hechos invalidados por semana. Sirve para ver si el brain «está vivo» y si hay picos de cambios.
- **Estado de los hechos:** vigentes, invalidados y *futuros* (los que tienen una fecha de inicio posterior a hoy).
- **Entidades por tipo:** las 8 clases con más entidades. Muchas «sin tipo» o genéricas indican que conviene trabajar la ontología ([[Vocabulario]]).
- **Relaciones más usadas:** los tipos de relación con más hechos. Una cola enorme de relaciones raras suele indicar vocabulario sin normalizar.
- **Entidades más conectadas:** los nodos con más hechos; suelen ser los temas centrales del brain.

## Conocimiento documental
Al final, cuántos **documentos** y **trozos indexados** hay y en qué estado: *indexados*, *indexando*, *en cola*, *con error* o *duplicate* (un documento que repite otro y no se indexa dos veces). Los documentos se gestionan en [[Conocimiento]].

## Consejos
- Si todo está a cero, aún no se ha ingerido nada: crea una propuesta ([[Propuestas]]).
- Si los episodios suben pero los hechos no, la extracción no está funcionando: revisa el LLM en [[Proveedores de IA]] y los [[Trabajos]] fallidos.
