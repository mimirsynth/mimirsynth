[English](Type-corrector) · **Español**

# Corrector de tipos

Pestaña **Tipos dudosos** de [[Calidad del contenido]] (solo administradores del brain), también llamada corrector de tipos. Reclasifica **entidades que quedaron sin tipo, con un tipo que la ontología no tiene o con un tipo comodín** y que en realidad son otra cosa.

## Por qué existe
Graphiti no cambia el tipo de las entidades ya existentes. Si una aplicación se clasificó una vez como «Organization» (error típico), se queda así para siempre, aunque la ontología mejore. El corrector pone al **decisor** a revisar cada entidad, con los tipos de la ontología como opciones, y propone el correcto. **Tú apruebas** y el cambio es **reversible**.

## Qué revisa
No supone ningún dominio: lo que mira sale de la [[Ontología]] del brain, por este orden:
1. Entidades **sin tipo**.
2. Entidades cuyo tipo **no está en la ontología** (por ejemplo, los tipos por defecto de un agente que escribe directamente en Graphiti).
3. Entidades de los tipos comodín o que más se confunden que indica el paquete (por ejemplo `Topic` o `Item`).

El resto no se toca. Una ontología escrita a mano, o cuyo paquete ya no existe, revisa `Object`, `Thing` y `Topic`.

Algunos nombres se apartan como **Dudosas** sin preguntar al decisor: los de cinco palabras o más en cualquier brain y, solo si el paquete lo activa, los nombres técnicos (rutas de fichero, opciones de línea de comandos, código, versiones al final del nombre, descripciones de un problema). `infrastructure` los activa todos, `software-knowledge` solo las opciones de línea de comandos y el resto de paquetes ninguno. Detalles: «Corrector de tipos» en [`docs/es/ONTOLOGY.md`](https://github.com/MimirSynth/mimirsynth/blob/main/docs/es/ONTOLOGY.md).

## Requisitos
- Una **ontología** aplicada al brain (si no, verás un aviso: [[Ontología]]).
- Un **decisor** configurado ([[Proveedores de IA]]).

## Cómo usarlo
1. Pulsa **Analizar…**, indica en el diálogo cuántas entidades revisar (1–1000) y pulsa **Analizar**. Se lanza un trabajo en segundo plano con barra de progreso (ver [[Trabajos]]); si falla, se muestra el último error.
2. Cuando termine, filtra por **Estado**:
   | Estado | Qué hay |
   |---|---|
   | **Propuestos** | El decisor propone un tipo, con su confianza en porcentaje |
   | **Dudosas** | Nombres que no parecen una entidad concreta (ver arriba). No tiene sentido darles tipo: únelas a la entidad de la que son un detalle (más abajo) o descártalas |
   | **Sin tipo adecuado** | Ningún tipo de la ontología encaja. Si hay muchas de una misma clase, **falta un tipo en la ontología** |
   | **Aplicados** | Ya corregidos |
   | **Unidas** | Nombres que no eran una entidad y se unieron a aquella de la que son un detalle |
   | **Rechazados** | Los que descartaste; no se vuelven a ofrecer |
   | **Ya correctos** | El decisor confirma el tipo actual |
3. En **Propuestos**, ajusta **Confianza mínima** con el deslizador (0,5–0,99) para ver solo las propuestas más seguras. Una nota indica cuántas quedan ocultas por debajo del umbral, con **Ver todas**.
4. **Aplicar** en una fila aplica esa propuesta sola. **Selecciona** las que quieras (hay «seleccionar todo») o actúa sobre todo lo que muestra el filtro:
   - **Aplicar seleccionadas** / **Aplicar todas las visibles**: una confirmación muestra un resumen por tipo propuesto antes de cambiar nada. Aplicar más de una a la vez está **desactivado hasta que hayas decidido 20 propuestas una a una** en este brain (aplicadas, aplicadas como otro tipo o rechazadas, cada una por separado): la confianza del decisor dice poco hasta medirla con tus propias decisiones. Después, junto al umbral, el corrector dice qué parte de las propuestas por encima de él que decidiste una a una aplicaste y mantuviste (ni rechazadas ni deshechas).
   - **Aplicar como…** en una fila: la aplica con otro tipo de la ontología distinto del propuesto, cuando el decisor acierta en la clase pero no en el tipo.
   - **Rechazar seleccionadas** / **Rechazar todas las visibles** (esta última pide confirmación). En **Dudosas**, **Descartar seleccionadas**.

   Solo se aplican o rechazan las filas que muestra el filtro: las ocultas por el umbral de confianza no se tocan nunca.
4b. En **Dudosas**, un nombre que es un detalle de otra entidad (la opción de una herramienta, el fichero de un proyecto, el campo de una API) se puede **unir** a ella. Cuando el análisis aparta un nombre, el decisor dice además de cuál de las entidades con las que comparte hechos vigentes es un detalle (hasta 8, o de ninguna); la fila lo muestra en **Es un detalle de**, con su confianza. **Unir** mueve sus hechos a esa entidad y deja su nombre como alias de ella, como al fusionar duplicados ([[Fusionar duplicados]]); el nodo antiguo no se queda huérfano. **Elegir…** deja escoger otra de esas entidades, o una si el decisor no propuso ninguna. Se deshace con **Deshacer** en **Unidas**, o en Vocabulario → Cambios recientes.
5. Un mensaje informa del resultado, incluido cuántos cambios **no encajaban en la ontología actual** (por ejemplo, un tipo quitado después del análisis) y no se aplicaron.
6. Si te equivocas, cada cambio aplicado tiene su propio **Deshacer** en **Aplicados**, y cada unión en **Unidas**.

Un curador también puede corregir **una entidad** sin el corrector, con **Cambiar tipo** en su [[Página de entidad]]. Su propuesta, si la tenía, deja entonces de estar pendiente.

## Consejos
- Empieza con lotes pequeños (50–100) y decide las primeras una a una: aplicar en bloque espera a 20 de ellas, y luego la parte que mantuviste te dice hasta dónde puedes bajar el umbral.
- Revisa «Sin tipo adecuado»: es la mejor pista de qué tipos añadir a la ontología.
- Si te salen muchas «Dudosas», es señal de que el ingestor está creando entidades de baja calidad: mejora las instrucciones de extracción. Las opciones, rutas de campos, rutas de ficheros, URLs, fechas y frases ya no se crean como entidades al ingerir ([[Ontología]]), así que esas son de antes.
