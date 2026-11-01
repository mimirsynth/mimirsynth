[English](Overview) · **Español**

# Resumen

Pantalla de inicio. Muestra el estado del **brain activo** de un vistazo: cuánto conocimiento tiene, cómo ha evolucionado y qué es lo más importante en él. Salvo el bloque **Necesita tu atención**, es de solo lectura.

## Necesita tu atención
Los curadores y superiores ven primero una lista corta de lo que **espera la decisión de una persona** en el brain, cada línea con su número y un enlace a la herramienta donde se decide:

| Línea | Dónde se decide |
|---|---|
| Propuestas esperando una decisión | [[Propuestas]], filtradas a pendientes |
| Correcciones pendientes, de agentes o de valoraciones «incorrecto» | [[Propuestas]], filtradas a correcciones pendientes |
| Grupos de posibles duplicados | [[Calidad del contenido]] → Duplicados |
| Posibles contradicciones | [[Calidad del contenido]] → Contradicciones |
| Hechos a revisar, pasados de su vida útil | [[Calidad del contenido]] → A revisar |
| Tipos dudosos con un cambio propuesto (solo administradores) | [[Calidad del contenido]] → Tipos dudosos |
| Consultas de referencia que empeoraron en la última ejecución | [[Preguntar]] → Consultas de referencia |

Las líneas a cero no salen, y cuando no hay nada pendiente dice «Nada necesita tu atención». Los contadores son los mismos que calcula cada página y se guardan un minuto para que el inicio sea rápido: algo que acabas de resolver puede seguir contando durante ese minuto (Calidad del contenido los enseña siempre recalculados).

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
