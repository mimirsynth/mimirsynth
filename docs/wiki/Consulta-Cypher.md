[English](Cypher-query) · **Español**

# Consulta Cypher

Consola para lanzar consultas **Cypher de solo lectura** directamente contra el grafo del brain. Es una herramienta para usuarios avanzados: cuando la interfaz no ofrece la vista que necesitas.

## Cómo se usa
1. Escribe la consulta en el área de texto (o elige una de **Ejemplos**).
2. Pulsa **Ejecutar** o `Ctrl+Enter`.
3. El resultado aparece debajo, con el número de filas y los milisegundos.
4. **Historial** guarda tus 12 últimas consultas en este navegador para repetirlas.

## El resultado
- **Tabla:** una columna por cada valor devuelto; cada columna se puede ordenar y filtrar por texto.
- **Grafo:** si el resultado devuelve nodos o relaciones (por ejemplo `RETURN a, r, b`), esta pestaña se abre sola y los dibuja en el mismo lienzo que la pantalla [[Grafo]], con disposición de fuerza en 2D. Al pasar por encima de un nodo se ven su nombre y su tipo, al pulsarlo se resaltan él y su vecindad, y los hechos invalidados se dibujan con **línea discontinua**. Sigue los **Efectos gráficos** elegidos en la pantalla Grafo para este dispositivo. Aquí no hay halos ni expansión.

## Límites y seguridad
- **Solo lectura:** cualquier consulta que intente escribir (CREATE, DELETE, SET, MERGE…) se rechaza.
- **Máximo 500 filas:** si hay más, el resultado se recorta y se avisa.
- **Tiempo máximo de 15 segundos** por consulta.
- Solo ves el grafo del brain activo.

## Ejemplos incluidos
| Ejemplo | Para qué |
|---|---|
| Hechos invalidados recientes | Qué ha dejado de ser cierto últimamente |
| Vecindad de una entidad | Todos los hechos de una entidad por nombre |
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
