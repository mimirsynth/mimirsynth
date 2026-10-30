**English** · [Español](Recuerdo-e-ingesta)

# Recall and ingestion

Two sections of the **System** group of administration (instance administrator only).

## Recall
It controls how **documents** are mixed into the recall agents receive, and the text index.

| Setting | Default | Range | What it does |
|---|---|---|---|
| **Minimum similarity of a passage** | 0.66 | 0–1 | Minimum cosine for a document passage to enter recall |
| **Document passages per recall** | 2 | 0–10 | Maximum number of document passages accompanying the facts. **0 disables** documents in recall |
| **Maximum time of the document search** | 0.6 s | 0.1–10 | If it takes longer, recall answers **without documents** (facts are not delayed) |
| **Text index synchronisation** | 10 min | 0–1440 | How often the episode text is copied to the index. **0 = disabled** |

### Calibrating similarity
Similarity depends on the **embedding model**. With `nomic-embed-text`, 0.66 works well. If you change model ([[AI providers]]), recalibrate:
- Too low → loosely related passages get in ("noise").
- Too high → almost none gets in.

Try real questions in [[Ask]] and check whether the **Document passages** it lists are relevant. To measure instead of guessing, keep **reference queries** for the brain ([[Reference queries]], curators and above): questions with what their recall must bring and what it must not. **Run** counts the expected items found and the false positives, and **Simulate** repeats the measurement with other thresholds (for instance `0.68 0.70 0.72`) **without changing this setting**.

### Document recall budget
Passages are limited in **number** (2 by default), **size** (~600 tokens in total) and **time**. When the same text appears in two documents (the same note in two sources, or in the brain and in a brain that lends it its documents), only the first copy is kept, so the passages are the best *different* ones. An agent can ask for `docs: 0` in a particular request to not receive them.

### Lent memory
If other brains lend their memory to this one ([[Federation]]), recall also queries them and merges what they return with the brain's own results, marking each lent item with its origin. A source that fails is left out without breaking the query. An agent can ask for `federated: false` to get only the brain's own memory.

### The episode text index
It copies the text of the episodes from FalkorDB to PostgreSQL, chunked, with vectors and full-text search. It is kept up to date only by the periodic synchronisation; curators can force it with **Reindex now** in [[Ask]]. It can always be **rebuilt** from the graph.

## Ingestion and jobs
| Setting | Default | Range | What it does |
|---|---|---|---|
| **Ingestion retries** | 4 | 1–20 | Attempts when the model answers with a rate limit or a transient error |
| **Batch size when changing the embedding model** | 64 texts | 1–512 | Texts per batch when recomputing vectors with another model. Smaller spreads the load on the provider better |
| **Pause between batches when changing model** | 0 s | 0–600 | Wait between batches to respect the provider's rate limit. On a 429 it also waits for what `Retry-After` says |
| **Model change wait** | 60 s | 1–3600 | How long the switch to a new embedding model waits for vector writes in progress (ingestions, indexing). If they do not finish, the switch is postponed and retried; writes are never cut off |
| **Alert about a stalled model change** | 24 h | 0–8760 | Hours a shadow fill can stay failed or stalled, taking up memory, before the `reindex.orphan` alert ([[Notifications]]) |
| **Keep finished jobs** | 60 days | 1–3650 | After this period finished, failed and cancelled jobs are deleted |
| **Keep scheduled rescans** | 7 days | 1–365 | Automatic rescans with no issues are noise (one every few minutes): they are deleted sooner |

Purging runs on start and every hour. More on the queue in [[Jobs]]. The embedding model change itself is explained in [[AI providers]].

> The **concurrency** of LLM calls during an ingestion is set with an environment variable at startup (it is not changed live). See [[Environment variables]].
