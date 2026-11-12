**English** · [Español](Consulta-Cypher)

# Cypher query

The **Cypher** tab of the [[Graph]] screen runs **read-only Cypher** queries directly against the brain's graph and draws what they return on the same canvas. It is a tool for advanced users: for when the interface does not offer the view you need. The old `/consulta` address leads to this tab.

## How to use it
1. Write the query in the field (or pick one from **Examples**).
2. Press **Run** or `Ctrl+Enter` (`⌘+Enter` on a Mac).
3. Right under the field, one line says how many rows came back and in how many milliseconds; the result goes below.
4. **History** keeps your last 20 queries in this browser so you can repeat them. Picking an example or a past query replaces what was written, and **Undo** brings it back.

## The result
If the result returns nodes or relations (for example `RETURN a, r, b`), it comes out as a **graph**, and **Show as** switches between **Graph** and **Table**. If it returns only values (a count, a name), it comes out as a table straight away.
- **Graph:** the same canvas as the **Explore** tab, with the force layout in 2D. Hovering a node shows its name and type, and invalidated facts are drawn with a **dashed line**. Each edge carries the name of its relation (`RUNS_ON`), not the generic `RELATES_TO` type. **Clicking a node or an edge** opens its detail beside the canvas: its labels and all its properties as stored in the graph (without the embedding vectors). An entity node has **View page**. It follows the **Graphic effects** picked under **Explore** for this device. There are no halos or expansion here.
- **Table:** one column per returned value; each column can be sorted and filtered by text, and an entity links to its [[Entity page]].

## Limits and safety
- **Read-only:** any query that tries to write (CREATE, DELETE, SET, MERGE…) is rejected.
- **Maximum 500 rows:** if there are more, the result is trimmed and you are told.
- **Maximum time of 15 seconds** per query.
- You only see the active brain's graph.

## Included examples
| Example | Purpose |
|---|---|
| Recently invalidated facts | What has stopped being true lately |
| Neighbourhood of the most connected entity | The facts of the entity with the most relations in the brain |
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
