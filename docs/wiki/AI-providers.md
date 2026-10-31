**English** · [Español](Proveedores-de-IA)

# AI providers

Three sections of administration: **LLM model**, **Embeddings** and **Decider**. Each is a table of **engines**: an engine is the combination of an *endpoint*, a key and a model. MimirSynth talks to any service **compatible with the OpenAI API** (Ollama, vLLM, LM Studio, OpenAI, OpenRouter, your own gateway…).

## Status and Check
The header of each section shows the **Status** of its provider ("OK · name", "not configured", "down · …", or "via environment variables") and a **Check** button. **Check** makes a real call to the engine in use, including one that comes from the `MIMIRSYNTH_LLM_*` / `MIMIRSYNTH_EMBEDDING_*` variables, and keeps the result next to the button until the next check: "Responding · model · 120 ms" or the error, with the time it was checked.

The instance also runs this check on its own every few minutes and raises an alert if an engine stops responding ([[Notifications]]).

## What each one is for
| Engine | Required | What it does |
|---|---|---|
| **LLM** | Yes, to ingest | Reads approved proposals and **extracts entities and facts** (using the Graphiti library). Without it, approved proposals stay in "Approved". |
| **Embeddings** | Yes, to search | Turns texts into vectors for **recall**, the text index and document search. |
| **Decider** | No | **Closed-decision** model (chooses among options with a probability): automatic proposal triage and the [[Type corrector]]. Without it, everything goes through a curator. |

## Adding an engine
**Add engine** button. Fields:
- **Endpoint (base URL):** the API address, normally ending in `/v1` (`http://ollama:11434/v1`, `https://api.openai.com/v1`…).
- **API key:** stored **encrypted**. For a local service without authentication any text usually works. When editing, empty = keep the current one.
- **Load models:** asks the endpoint for the list of available models. If the endpoint does not offer it, type the name by hand.
- **Model:** the model to use. For an embedding engine it cannot be changed after saving (see below).
- **Small model (LLM only, optional):** for lightweight tasks; defaults to the same one.
- **Confidence threshold (Decider only):** between 0.50 and 0.99 (default 0.80). Below it, the proposal goes to human review.
- **Name** and **Enabled**.
Press **Save**. Then **Test** makes a real call: the result ("OK…" or the error) appears under the engine.

## The table
Columns: name, endpoint, model (with the dimension for embeddings and the threshold for deciders) and **state** (*default*, *disabled*, *no key*). Actions per row: **Test**, **Default**, **Edit**, **Delete**, and **Reindex** on an embedding engine whose model differs from the one in use.

There can be **several engines** of each kind; the one marked **Default** is used. When you **delete** an engine, the brains that used it move to the default engine, or to the environment variables if there is no other.

## Environment variables as a fallback
If there is still no engine in the interface, MimirSynth uses `MIMIRSYNTH_LLM_*` and `MIMIRSYNTH_EMBEDDING_*` ([[Environment variables]]); changing them requires restarting the service. Add the same engine here to manage it from the interface: an engine added here takes precedence over the variables.

## Changing the embedding model
Stored vectors depend on the model, and vectors from different models are not comparable. That is why an embedding engine's **model and dimension cannot be edited**: to change model, add a **new engine** with the new model and move everything to it with **Reindex**. Nothing in use changes until you confirm the switch.

1. **Add** the new embedding engine (do not make it the default).
2. Press **Reindex** on its row. The dialog shows an **estimate**: how many graph items and chunks will be recomputed, roughly how many engine calls, the memory needed in FalkorDB against the free memory, and the extra space in PostgreSQL (check the free disk yourself). If FalkorDB does not have enough free memory, it will not start.
3. **Compute in shadow** recomputes every vector of every brain with the new engine and stores it aside. A panel shows the progress, with **Cancel**. It can take a while and uses engine calls.
4. When it finishes, the panel says the vectors are **ready in shadow** and the model in use has not changed yet. Press **Switch to the new model** and tick **I have backed up FalkorDB and PostgreSQL**. The switch completes whatever changed meanwhile, pauses vector writes (ingestion, index, documents) for a moment and swaps everything at once; the new engine becomes the default. If anything fails, everything stays on the previous engine and you can try again. **Discard** deletes the shadow vectors instead.
5. Afterwards, **recalibrate the minimum passage similarity** of the recall ([[Recall and ingestion]]): the value for the previous model does not fit the new one. Agents that write directly to Graphiti keep using the previous model until you switch them too.

Good to know:
- An unfinished shadow computation (failed or cancelled midway) keeps taking memory: the panel offers **Retry** (it only computes what is missing) and **Discard**. If it stays like that for longer than the configured hours, the `reindex.orphan` alert is raised.
- Brains that have reference queries ([[Reference queries]]) run them on their own before the fill (with the previous model) and after the switch, and the `refquery.regressed` alert warns you if recall got worse.
- Batch size, pause between batches, how long the switch waits for writes in progress, and when to warn about a stalled change are set in **Ingestion and jobs** ([[Settings reference]]).
- Your `.env` keeps the old `MIMIRSYNTH_EMBEDDING_*` values. They only matter for a fresh installation or when no engine is registered here: if you rely on them, update them to the new model and dimension.
- If another Graphiti writes to the same FalkorDB, it **must use the same model** as the default engine.
- Choose a quality model from the start: changing later is possible, but it recomputes everything. `nomic-embed-text` (768 dimensions) is a local, lightweight option.

Technical details: [docs/CONFIGURATION.md](https://github.com/MimirSynth/mimirsynth/blob/main/docs/CONFIGURATION.md).

## Tips for the LLM
- To extract facts well, a **capable** model is advisable (not the smallest).
- **"Reasoning" models:** some return their reasoning instead of the JSON and extraction fails with empty responses. If it happens, use a proxy that disables *thinking* or a non-reasoning model.
- **Rate limits:** if your provider limits requests, ingestion retries several times (see *Ingestion retries* in [[Recall and ingestion]]) and reduces concurrency.
- A cloud provider receives the **text of your proposals and episodes**. If it is sensitive information, use a local model.

## Tips for the decider
- It judges each proposal against the **brain's scope**: its description and the entity and relation types of its ontology. Fill in the brain's description ([[Brains and members]]); with neither description nor ontology it only checks that the proposal is a factual statement. It assumes no particular domain.
- It works well with small models (it answers few options).
- Start with a **high threshold (0.9)** so it only approves the obvious; lower it if you see too much going to review.
- It never rejects on its own: anything doubtful or off-topic goes to a curator.

## Consumption
**Consumption**, in this same section, shows what each engine and each brain spends: calls, tokens, requests per minute and 429/5xx errors, with an estimated cost from a price per million tokens per model. See [[AI consumption]].
