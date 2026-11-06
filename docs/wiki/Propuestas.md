[English](Proposals) · **Español**

# Propuestas

La **cuarentena de aportaciones**. Es la única vía por la que entra memoria nueva al grafo: lo que envía un colaborador (o un agente con token de colaborador) **no se incorpora hasta que alguien lo aprueba**. Así un agente que se equivoca, o un texto dudoso, no ensucia la memoria.

## Flujo
```
Enviada ──► (decisor opcional) ──► Pendiente ──► Aprobada ──► Ingerida
                                      │              │
                                      └► Rechazada   └► Fallida ──► (reintentar o rechazar)
```
1. **Enviar.** Un colaborador queda en *Pendiente*. Un curador (o superior) queda *Aprobada* directamente («aprobada al enviar»), salvo que el detector de secretos haya marcado algo (ver abajo).
2. **Decisor (opcional).** Si hay un modelo decisor configurado, evalúa la propuesta según el **ámbito del brain**: su descripción y los tipos de entidad y de relación de su [[Ontología]]. Sin ninguna de las dos cosas, solo comprueba que la propuesta sea factual. Responde a dos preguntas (¿es factual? ¿qué acción recomienda?) y, si ambas respuestas superan el **umbral de confianza**, la aprueba solo. Si no, la deja para un curador. **Nunca rechaza por su cuenta**: lo que no encaja va a un curador.
3. **Revisión.** Un curador abre la propuesta y la **aprueba** o la **rechaza**. **+ Nota** (o <kbd>N</kbd>) abre una nota opcional y **Qué pasa al decidir** despliega lo que hará cada botón; lo que hay que leer antes de aprobar (una corrección invalida un hecho, los secretos marcados se tapan) se ve siempre. Al decidir aparece un aviso con lo que ha pasado y **Deshacer**. En **Por revisar** sale justo encima de la nota y los botones de la siguiente propuesta, en una línea, así que nada se mueve en la pantalla; en el resto, encima de la lista. Cuando ya no queda nada que hacer con él (la decisión se deshizo o la propuesta está en el grafo) se retira a los pocos segundos, y nunca enlaza a la propuesta que ya está abierta. Un lector de pantalla anuncia cada paso una vez (decidida, entrando en el grafo, el resultado), no la cuenta atrás, y dice cómo deshacer la decisión. El título de la propuesta abierta es un encabezado que da nombre al detalle, y cada entrada de la cola se lee por su título, con la vista previa y las marcas como descripción. Tras decidir, el foco pasa al título de la siguiente propuesta, para que un botón que sigue en su sitio no se pulse otra vez sin querer; al deshacer, la propuesta vuelve a abrirse y el foco vuelve a su entrada en la cola (en una pantalla estrecha, a su título, con el aviso debajo). Al moverse por la cola, la siguiente propuesta se ve al momento mientras se carga su texto completo:
   - **Una aprobación espera 10 segundos** antes de ingerirse, y en ese tiempo se puede deshacer: la propuesta vuelve a *Pendiente* y no entra nada en el grafo. Después, el aviso sigue la ingesta hasta que termina y dice cuántas entidades y hechos se crearon (o que no se extrajo ninguno). Lo que ya está en el grafo se corrige invalidando sus hechos, como el resto de la memoria. Las aprobaciones del decisor y de los webhooks no esperan.
   - **Un rechazo se puede deshacer o reabrir** cuando quieras, salvo que su texto se haya purgado por la retención.
4. **Ingesta.** Una propuesta aprobada se envía al LLM, que extrae entidades y hechos y los añade al grafo (invalidando los que contradice). Pasa a *Ingerida*. Si falla, queda *Fallida* y se puede **reintentar**, o **rechazar** si no merece la pena intentarlo otra vez (un reintento que aún espera se cancela; uno que ya está en marcha se deja terminar).

> El decisor sabe de qué trata el brain por su **descripción**: escribe una al crear o editar el brain (Administración → Brains, ver [[Administrar brains y miembros]]).

## La pantalla
Tiene dos pestañas:
- **Por revisar** (curadores, se abre por defecto) es la cola de lo que espera una decisión.
- **Mis propuestas** tiene el formulario para proponer y lo que has enviado, en todos sus estados.

Un **colaborador** solo tiene la segunda.

### Por revisar
A la izquierda, la **cola** de pendientes; a la derecha, la propuesta abierta con su detalle y los botones **Rechazar** y **Aprobar** siempre a la vista. En una pantalla estrecha se ve una cosa cada vez: encima de la propuesta, **Volver a la cola**, su posición en la cola («3 de 16») y **Anterior** / **Siguiente** para avanzar sin volver; y la propuesta que abres empieza por su título, que recibe el foco, esté donde esté la cola; **Volver a la cola** devuelve el foco a su entrada. En un móvil, un solo selector, **Qué propuestas ver**, sustituye a las filas de **Mostrar** y **Tipo** (Pendientes, Pendientes que añaden, Pendientes que corrigen y Decididas, cada una con su número); la decisión se queda fija abajo, al alcance del pulgar, con **Rechazar** y **Aprobar** de 44 px en pantallas táctiles, donde no aparece la ayuda de los atajos.

- **Orden por riesgo y antigüedad:** primero las correcciones, después las que tienen un secreto por revisar, después las que el brain ya sabe (marcadas **Posible duplicado** si un hecho vigente dice casi lo mismo, o **Posible dato caducado** si se parecen a un hecho que dejó de ser cierto; solo un posible duplicado y un secreto por revisar se marcan en ámbar (una corrección tiene su propia marca rellena), y un posible dato caducado o una confianza baja llevan una marca neutra con icono), después las de poca confianza declarada (menos de 0,6) y, dentro de cada grupo, la más antigua primero. Cada entrada dice quién la envió y cuánto lleva esperando.
- **Atajos de teclado:** <kbd>J</kbd>/<kbd>K</kbd> pasan a la siguiente o a la anterior (un lector de pantalla oye cuál y en qué posición, «#12 · título (3 de 16)»), <kbd>A</kbd> aprueba, <kbd>R</kbd> rechaza, <kbd>X</kbd> la marca para decidir en lote, <kbd>N</kbd> abre la nota (dentro, <kbd>Esc</kbd> vuelve a la propuesta y <kbd>Ctrl</kbd>+<kbd>Intro</kbd> aprueba, como <kbd>A</kbd>) y <kbd>Z</kbd> deshace la última decisión mientras el aviso lo ofrece. No actúan mientras escribes en la nota. Al decidir, se abre sola la siguiente. En una pantalla estrecha, <kbd>A</kbd> y <kbd>R</kbd> solo actúan con la propuesta abierta, nunca sobre una que no has visto. En una propuesta con un secreto por revisar, <kbd>A</kbd> abre la confirmación de **Enmascarar y aprobar**. En una confirmación que no borra nada, <kbd>Intro</kbd> pulsa su botón principal; una abierta con <kbd>A</kbd> devuelve el foco al título de la propuesta al cerrarse.
- **En lote:** marca varias (o **Seleccionar todas**) y usa **Aprobar las seleccionadas** o **Rechazar las seleccionadas**; la barra ya dice cuántas de las marcadas se aprobarían aparte. Una confirmación las lista por número y título, dice cuántas de las seleccionadas decide («¿Aprobar 2 de 3?») y admite una nota común. Las correcciones, las que tienen un secreto por revisar y las que el brain ya sabe o aún no ha comprobado **no se aprueban en lote**: se quedan seleccionadas para decidirlas una a una. Solo entran en el lote las que ves en la cola.
- El selector **Mostrar** cambia entre **Pendientes** y **Decididas**, el historial: aprobadas, ingeridas, rechazadas y fallidas, en una tabla con filtros. La elección queda en la dirección (`?estado=decided`), así que al recargar o compartir el enlace se abre la misma vista. En la cola, la propuesta abierta muestra su tipo solo si es una corrección, y la confianza del autor solo si la indicó: allí todas están pendientes y añadir es lo habitual. Las fechas y los números siguen el idioma de la interfaz (en español, 0,6 y 25/3/26). El selector **Tipo** (*Todas*, *Añaden*, *Corrigen*) filtra las dos vistas, y sus números cuentan dentro del estado que se ve (las decididas, las rechazadas…). La pestaña **Por revisar** dice cuántas hay pendientes solo mientras se ve otra pestaña; dentro, ya lo dice **Pendientes**.

Cuando hay correcciones esperando, un aviso dice cuántas, porque cada una invalida un hecho y solo la decide una persona. **Ver solo las correcciones pendientes** filtra la cola.

### Las tablas
**Decididas** y **Mis propuestas** muestran **#** (el número de la propuesta), **Tipo**, **Título**, **Autor**, **Confianza**, **Estado**, **Enviada** y **Decidida**: quién la decidió (un curador, el decisor, un webhook o su autor al enviarla) y cuándo. El tipo es una marca con un icono y una palabra, **Añade** o **Corrige**, y la de una corrección va rellena, así que se distingue sin depender del color. Puedes filtrar por título y por autor (**Todos los autores**), ordenar por título, autor, confianza, fecha de envío o de decisión (de entrada, las enviadas más recientes primero, como marca la columna **Enviada**), y pasar de página con el paginador de abajo. Los filtros y el orden se aplican a **todas las propuestas**, no solo a las filas que ves, así que siempre se llega a las antiguas.

> Un **lector** no ve propuestas ni puede crearlas. Un **colaborador** ve solo las suyas; un **curador** o superior ve todas.

## Crear una propuesta
En **Mis propuestas**, el formulario (se puede plegar), con:
- **Título:** corto y descriptivo («Migración de la base de datos a PostgreSQL 17»).
- **Contenido:** *qué ha pasado o qué hay que recordar, con fecha y nombres exactos*.
- **Confianza (0–1, opcional):** cuánto te fías de ese dato. Se muestra al revisor.

El botón es **Proponer** para un colaborador y **Crear y aprobar** para un curador: lo que crea un curador no pasa por la cola y entra en el grafo, como dice el formulario, salvo que el detector de secretos marque algo. Consejos para escribir bien: [[Escribir buena memoria]].

## Correcciones
Una **corrección** es una propuesta que no añade memoria: pide **invalidar un hecho** que ya no es cierto. Los agentes la envían con la herramienta MCP `correct` o con `POST /proposals/corrections`, apuntando al hecho por su uuid (el que dan `facts_about`, `timeline` y `whats_new`), con el motivo y, opcionalmente, el texto que lo sustituye y la fecha en que dejó de ser cierto.
- Su título empieza por «Corrección:» y su detalle enseña el **hecho que se invalida** (sujeto → relación → destino, desde cuándo estaba vigente y su uuid), el **motivo** y **lo que lo sustituye**.
- El decisor **nunca** aprueba una corrección y, por MCP, siempre espera a una persona, aunque el token sea de curador. Por la API REST, si la envía un curador se aplica al momento.
- Al aprobarla, el hecho **se invalida, nunca se borra**, con la fecha de la corrección; lo muestra el paso **Hecho invalidado**. Si hay sustituto, se ingiere como cualquier memoria, con esa fecha. La invalidación queda también en el historial del vocabulario, como las que se hacen desde [[Hechos]] o [[Contradicciones]].
- Si el hecho dejó de estar vigente mientras la corrección esperaba, aprobarla da un error y la corrección sigue pendiente: recházala.
- **Reactivar el hecho**, en la propia corrección, lo deja como estaba. El sustituto ya ingerido no se toca.

## Secretos en las propuestas
Antes de guardar una propuesta (desde la interfaz, la API o la herramienta `remember` del MCP), su título y su contenido pasan por el **detector de secretos**: claves de nube y de proveedores de IA, tokens, claves privadas, JWT, cabeceras `Authorization`, contraseñas en URLs… Algunos hallazgos son **seguros**; un valor de aspecto aleatorio asignado a `password`, `secret` o `token` es solo **posible**. Lo que pasa depende de la política del brain (Administración → Brain → **Secretos**):

| Política | Secretos seguros | Secretos posibles |
|---|---|---|
| **Enmascarar** (por defecto) | Se sustituyen por `[secreto eliminado: tipo]` antes de guardar | Se marcan, sin tocarlos |
| **Bloquear** | La propuesta se **rechaza** con un error que indica el tipo de secreto | Se marcan, sin tocarlos |
| **Solo avisar** | Se marcan, sin tocarlos | Se marcan, sin tocarlos |

- **Una propuesta con algo marcado siempre espera a un curador**, aunque la haya enviado un curador, y el decisor no la aprueba por su cuenta.
- **Nunca se aprueba tal cual.** Su botón **Aprobar** pasa a ser **Enmascarar y aprobar**. Una confirmación nombra los tipos de secreto; después, cada valor marcado del título y del texto se sustituye por `[secreto eliminado: tipo]` y la propuesta se aprueba. El valor original no se guarda, ni aunque deshagas la aprobación. La auditoría registra qué tipos se taparon (`proposal.secrets_masked`), nunca los valores. Por la API es `POST /proposals/{id}/mask-and-approve`; `POST /proposals/{id}/approve` responde 409 con una propuesta así.
- **Con Enmascarar, la propuesta de un curador se guarda ya enmascarada y se aprueba al momento:** no queda nada que revisar, porque el valor nunca llega a la memoria.
- **El autor se entera al enviarla:** el formulario dice qué tipos de secreto se enmascararon o se marcaron, la respuesta de `POST /proposals` lleva el mismo texto en `secrets_notice` y el resultado de `remember` lo añade, para que un agente sepa que su texto ha cambiado.
- Después, la lista marca esas propuestas (**Secreto enmascarado** o **Secreto por revisar**, también las aprobadas al momento) y el detalle muestra **Secretos detectados**: qué se enmascaró y qué se marcó para revisar. El valor no se muestra nunca, ni se guarda en la auditoría ni viaja en las notificaciones.
- Guarda los secretos en un gestor de contraseñas y en la memoria solo **dónde** están.

## Detalle de una propuesta
Al abrirla ves una **línea de tiempo**:
- **Enviada:** quién y cuándo, la confianza declarada y la **procedencia** (de dónde dice el autor que sale y en qué formato llegó).
- **Lo que el brain ya sabe** (en las pendientes que añaden conocimiento): los hechos más parecidos al texto de la propuesta, con sus entidades enlazadas, su relación en palabras («hosted on», con el nombre tal cual en su descripción emergente) y sus fechas, para ver si repite o contradice algo. Una primera línea dice qué mirar: **Posible duplicado** si el brain ya dice algo casi igual, un aviso si se parece a algo que dejó de ser cierto, que hay algo muy parecido, o que no hay nada casi igual. Ante un posible duplicado, algo cercano a un hecho que ya no es cierto, o algo muy parecido a un hecho vigente, ese hecho se muestra como **Lo que dice el brain**, y el propio texto de la propuesta, arriba en el detalle, marca las palabras que le añade, así que se leen uno frente al otro sin repetir la propuesta. En la cola, una pendiente muestra una línea sobre su origen (quién la envió, cuándo y su procedencia) en vez de una cronología de tres pasos, y además lo que dijo el decisor si la miró. Cada hecho se marca **Casi igual** (sus palabras están en la propuesta y la propuesta apenas dice más, o los embeddings son casi idénticos) o **Muy parecido** (sus palabras están en la propuesta, que añade más; o una similitud alta), los más cercanos primero, con su similitud a la vista; uno que ya no es cierto sale tachado. Los hechos que solo están relacionados se quedan plegados tras **N hechos solo relacionados**, para que no se lean como evidencia. Una contradicción no se distingue solo por el texto: los hechos más cercanos están ahí para comprobarlo. Si no hay nada parecido, lo dice: sería conocimiento nuevo. El brain lo comprueba en segundo plano en cuanto llega la propuesta (si hay motor de extracción), otra vez cada vez que se abre su detalle y, para las pendientes que nunca se comprobaron (llegaron sin motor o la comprobación falló), cada vez que un curador abre la cola, para que la cola pueda ordenarlas y marcarlas todas. Ante un posible duplicado, rechazar pasa a ser el botón principal: **Rechazar: ya lo sabe**, que deja ese motivo como nota si no escribiste ninguna (<kbd>R</kbd> hace lo mismo). Ante algo que se parece a un hecho que ya no es cierto, **Aprobar** sigue siendo el principal y el rechazo dice **Rechazar: ya no es cierto**, también con su motivo listo. Aprobar cualquiera de las dos pide una confirmación que cita ese hecho, tanto con el botón como con <kbd>A</kbd>; ante un posible duplicado su botón principal, el que pulsa <kbd>Intro</kbd>, es el rechazo, con **Aprobar igualmente** al lado. Lo que solo es muy parecido («Muy parecido a algo que el brain ya sabe: comprueba qué añade la propuesta») no cuenta como sabido: no lleva marca en la cola, no pide confirmación y se puede aprobar en lote. Hasta que esa comprobación responde, **Aprobar** espera (se ve ocupado): una <kbd>A</kbd> pulsada mientras tanto se guarda y aprueba, o pregunta antes, en cuanto el brain ha respondido. Esta consulta no cuenta para la calidad del recall.
- **Revisión:** si se aprobó al enviar, la aprobó un curador (con su nota) o la decidió el decisor. Si fue el decisor, se muestra qué modelo, el umbral, sus dos respuestas con su confianza y el veredicto (**Aprobada automáticamente** o **Derivada a un curador**). Si el decisor no estaba disponible, se indica el error.
- **Ingesta en el grafo:** el id del episodio creado, la fecha, y un **informe**: cuántas entidades y hechos se crearon, cuántas entidades quedaron *sin tipo*, qué tipos se salieron de la ontología, qué entidades se fusionaron con su principal, cuáles no se fusionaron por ser ambiguas y cuántas relaciones se normalizaron por un alias.

## Acciones del curador
- **Aprobar / Rechazar** (con nota opcional).
- **Reabrir** una rechazada, o **Deshacer la aprobación** de una aprobada cuya ingesta aún no ha empezado.
- **Ingerir ahora** o **Reintentar ingesta** cuando una aprobada no se ha ingerido o falló; una fallida también se puede **rechazar**.
- **Reactivar el hecho** en una corrección aplicada.

## Avisos que puedes ver
- **«Sin motor LLM configurado»:** las aprobadas no se ingieren y se quedan en «Aprobadas». Un administrador debe configurarlo en [[Proveedores de IA]].
- **«Sin decisor»:** todas las propuestas de colaboradores esperan a un curador.
- **Ingesta fallida:** mira el motivo en el detalle y en [[Trabajos]]. Los errores más comunes son un límite de peticiones del proveedor o un modelo que no devuelve JSON válido (los modelos «razonadores» a veces necesitan un proxy que desactive el *thinking*).

## Desde un agente
Los agentes crean propuestas por la API REST o con la herramienta `remember` del servidor MCP, y correcciones con la herramienta `correct`: [[Conectar agentes]]. Desde un documento, el botón **Promover a memoria** de [[Conocimiento]] crea una propuesta con el pasaje y su procedencia.
