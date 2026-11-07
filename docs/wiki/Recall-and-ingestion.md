**English** · [Español](Recuerdo-e-ingesta)

# Recall and ingestion

Two sections of the **System** group of administration (instance administrator only).

## Recall
It controls how relevant a fact, an episode fragment or a document passage must be to enter the recall agents receive, how **documents** are mixed in, and the text index.

| Setting | Default | Range | What it does |
|---|---|---|---|
| **Minimum similarity of a fact or a fragment** | 0.55 | 0–1 | Minimum cosine for a graph fact or an episode fragment to enter recall. If nothing reaches it, recall comes back **empty** instead of filling up with the least distant. **0 = no threshold** |
| **Minimum similarity of a passage** | 0.66 | 0–1 | Minimum cosine for a document passage to enter recall |
| **Document passages per recall** | 2 | 0–10 | Maximum number of document passages accompanying the facts. **0 disables** documents in recall |
| **Maximum time of the document search** | 0.6 s | 0.1–10 | If it takes longer, recall answers **without documents** (facts are not delayed) |
| **Text index synchronisation** | 10 min | 0–1440 | How often the episode text is copied to the index. **0 = disabled** |

### Calibrating similarity
Similarity depends on the **embedding model**. With `nomic-embed-text`, 0.66 works well for passages. If you change model ([[AI providers]]), recalibrate both thresholds:
- Too low → loosely related facts or passages get in ("noise"), even for a question with nothing in memory.
- Too high → almost none gets in.

Try real questions in [[Ask]] and check whether the **Document passages** it lists are relevant. To measure instead of guessing, keep **reference queries** for the brain ([[Reference queries]], curators and above): questions with what their recall must bring and what it must not. **Run** counts the expected items found and the false positives, and **Simulate** repeats the measurement with other thresholds, of the passages or of the facts and fragments (for instance `0.68 0.70 0.72`), **without changing the setting**. An agent can also ask for its own threshold in each call (`min_similarity`, see [[Connect agents]]).

### Document recall budget
Passages are limited in **number** (2 by default), **size** (~600 tokens in total) and **time**. When the same text appears in two documents (the same note in two sources, or in the brain and in a brain that lends it its documents), only the first copy is kept, so the passages are the best *different* ones. An agent can ask for `docs: 0` in a particular request to not receive them.

### Lent memory
If other brains lend their memory to this one ([[Federation]]), recall also queries them and merges what they return with the brain's own results, marking each lent item with its origin. A source that fails is left out without breaking the query. An agent can ask for `federated: false` to get only the brain's own memory.

### The episode text index
It copies the text of the episodes from FalkorDB to PostgreSQL, chunked, with vectors and full-text search. It is kept up to date only by the periodic synchronisation; curators can force it with **Reindex now** in [[Ask]]. It can always be **rebuilt** from the graph.

### Current state first
With **Answer first with the current state** (Administration → Recall, off by default), a question about the present starts with the **current state** of the entities its first facts are about, up to two. That is the current value of each relation, before any other fact, fragment or passage. A relation a curator marked functional shows only its newest value and says how many others are still current (a possible contradiction); any other relation lists all its current values. A question about the past («before», «history», «what was») does not get it, and what stopped being true stays in its own section. The card is read from the graph when asked, so it is always current. It is also in the recall's JSON (`state`) and at `GET /api/brains/{slug}/entities/{uuid}/state`. Reference queries can simulate it (`params.state_card`).

### Trust and age
Every fact in the recall's JSON says its **trust tier** (`trust`), from where it came, highest first:
- **verified**: a probe checked it ([[Verifiable facts]]);
- **human**: a person approved it or wrote it in the application;
- **agent**: an agent chose to store it (`origin: "agent"`);
- **auto**: captured automatically, or a client that did not say.

A token sets the most its proposals can claim (*For an automatic capture* when it is created makes it `auto`), and the `origin` a client sends can only lower it. Facts from before this have no tier.

Two settings, both **off by default** under Administration → Recall, change the order:
- **Weigh facts by their origin**: an agent's fact weighs *Weight of a fact written by an agent* (0.95) and an automatic one *Weight of a fact captured automatically* (0.85).
- **Age facts by their relation**: a current fact of a relation with a shelf life loses weight little by little, down to *Weight of a fact to review* when its shelf life ends, instead of all at once at the end.

Simulate them with the [[Reference queries]] before turning them on.

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

Each entity the ingestion touches gets its **summary** rewritten by the brain's LLM, which merges what the episode adds and leaves the summary as it was when nothing durable is new. graphiti-core would otherwise append the new fact sentences to the old summary without asking the model, until it passed 2,000 characters, which is why many summaries read as a list of facts. It costs one call per batch of entities touched, counted in [[AI consumption]] as ingestion.

Purging runs on start and every hour. More on the queue in [[Jobs]]. The embedding model change itself is explained in [[AI providers]].

> The **concurrency** of LLM calls during an ingestion is set with an environment variable at startup (it is not changed live). See [[Environment variables]].
