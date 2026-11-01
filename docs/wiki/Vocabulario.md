[English](Vocabulary) · **Español**

# Vocabulario

El **vocabulario** es el **marco** del brain: qué tipos de cosas y de relaciones existen, y cómo se normalizan sus nombres. Vale para todo el brain, cambia poco, se aplica a lo que se ingiera a partir de ahora y lo gestionan los administradores. Sin él, el LLM crea cientos de variantes («CorreEn», «EstáEn», «AlojadoEn…») y tipos que no dicen nada.

El trabajo sobre el **contenido** que ya hay en el grafo (entidades duplicadas, hechos que se contradicen, tipos dudosos, hechos a revisar) no está aquí: está en [[Calidad del contenido]], dentro de Curación, y lo hacen los curadores.

## Lo declarado y lo observado
- **Ontología** es lo **declarado**: lo que se pide al ingestor (qué tipos de entidad y de relación extraer, entre qué tipos, y qué relaciones son de un solo valor o tienen vida útil).
- **Relaciones** y **Tipos de entidad** son lo **observado**: lo que hay de verdad en el grafo, con cuántos hechos o entidades usa cada uno.

Compararlos dice qué falta declarar (una relación muy usada que la ontología no tiene) y qué sobra (una variante que convendría unificar).

## Tarjetas de resumen
| Tarjeta | Qué cuenta |
|---|---|
| **Tipos de relación** | Cuántos hay «crudos» y cuántos tras normalizar el formato |
| **Hechos genéricos** | Hechos en relaciones poco informativas (`RELATES_TO`, `MENTIONED_IN`…) |
| **Cola larga** | Relaciones usadas por muy pocos hechos (≤ 2), que suelen ser ruido |
| **Entidades** | Total |

## Pestañas
Cada pestaña empieza con una o dos frases que dicen para qué sirve, quién la usa y qué pasa al actuar.

| Pestaña | Para qué | Quién |
|---|---|---|
| [[Relaciones y alias]] | Ver las relaciones que hay en el grafo y unificar las variantes con un alias | Lectura: todos · Alias: administrador |
| [[Tipos de entidad]] | Ver, definir, renombrar y fusionar los tipos de entidad | Lectura: todos · Cambios: administrador |
| [[Ontología]] | Declarar qué tipos y relaciones extrae el ingestor, qué relaciones son de **un solo valor a la vez** y cuál es su **vida útil** | Lectura: todos · Cambios: administrador |
| **Alias** | Los alias de relación activos, con opción de quitarlos | Lectura: todos · Quitar: administrador |

## Los alias, entre el marco y el contenido
Un **alias** hace que un nombre de relación se lea como otro (`HostedOn` como `HOSTED_ON`), al leer y al ingerir, sin cambiar los datos del grafo. Se crean con **Unificar con…** en Relaciones y se quitan en Alias.

Los **nombres de las entidades fusionadas** son otra cosa: al fusionar un duplicado en [[Calidad del contenido]] → Duplicados, su nombre se guarda en la entidad principal (su [[Página de entidad]] lo enseña), y lo que se ingiera después con ese nombre va a ella. La pestaña Alias lo explica y enlaza con Duplicados, donde la fusión se deshace desde **Fusiones recientes**.

## Del marco al contenido
Dos marcas de cada relación en [[Ontología]] hacen aparecer trabajo para los curadores:
- **Un solo valor a la vez**: dos destinos vigentes del mismo sujeto salen en [[Calidad del contenido]] → [[Contradicciones]].
- **Vida útil**: un hecho que pasa ese plazo sin confirmar sale en [[Calidad del contenido]] → **A revisar**.

El diálogo de la relación y la cabecera de Ontología enlazan con esas pestañas, y ellas enlazan de vuelta con Ontología.

## Un buen orden de trabajo
1. Aplica un **paquete de ontología** o define tus tipos ([[Ontología]]): evita que el desorden crezca.
2. Tras unas semanas de uso, revisa **Relaciones**: unifica con alias las variantes, y declara en la ontología las relaciones que se usan y no están.
3. Marca como de un solo valor, o con vida útil, solo las relaciones que lo necesiten; mide antes en [[Contradicciones]] → **Medir en todas las relaciones**.
4. Lo que salga de ahí (duplicados, contradicciones, tipos dudosos, hechos a revisar) se trabaja en [[Calidad del contenido]].
5. Vuelve a mirar las tarjetas: deberían bajar la cola larga y los hechos genéricos.

## Reversibilidad
Los **alias** no modifican el grafo (se aplican al leer) y se quitan cuando quieras. Renombrar o fusionar tipos sí cambia datos: muestra una **vista previa**, guarda lo necesario para revertirlo y se **deshace** desde su historial mientras no hagas otro cambio de vocabulario después. Los cambios quedan en la [[Auditoría]].

## Enlaces antiguos
Las direcciones de las pestañas que se movieron a Calidad del contenido (`/vocabulario?tab=dup`, `conflicts`, `stale` y `corrector`, y `/tipos`) siguen funcionando: llevan a la misma herramienta en su sitio nuevo.
