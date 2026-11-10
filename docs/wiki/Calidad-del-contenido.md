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
| **Duplicados** ([[Fusionar duplicados]]) | Grupos de entidades con el mismo nombre salvo versión o mayúsculas. Marca cuáles fusionar y cuál es la principal, o di que no son duplicados. La fusión se deshace desde **Fusiones recientes**. | Administrador (los curadores ven los grupos) |
| [[Contradicciones]] | Hechos vigentes que no pueden ser ciertos a la vez: el mismo sujeto con dos destinos en una relación de un solo valor. Quédate con el que sigue siendo cierto, o di que no es una contradicción. | Curador y superiores |
| **Tipos dudosos** ([[Corrector de tipos]]) | Entidades sin tipo o con uno comodín: el decisor propone un tipo de la ontología y un administrador lo aplica o lo descarta. Cada cambio se deshace por separado. | Administrador |
| **Resúmenes** | Entidades cuyo resumen es una lista de sus propios hechos: el motor propone de una a tres frases, y un curador las corrige si hace falta y las aprueba. Cada aprobación se deshace desde **Cambios recientes**. Ver más abajo. | Curador y superiores (un administrador lanza el análisis) |
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

## Enlaces antiguos
`/vocabulario?tab=dup`, `?tab=conflicts`, `?tab=stale`, `?tab=corrector` y `/tipos` llevan aquí, a la misma pestaña.

## Por revisar
El [[Resumen]] enseña a los curadores un bloque corto con los mismos contadores, más las propuestas y correcciones pendientes y las consultas de referencia que empeoraron, cada línea con un enlace directo a la herramienta. Ver «Por revisar» en [[Resumen]].
