[English](Relations-and-aliases) · **Español**

# Relaciones y alias

Pestaña **Relaciones** de [[Vocabulario]]. Lista todos los **tipos de relación** que usan los hechos del grafo (por ejemplo `RUNS_ON`, `HOSTED_ON`, `DEPENDS_ON`), con cuántos hechos tiene cada uno.

## Por qué hace falta
El LLM nombra las relaciones a su manera: «CorreEn», «EstáAlojadoEn», «HostedOn»… Son lo mismo con nombres distintos, y eso fragmenta las búsquedas y ensucia el grafo. Hay que **unificarlas**.

## La tabla
Columnas ordenables y filtrables:
- **Relación (normalizada):** el nombre canónico. Las genéricas (`RELATES_TO`, `MENTIONED_IN`…) llevan la etiqueta **genérica**.
- **Hechos:** cuántos hechos usan esa relación.
- **Variantes crudas:** los nombres originales que se agrupan bajo ella (con filtro por variante).
Puedes mostrar **solo la cola larga** (relaciones con 2 hechos o menos), que es donde suele estar el ruido.

## Unificar con un alias
Un **alias** dice «esta relación se lee como esta otra». Para crearlo (administrador del brain):
1. En la fila de la relación pulsa **Unificar con…**.
2. En **Se lee como**, elige una relación existente o escribe un nombre nuevo.
3. Confirma.

Qué ocurre:
- El alias se aplica **al leer**: los hechos se muestran, se buscan y se cuentan bajo el nombre canónico.
- **No modifica los datos del grafo.** Por eso es seguro y reversible.
- Se aplica también a las ingestas futuras: lo nuevo que llegue con la variante se normaliza.
- [[Contradicciones]] compara las relaciones después de aplicar los alias, así que los hechos escritos con dos variantes de una relación de un solo valor se comparan entre sí.

## Quitar un alias
En la pestaña **Alias** verás todos los alias activos (alias → «se lee como»). **Quitar** devuelve la relación a su nombre propio; los hechos no se tocan.

## Normalización automática de formato
Antes de nada, MimirSynth ya trata como iguales las variantes que solo difieren en formato (mayúsculas, guiones, guiones bajos). La tarjeta de resumen muestra «crudos → tras normalizar formato». Los alias son para sinónimos de *significado* que el formato no resuelve.

## Cuándo no unificar
No unifiques relaciones que significan cosas distintas aunque se parezcan (`DEPENDS_ON` vs `REQUIRES` pueden ser matices que te interese conservar). En caso de duda, mira los hechos de ambas en [[Hechos]] filtrando por relación.
