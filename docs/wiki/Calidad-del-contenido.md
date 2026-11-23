[English](Content-quality) · **Español**

# Calidad del contenido

En **Curación**, en la barra lateral, para curadores y superiores. Reúne el **trabajo de calidad sobre lo que ya hay en el grafo**: entidades que son la misma cosa, hechos que se contradicen, entidades con un tipo dudoso y hechos que hay que volver a confirmar. Cambia cada día y lo hacen los curadores.

El **marco** que hace aparecer este trabajo (qué relación es de un solo valor, cuánto dura cada una, qué tipos existen) está en [[Vocabulario]], y lo gestionan los administradores.

## Resumen
Arriba, una tarjeta por herramienta con lo que **espera una decisión**: grupos de posibles duplicados, posibles contradicciones, tipos dudosos (solo administradores), hechos a revisar y resúmenes propuestos. Los contadores se recalculan cada vez que abres la página y después de cada cambio que hagas en ella; las etiquetas de las pestañas llevan los mismos números.

Una línea debajo apunta a lo que sigue en otro sitio:
- **[[Hechos]]**, para leer y explorar la memoria (navegar, buscar, línea temporal, página de entidad). Un curador también puede invalidar o reactivar hechos allí.
- **[[Preguntar]] → Calidad** y las **[[Consultas de referencia]]**, que miden lo bien que contesta el recall. Lo que producen para un curador (correcciones abiertas por una valoración «incorrecto», consultas de referencia que empeoraron) sale en **Por revisar** del [[Resumen]].

## Pestañas
| Pestaña | Para qué sirve | Quién decide |
|---|---|---|
| **Duplicados** ([[Fusionar duplicados]]) | Grupos de entidades con el mismo nombre salvo mayúsculas, espacios o una versión final. Marca cuáles fusionar y cuál es la principal, o di que no son duplicados. La fusión se deshace desde **Fusiones recientes**. | Administrador (los curadores ven los grupos) |
| [[Contradicciones]] | Hechos vigentes que no pueden ser ciertos a la vez: el mismo sujeto con dos destinos en una relación de un solo valor. Quédate con el que sigue siendo cierto, o di que no es una contradicción. | Curador y superiores |
| **Tipos dudosos** ([[Corrector de tipos]]) | Entidades sin tipo o con uno comodín: el decisor propone un tipo de la ontología y un administrador lo aplica o lo descarta. Cada cambio se deshace por separado. | Administrador |
| **Resúmenes** | Entidades cuyo resumen es una lista de sus propios hechos: el motor propone de una a tres frases, y un curador las corrige si hace falta y las aprueba. Cada aprobación se deshace desde **Cambios recientes**. Ver más abajo. | Curador y superiores (un administrador lanza el análisis) |
| **Temas** | Revisiones de tema: el LLM lee todo lo que la memoria sabe de una entidad y propone qué invalidar, unir, reescribir o añadir, cada cosa con sus pruebas. Un curador aprueba o rechaza cada acción. Ver más abajo. | Curador y superiores (se pide desde la [[Página de entidad]]) |
| **A revisar** | Hechos vigentes que han superado la vida útil de su relación. **Confirma** los que siguen siendo ciertos (renueva la fecha sin tocar el grafo) o **invalida** los demás. | Curador y superiores |
| **Alias repetidos** | Nombres fusionados que solo repiten el nombre de la entidad (sin contar mayúsculas ni espacios) u otro alias, que dejaron fusiones antiguas. La lista dice qué se quita y qué se queda, y no escribe nada; **Limpiar** guarda antes una copia del grafo y después los quita como trabajo en segundo plano. El cambio queda en **Cambios recientes** y se deshace desde ahí o desde **Limpiezas anteriores**; una entidad que cambió después de la limpieza se deja como está. | Administrador |

Cada pestaña empieza diciendo para qué sirve y qué pasa al actuar, y enlaza de vuelta con el sitio de [[Vocabulario]] donde está su interruptor: [[Ontología]] para las relaciones de un solo valor y la vida útil, y **Alias** para los alias de relación, junto a los nombres de las entidades fusionadas.

Los lectores y colaboradores no ven esta entrada en la barra lateral; si abren su dirección, la página les dice que es para curadores.

## Resúmenes
Muchas entidades tienen **como resumen la lista de sus propios hechos**, porque las ingestas anteriores le añadían la frase de cada hecho nuevo. La pestaña **Resúmenes** propone uno mejor y un curador decide:
- **Analizar…** (un administrador del brain) pide cuántas entidades revisar y revisa hasta ese número, empezando por las más conectadas, cuyo resumen pasa de 1.000 caracteres, tiene varias líneas o solo repite sus hechos cuando tiene más de uno. Una sola frase corta con un hecho se deja como está. Para cada una, el motor de resúmenes escribe **de una a tres frases** a partir de los hechos vigentes de la entidad y de los episodios que la mencionan; esos textos le llegan como datos, nunca como instrucciones. El texto propuesto pasa por el detector de secretos del brain.
- **Una entidad, desde su página:** en la [[Página de entidad]], cuando el resumen está oculto o no existe, un curador puede elegir **Proponer un resumen mejor** solo para esa entidad (una llamada, también para una entidad sin resumen); la propuesta aparece aquí, con el motivo «pedido desde su página».
- **Coste:** una llamada al motor por entidad, que cuenta en el [[Consumo de IA]] como **Revisión de resúmenes**. El análisis se detiene si el brain ha agotado su presupuesto de IA y está configurado para pausar. El motor es **Motor para revisar resúmenes** de la [[Referencia de ajustes]], o el motor LLM predeterminado.
- **Revisar** (curadores y superiores): cada propuesta muestra el resumen de **ahora** y el **propuesto**, uno junto al otro. El texto propuesto se puede corregir antes de aprobarlo (**Aprobar con mis cambios**), y queda quién lo corrigió. **Aprobar todas las visibles** aplica los textos propuestos tal como están, con un filtro por número de hechos y por el motivo; una propuesta con algo que el detector de secretos marcó se queda para aprobarla una a una.
- **Aprobar sustituye el propio resumen de la entidad**, solo si sigue siendo el resumen a partir del que se escribió la propuesta; si cambió entretanto (por ejemplo, con una ingesta), la propuesta se **retira** y el próximo análisis la vuelve a mirar. Cada aprobación queda en **Cambios recientes** de [[Tipos de entidad]] con el texto de antes y el de después, y **Deshacer** (allí o en la pestaña) devuelve el texto anterior.
- Una entidad cuyo resumen aprobado gana después muchos hechos (al menos cinco más, y el doble) se vuelve a proponer; un texto aprobado nunca se sobrescribe solo.

## Temas
Una **revisión de tema** mira una entidad entera, cosa que no hacen las demás pestañas, cada una dedicada a un tipo de problema: un proveedor que cambió y dejó vigentes los hechos del antiguo y del nuevo, dos hechos que dicen lo mismo, un hecho mal escrito, algo que dicen los episodios y que ningún hecho guarda.
- **Pedirla:** en la [[Página de entidad]], dentro de **Curación**, un curador elige **Revisar este tema**. Se hace como un trabajo en segundo plano, una por entidad a la vez, y la revisión se abre al terminar. Se rechaza si no hay ningún motor LLM configurado, si el brain ha agotado su presupuesto de IA y está en pausa, y en un brain de solo lectura.
- **Qué lee:** los hechos vigentes y anteriores de la entidad (hasta 150, los más recientes primero), los episodios que la mencionan (hasta 20, los primeros 800 caracteres de cada uno), los hechos vigentes de las entidades con las que se relaciona (hasta 100) y el estado de la sonda que tengan ([[Hechos verificables]]). Todo eso le llega al motor como datos, nunca como instrucciones.
- **Coste:** una llamada al motor LLM predeterminado del brain, que cuenta en el [[Consumo de IA]] como del curador. Dos ajustes del curador la acotan: `topic_calls` (1 por defecto, hasta 5) es cuántas llamadas puede usar una revisión cuando el tema no cabe en una, y `topic_max_tokens` (4.000 por defecto) el tamaño de cada respuesta. Lo que no cabe se queda fuera, y la revisión dice cuánto.
- **Qué propone:** un **estado del tema** corto y acciones, cada una citando los hechos o episodios que la sostienen: **Invalidar** (un hecho que contradice otro hecho o episodio más reciente), **Unir repetidos** (se queda el más preciso y se invalidan los demás), **Reescribir** (un hecho, con la frase corregida), **Quitar por vacío** (un hecho con un comodín o la propia memoria en un extremo) y **Falta en la memoria** (algo que dicen los episodios y ningún hecho). Una respuesta que no sigue el formato esperado hace que la revisión **falle**, y no se guarda nada de ella. Una acción que cita algo que no se le envió, no cita nada, actúa sobre un hecho que no está vigente o no cumple la regla de su tipo se descarta, y la revisión dice cuántas y por qué. El detector de secretos del brain lee todo lo que escribió el motor.
- **Decidir:** cada acción muestra los hechos sobre los que actúa y las pruebas que cita; un hecho tachado ya no está vigente. **Aprobar** la convierte en una corrección que se aplica en el momento, con el motivo y las pruebas de la revisión, que queda auditada y se deshace desde la propia corrección con **Reactivar el hecho**; la corrección de una reescritura lleva el texto nuevo como sustituto, que se ingiere. **Falta en la memoria** pasa, en cambio, a ser una propuesta de texto libre en la cola de [[Propuestas]]. El texto de una reescritura o de lo que falta se puede editar antes de aprobarlo. Con dos o más acciones pendientes, cada una lleva una casilla (**Se aprueba** / **Se rechaza**, todas marcadas al principio), y el botón del bloque, **Aprobar N y rechazar M**, aprueba las marcadas, una a una y por el mismo camino que su propio botón Aprobar, y rechaza las desmarcadas con una nota; una que no se pueda aplicar dice por qué y sigue pendiente. Un token de API no puede decidir en lote. Un hecho que dejó de estar vigente antes de aprobar se deja como está, y la acción lo dice.
- **Precisión por tipo:** qué parte de cada tipo de acción aprobaron los curadores de este brain, junto a la revisión. Nada se aprueba solo.

## Enlaces antiguos
`/vocabulario?tab=dup`, `?tab=conflicts`, `?tab=stale`, `?tab=corrector` y `/tipos` llevan aquí, a la misma pestaña.

## Por revisar
El [[Resumen]] enseña a los curadores un bloque corto con los mismos contadores, más las propuestas y correcciones pendientes y las consultas de referencia que empeoraron, cada línea con un enlace directo a la herramienta. Ver «Por revisar» en [[Resumen]].
