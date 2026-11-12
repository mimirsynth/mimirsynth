[English](Cypher-query) · **Español**

# Consulta Cypher

La pestaña **Cypher** de la pantalla [[Grafo]] lanza consultas **Cypher de solo lectura** directamente contra el grafo del brain y dibuja lo que devuelven en el mismo lienzo. Es una herramienta para usuarios avanzados: cuando la interfaz no ofrece la vista que necesitas. La antigua dirección `/consulta` lleva a esta pestaña.

## Cómo se usa
1. Escribe la consulta en el campo (o elige una en **Ejemplos**).
2. Pulsa **Ejecutar** o `Ctrl+Intro` (`⌘+Intro` en un Mac).
3. Justo debajo del campo, una línea dice cuántas filas ha devuelto y en cuántos milisegundos; el resultado va debajo.
4. **Historial** guarda tus 20 últimas consultas en este navegador para repetirlas. Elegir un ejemplo o una consulta del historial sustituye lo que había escrito, y **Deshacer** lo recupera.

## El resultado
Si el resultado devuelve nodos o relaciones (por ejemplo `RETURN a, r, b`), sale como **grafo**, y **Ver como** cambia entre **Grafo** y **Tabla**. Si solo devuelve valores (un recuento, un nombre), sale directamente como tabla.
- **Grafo:** el mismo lienzo que la pestaña **Explorar**, con disposición de fuerza en 2D. Al pasar por encima de un nodo se ven su nombre y su tipo, y los hechos invalidados se dibujan con **línea discontinua**. Cada arista lleva el nombre de su relación (`RUNS_ON`), no el tipo genérico `RELATES_TO`. **Clic en un nodo o en una arista** abre al lado su detalle: sus etiquetas y todas sus propiedades tal como están en el grafo (sin los vectores de embedding). Un nodo de entidad tiene **Ver página**. Sigue los **Efectos gráficos** elegidos en **Explorar** para este dispositivo. Aquí no hay halos ni expansión.
- **Tabla:** una columna por cada valor devuelto; cada columna se puede ordenar y filtrar por texto, y una entidad es un enlace a su [[Página de entidad]].

## Límites y seguridad
- **Solo lectura:** cualquier consulta que intente escribir (CREATE, DELETE, SET, MERGE…) se rechaza.
- **Máximo 500 filas:** si hay más, el resultado se recorta y se avisa.
- **Tiempo máximo de 15 segundos** por consulta.
- Solo ves el grafo del brain activo.

## Ejemplos incluidos
| Ejemplo | Para qué |
|---|---|
| Hechos invalidados recientes | Qué ha dejado de ser cierto últimamente |
| Vecindad de la entidad más conectada | Los hechos de la entidad con más relaciones del brain |
| Entidades por grado | Ranking por número de hechos |
| Episodios recientes | Qué se ha ingerido últimamente |
| Hechos por tipo de relación | Cuántos hechos hay por relación |

## Modelo de datos (para escribir tus consultas)
- Las entidades son nodos `:Entity` con propiedades como `uuid`, `name`, `summary`.
- Los episodios son nodos `:Episodic` con `name`, `content`, `created_at`.
- Los hechos son aristas `:RELATES_TO` entre entidades, con `name` (tipo de relación), `fact` (el texto), `valid_at`, `invalid_at`, `created_at`.
- Un hecho **vigente** tiene `invalid_at IS NULL`.

```cypher
// Hechos que dejaron de ser ciertos este año, con sus entidades
MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
WHERE r.invalid_at IS NOT NULL AND r.invalid_at >= '2026-01-01'
RETURN a.name AS origen, r.name AS relacion, b.name AS destino, r.invalid_at
ORDER BY r.invalid_at DESC LIMIT 50
```
