[English](Vocabulary) · **Español**

# Vocabulario

El **vocabulario** es el conjunto de tipos de relación y de entidad que existen en el grafo. Con el tiempo, el LLM crea cientos de variantes («CorreEn», «EstáEn», «AlojadoEn»…) y entidades duplicadas («Servidor 1», «servidor-1»), y a veces deja vigentes dos hechos que no pueden ser ciertos a la vez. Esta pantalla sirve para **ver ese desorden y arreglarlo** sin tocar el grafo a mano.

## Tarjetas de resumen
| Tarjeta | Qué cuenta |
|---|---|
| **Tipos de relación** | Cuántos hay «crudos» y cuántos tras normalizar el formato |
| **Hechos genéricos** | Hechos en relaciones poco informativas (`RELATES_TO`, `MENTIONED_IN`…) |
| **Cola larga** | Relaciones usadas por muy pocos hechos (≤ 2), que suelen ser ruido |
| **Entidades** | Total y por tipo |
| **Posibles duplicados** | Entidades con el mismo nombre salvo versión o mayúsculas |

## Pestañas
| Pestaña | Para qué | Quién |
|---|---|---|
| [[Relaciones y alias]] | Ver todas las relaciones y unificar las parecidas con alias | Lectura: todos · Alias: administrador |
| [[Tipos de entidad]] | Ver, renombrar, fusionar y definir los tipos de entidad | Lectura: todos · Cambios: administrador |
| [[Corrector de tipos]] | Reclasificar entidades que quedaron sin tipo o con uno comodín | Administrador |
| [[Ontología]] | Definir qué tipos y relaciones puede extraer el ingestor, y qué relaciones son de un solo valor | Lectura: todos · Cambios: administrador |
| **Alias** | Lista de los alias activos, con opción de quitarlos | Lectura: todos · Quitar: administrador |
| [[Fusionar duplicados]] | Unir entidades que son la misma cosa | Lectura: todos · Fusionar: administrador |
| **A revisar** | Hechos vigentes que han superado la vida útil de su relación: confirma los que siguen siendo ciertos e invalida los demás (ver «Vida útil» en [[Ontología]]) | Curador |
| [[Contradicciones]] | Resolver hechos vigentes que se contradicen en relaciones de un solo valor, y **Medir en todas las relaciones** para saber cuáles lo son | Curador y superiores |

## Un buen orden de trabajo
1. Aplica un **paquete de ontología** o define tus tipos ([[Ontología]]): evita que el desorden crezca.
2. Tras unas semanas de uso, revisa **Relaciones**: unifica con alias las variantes.
3. Revisa **Duplicados** y fusiona.
4. Ejecuta el **Corrector de tipos** para reclasificar entidades genéricas.
5. En **Contradicciones**, usa **Medir en todas las relaciones** y marca como de un solo valor en la ontología solo las relaciones que de verdad admitan un único valor a la vez; después, resuelve los casos que encuentre.
6. Vuelve a mirar las tarjetas: deberían bajar la cola larga y los duplicados.

## Reversibilidad
Los **alias** no modifican el grafo (se aplican al leer) y se quitan cuando quieras. Las operaciones que sí cambian datos (renombrar o fusionar tipos, fusionar entidades, invalidar hechos al resolver una contradicción) muestran una **vista previa** o una confirmación, guardan lo necesario para revertirlas y se pueden **deshacer** desde su historial mientras no hagas otro cambio de vocabulario después. Cada corrección de tipo se deshace por separado desde **Aplicados** en el [[Corrector de tipos]]. Los cambios quedan en la [[Auditoría]].
