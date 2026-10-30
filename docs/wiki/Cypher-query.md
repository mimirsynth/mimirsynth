**English** · [Español](Consulta-Cypher)

# Cypher query

A console to run **read-only Cypher** queries directly against the brain's graph. It is a tool for advanced users: for when the interface does not offer the view you need.

## How to use it
1. Write the query in the text area (or pick one from **Examples**).
2. Press **Run** or `Ctrl+Enter`.
3. The result appears below, with the number of rows and the milliseconds.
4. **History** keeps your last 12 queries in this browser so you can repeat them.

## The result
- **Table:** one column per returned value; each column can be sorted and filtered by text.
- **Graph:** if the result returns nodes or relations (for example `RETURN a, r, b`), this tab opens on its own and draws them on the same canvas as the [[Graph]] screen, with a force layout in 2D. Hovering a node shows its name and type, clicking it highlights it and its neighbourhood, and invalidated facts are drawn with a **dashed line**. It follows the **Graphic effects** chosen on the Graph screen for this device. There are no halos or expansion here.

## Limits and safety
- **Read-only:** any query that tries to write (CREATE, DELETE, SET, MERGE…) is rejected.
- **Maximum 500 rows:** if there are more, the result is trimmed and you are told.
- **Maximum time of 15 seconds** per query.
- You only see the active brain's graph.

## Included examples
| Example | Purpose |
|---|---|
| Recently invalidated facts | What has stopped being true lately |
| Neighbourhood of an entity | All the facts of an entity by name |
| Entities by degree | Ranking by number of facts |
| Recent episodes | What has been ingested lately |
| Facts by relation type | How many facts there are per relation |

## Data model (for writing your queries)
- Entities are `:Entity` nodes with properties such as `uuid`, `name`, `summary`.
- Episodes are `:Episodic` nodes with `name`, `content`, `created_at`.
- Facts are `:RELATES_TO` edges between entities, with `name` (relation type), `fact` (the text), `valid_at`, `invalid_at`, `created_at`.
- A **current** fact has `invalid_at IS NULL`.

```cypher
// Facts that stopped being true this year, with their entities
MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
WHERE r.invalid_at IS NOT NULL AND r.invalid_at >= '2026-01-01'
RETURN a.name AS source, r.name AS relation, b.name AS target, r.invalid_at
ORDER BY r.invalid_at DESC LIMIT 50
```
