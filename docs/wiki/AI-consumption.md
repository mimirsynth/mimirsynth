**English** · [Español](Consumo-de-IA)

# AI consumption

What each brain spends on AI engines, so that a big document source or a reindex does not run up the bill without anyone seeing it, and so that a slow ingestion can be explained.

## What is counted
Every call MimirSynth makes to an engine, where it makes it:

| Use | Engine | When |
|---|---|---|
| Fact extraction | LLM and embeddings | Ingesting a proposal (Graphiti) |
| Decider | Decider | Triaging a proposal |
| Corrector of types | Decider | Looking for wrong entity types |
| Recall | Embeddings | Every recall, also over MCP, and the document search |
| Document index / Episode index | Embeddings | Indexing documents and episodes |
| Fact editing | Embeddings | Editing a fact's text |
| Import | Embeddings | Computing the vectors of an imported brain |
| Model change | Embeddings | The shadow fill of a model change (not on behalf of a brain) |

For each call it keeps the **tokens** (input and output) that the answer reports in its `usage` field; when an answer has none, the input is estimated (4 characters per token) and the call is marked as estimated. It also counts the **429** answers (the provider limits the pace) and the **5xx** ones, and the **pace**: requests per minute right now and the day's peak. Only counters per day, brain, engine and use are stored, never the calls or their text.

## Where to see it
- **Administration → Brain access → AI consumption** (brain administrators): the last 30 days of the brain, per use and engine, and its budget.
- **Administration → AI models → Consumption** (instance administrator): every engine with its requests per minute now, its peak, its errors and its price, and every brain. It refreshes every 15 seconds.

## Estimated cost
Set a **price per million tokens**, for input and for output, per model (Consumption → **Price**). A model without a price is shown as such and does not count in the cost. For a local engine (Ollama), leave it at zero: what matters there is the time.

## Monthly budget
Optional, per brain, in **tokens** or in **estimated cost**:
- At **80 %** and at **100 %** the `ai.budget` notification goes out, once per month and level (see [[Notifications]]).
- With **Pause ingestion when it is spent**, at 100 % the brain stops ingesting proposals. An approved proposal waits, marked «paused», without being lost; it goes on by itself when the budget is raised or the month changes (checked every ten minutes). Recall, the decider and document indexing are not paused.

Changes to the budget and to the prices are audited (`brain.ai_budget`, `ai.price`).

## API
`GET /api/brains/{slug}/ai-usage?days=30` and `PUT /api/brains/{slug}/ai-budget` (`{"limit", "unit": "tokens" | "cost", "pause"}`; an empty `limit` removes it), for brain administrators. `GET /api/ai-usage?days=30`, `PUT /api/ai-usage/prices` (`{"kind", "model", "price_in", "price_out"}`) and `DELETE /api/ai-usage/prices?kind=&model=`, for the instance administrator. See [[REST API]].
