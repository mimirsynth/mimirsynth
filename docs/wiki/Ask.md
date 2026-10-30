**English** · [Español](Preguntar)

# Ask

Here you try **recall**: the same thing an agent does when it queries the memory before answering. It is used to check what your agent would find and to debug why an answer is poor.

## How to use it
1. Write a question or a sentence in natural language (e.g. "where is the production database now?").
2. Adjust, if you like, **Facts** (how many facts to bring, 0–30) and **Fragments** (how many episode fragments, 0–15).
3. Press **Search** or `Ctrl+Enter`.

## What it returns
- **Facts:** the most similar to the question, current and invalidated (invalidated ones struck through with their date range). Each shows its similarity.
- **Episode fragments:** pieces of the episodes' **original text**, found by meaning and by words. They recover details extraction may have lost.
- **Document passages:** the passages of indexed documents that recall brought, each with its title and similarity. There are at most as many as the brain's *Document passages per recall* (2 by default), only above the *Minimum similarity of a passage*, and the same text found in two documents is shown once (see [[Recall and ingestion]]).
- **Injected context:** the final block of text, with a copy button. It is what an agent would receive: current facts, the evolution of the facts of the mentioned entities and the cited document passages.
- **Timings:** total milliseconds and broken down (embedding, facts, fragments).

If another brain lends its memory to this one (federation), the items that come from it carry that brain's name.

## How it is combined
Facts and fragments are ranked separately and then **fused** (reciprocal rank) giving a bit more weight to **recent** items: a question about "now" favours the latest known. No LLM is involved, which is why it is fast (typically tens or a few hundred milliseconds).

## The text index
Fragments come from an **index of the episode text** stored in PostgreSQL. In the header you see its status ("index: N fragments from M episodes"). It synchronises by itself every few minutes (see [[Recall and ingestion]]); **curators** can press **Reindex now** to force it. If it says "disabled", the instance has no PostgreSQL with pgvector and only facts will be searched.

## Saving a reference query (curator or higher)
Curators and above see two tabs, **Ask** and **Reference queries**. After a search, every fact, fragment and passage has two buttons: **Expected** (it must come up for this question) and **Extra** (it should not). **Save as reference query** opens the form already filled in with the question and what you marked (the first 200 characters of each result), so the brain can check later that recall still finds it. See [[Reference queries]].

## If the result is poor
| Symptom | Likely cause | What to do |
|---|---|---|
| Returns nothing | Empty brain or embeddings down | [[Overview]]; test the engine in [[AI providers]] |
| Brings old facts | Recent episodes missing or not ingested | [[Jobs]], [[Proposals]] |
| Returns the same item under three names | Duplicate entities | [[Vocabulary]] → Duplicates |
| A concrete detail is missing | It was in the text, not extracted as a fact | Look at the *fragments*; consider rephrasing the episode |
| No document passages, or irrelevant ones | Passage threshold too high or too low for the embedding model | Measure it with [[Reference queries]] (**Simulate**) before changing it |
