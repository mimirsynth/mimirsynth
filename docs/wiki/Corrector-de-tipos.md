[English](Type-corrector) · **Español**

# Corrector de tipos

Pestaña **Corrector de tipos** de [[Vocabulario]] (solo administradores del brain). Reclasifica **entidades que quedaron sin tipo, con un tipo que la ontología no tiene o con un tipo comodín** y que en realidad son otra cosa.

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
1. En **Entidades a analizar** indica cuántas revisar (1–1000) y pulsa **Analizar**. Se lanza un trabajo en segundo plano con barra de progreso (ver [[Trabajos]]); si falla, se muestra el último error.
2. Cuando termine, filtra por **Estado**:
   | Estado | Qué hay |
   |---|---|
   | **Propuestos** | El decisor propone un tipo, con su confianza en porcentaje |
   | **Dudosas** | Nombres que no parecen una entidad concreta (ver arriba). No tiene sentido darles tipo; puedes descartarlas |
   | **Sin tipo adecuado** | Ningún tipo de la ontología encaja. Si hay muchas de una misma clase, **falta un tipo en la ontología** |
   | **Aplicados** | Ya corregidos |
   | **Rechazados** | Los que descartaste; no se vuelven a ofrecer |
   | **Ya correctos** | El decisor confirma el tipo actual |
3. En **Propuestos**, ajusta **Confianza mínima** con el deslizador (0,5–0,99) para ver solo las propuestas más seguras. Una nota indica cuántas quedan ocultas por debajo del umbral, con **Ver todas**.
4. **Selecciona** las que quieras (hay «seleccionar todo») o actúa sobre todo lo que muestra el filtro:
   - **Aplicar seleccionadas** / **Aplicar todas las visibles**: una confirmación muestra un resumen por tipo propuesto antes de cambiar nada.
   - **Rechazar seleccionadas** / **Rechazar todas las visibles** (esta última pide confirmación). En **Dudosas**, **Descartar seleccionadas**.

   Solo se aplican o rechazan las filas que muestra el filtro: las ocultas por el umbral de confianza no se tocan nunca.
5. Un mensaje informa del resultado, incluido cuántos cambios **no encajaban en la ontología actual** (por ejemplo, un tipo quitado después del análisis) y no se aplicaron.
6. Si te equivocas, cada cambio aplicado tiene su propio **Deshacer** en **Aplicados**.

## Consejos
- Empieza con lotes pequeños (50–100) y confianza alta (0,9) para fiarte del criterio del decisor; baja el umbral poco a poco.
- Revisa «Sin tipo adecuado»: es la mejor pista de qué tipos añadir a la ontología.
- Si te salen muchas «Dudosas», es señal de que el ingestor está creando entidades de baja calidad: mejora las instrucciones de extracción.
