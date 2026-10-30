[English](Proposals) · **Español**

# Propuestas

La **cuarentena de aportaciones**. Es la única vía por la que entra memoria nueva al grafo: lo que envía un colaborador (o un agente con token de colaborador) **no se incorpora hasta que alguien lo aprueba**. Así un agente que se equivoca, o un texto dudoso, no ensucia la memoria.

## Flujo
```
Enviada ──► (decisor opcional) ──► Pendiente ──► Aprobada ──► Ingerida
                                      │              │
                                      └► Rechazada   └► Fallida ──► (reintentar)
```
1. **Enviar.** Un colaborador queda en *Pendiente*. Un curador (o superior) queda *Aprobada* directamente («aprobada al enviar»), salvo que el detector de secretos haya marcado algo (ver abajo).
2. **Decisor (opcional).** Si hay un modelo decisor configurado, evalúa la propuesta según el **ámbito del brain**: su descripción y los tipos de entidad y de relación de su [[Ontología]]. Sin ninguna de las dos cosas, solo comprueba que la propuesta sea factual. Responde a dos preguntas (¿es factual? ¿qué acción recomienda?) y, si ambas respuestas superan el **umbral de confianza**, la aprueba solo. Si no, la deja para un curador. **Nunca rechaza por su cuenta**: lo que no encaja va a un curador.
3. **Revisión.** Un curador abre la propuesta y la **aprueba** o la **rechaza** (con una nota opcional).
4. **Ingesta.** Una propuesta aprobada se envía al LLM, que extrae entidades y hechos y los añade al grafo (invalidando los que contradice). Pasa a *Ingerida*. Si falla, queda *Fallida* y se puede **reintentar**.

> El decisor sabe de qué trata el brain por su **descripción**: escribe una al crear o editar el brain (Administración → Brains, ver [[Administrar brains y miembros]]).

## La lista
Arriba, el selector **Estado** con un contador por estado: *Todas*, *Pendientes*, *Aprobadas*, *Rechazadas*, *Fallidas*, *Ingeridas*. Se abre en *Pendientes* si hay alguna pendiente y, si no, en *Todas*.

La tabla muestra **Título**, **Autor**, **Confianza**, **Estado** y **Enviada**. Puedes filtrar por título y por autor (**Todos los autores**), ordenar por título, autor, confianza o fecha, y pasar de página con el paginador de abajo. Los filtros y el orden se aplican a **todas las propuestas**, no solo a las filas que ves, así que siempre se llega a las antiguas.

> Un **lector** no ve propuestas ni puede crearlas. Un **colaborador** ve solo las suyas; un **curador** o superior ve todas.

## Crear una propuesta
El formulario encima de la lista, con:
- **Título:** corto y descriptivo («Migración de la base de datos a PostgreSQL 17»).
- **Contenido:** *qué ha pasado o qué hay que recordar, con fecha y nombres exactos*.
- **Confianza (0–1, opcional):** cuánto te fías de ese dato. Se muestra al revisor.

El botón es **Proponer** para un colaborador y **Añadir** para un curador (queda aprobada al enviarla). Consejos para escribir bien: [[Escribir buena memoria]].

## Correcciones
Una **corrección** es una propuesta que no añade memoria: pide **invalidar un hecho** que ya no es cierto. Los agentes la envían con la herramienta MCP `correct` o con `POST /proposals/corrections`, apuntando al hecho por su uuid (el que dan `facts_about`, `timeline` y `whats_new`), con el motivo y, opcionalmente, el texto que lo sustituye y la fecha en que dejó de ser cierto.
- Su título empieza por «Corrección:» y su detalle enseña el **hecho que se invalida** (sujeto → relación → destino, desde cuándo estaba vigente y su uuid), el **motivo** y **lo que lo sustituye**.
- El decisor **nunca** aprueba una corrección y, por MCP, siempre espera a una persona, aunque el token sea de curador. Por la API REST, si la envía un curador se aplica al momento.
- Al aprobarla, el hecho **se invalida, nunca se borra**, con la fecha de la corrección; lo muestra el paso **Hecho invalidado**. Si hay sustituto, se ingiere como cualquier memoria, con esa fecha. La invalidación queda también en el historial del vocabulario, como las que se hacen desde [[Hechos]] o [[Contradicciones]].
- Si el hecho dejó de estar vigente mientras la corrección esperaba, aprobarla da un error y la corrección sigue pendiente: recházala.
- **Reactivar el hecho**, en la propia corrección, lo deja como estaba. El sustituto ya ingerido no se toca.

## Secretos en las propuestas
Antes de guardar una propuesta (desde la interfaz, la API o la herramienta `remember` del MCP), su título y su contenido pasan por el **detector de secretos**: claves de nube y de proveedores de IA, tokens, claves privadas, JWT, cabeceras `Authorization`, contraseñas en URLs… Algunos hallazgos son **seguros**; un valor de aspecto aleatorio asignado a `password`, `secret` o `token` es solo **posible**. Lo que pasa depende de la política del brain (Administración → Acceso al brain → **Secretos**):

| Política | Secretos seguros | Secretos posibles |
|---|---|---|
| **Enmascarar** (por defecto) | Se sustituyen por `[secreto eliminado: tipo]` antes de guardar | Se marcan, sin tocarlos |
| **Bloquear** | La propuesta se **rechaza** con un error que indica el tipo de secreto | Se marcan, sin tocarlos |
| **Solo avisar** | Se marcan, sin tocarlos | Se marcan, sin tocarlos |

- **Una propuesta con algo marcado siempre espera a un curador**, aunque la haya enviado un curador, y el decisor no la aprueba por su cuenta.
- El detalle de la propuesta muestra **Secretos detectados**: qué se enmascaró y qué se marcó para revisar. El valor no se muestra nunca, ni se guarda en la auditoría ni viaja en las notificaciones.
- Guarda los secretos en un gestor de contraseñas y en la memoria solo **dónde** están.

## Detalle de una propuesta
Al abrirla ves una **línea de tiempo**:
- **Enviada:** quién y cuándo, y la confianza declarada.
- **Revisión:** si se aprobó al enviar, la aprobó un curador (con su nota) o la decidió el decisor. Si fue el decisor, se muestra qué modelo, el umbral, sus dos respuestas con su confianza y el veredicto (**Aprobada automáticamente** o **Derivada a un curador**). Si el decisor no estaba disponible, se indica el error.
- **Ingesta en el grafo:** el id del episodio creado, la fecha, y un **informe**: cuántas entidades y hechos se crearon, cuántas entidades quedaron *sin tipo*, qué tipos se salieron de la ontología, qué entidades se fusionaron con su principal, cuáles no se fusionaron por ser ambiguas y cuántas relaciones se normalizaron por un alias.

## Acciones del curador
- **Aprobar / Rechazar** (con nota opcional).
- **Ingerir ahora** o **Reintentar ingesta** cuando una aprobada no se ha ingerido o falló.
- **Reactivar el hecho** en una corrección aplicada.

## Avisos que puedes ver
- **«Sin motor LLM configurado»:** las aprobadas no se ingieren y se quedan en «Aprobadas». Un administrador debe configurarlo en [[Proveedores de IA]].
- **«Sin decisor»:** todas las propuestas de colaboradores esperan a un curador.
- **Ingesta fallida:** mira el motivo en el detalle y en [[Trabajos]]. Los errores más comunes son un límite de peticiones del proveedor o un modelo que no devuelve JSON válido (los modelos «razonadores» a veces necesitan un proxy que desactive el *thinking*).

## Desde un agente
Los agentes crean propuestas por la API REST o con la herramienta `remember` del servidor MCP, y correcciones con la herramienta `correct`: [[Conectar agentes]]. Desde un documento, el botón **Promover a memoria** de [[Conocimiento]] crea una propuesta con el pasaje y su procedencia.
