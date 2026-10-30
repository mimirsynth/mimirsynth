**English** · [Español](Consultas-de-referencia)

# Reference queries

A **reference query** is a question together with what its recall **must** bring and what it **must not**. Keeping a set of them per brain lets you measure recall quality with data, before and after changing the passage threshold, the embedding model or the weights, instead of judging by a handful of searches in [[Ask]].

## Who can use them
They are in **Ask → Reference queries**, for **curators and above** (see [[Roles and permissions]]); readers and contributors do not see the tab. Each brain has its own queries, up to 500.

## Creating queries
**New query** opens the form:
- **Query:** the question, as an agent would ask it.
- **Must appear:** one text per line. It counts as found if it appears in any result (fact, episode fragment or document passage), ignoring case and spacing. Start the line with `fact:`, `chunk:` or `doc:` to require that type of result.
- **Must not appear:** known false positives, in the same format.
- **Documents section:** **Either way**, **There must be document passages** or **There must be no document passages**.
- **Note:** free text for yourself.

Each list takes up to 50 texts of up to 500 characters. **Edit** and **Delete** are on every row; deleting a query does not change the results of earlier runs.

You can also build them from [[Ask]]: after a search, mark results as **Expected** or **Extra** and press **Save as reference query**; the form opens already filled in.

The texts go through the brain's secret detector, so saving a graph fact as an expected text never copies a credential: depending on the brain's setting the secret is masked or the query is refused.

## Importing and exporting
- **Export** downloads every query of the brain as JSON, to take them to another brain or instance.
- **Import** adds the queries of a JSON file. A query whose text matches one already saved (ignoring case and spacing) is skipped, and you are told how many were imported and skipped.

```json
{"items": [
  {"query": "Where does the mail service run?",
   "expect": [{"text": "mail service runs on server 2", "kind": "fact"}],
   "avoid": [{"text": "old mail server", "kind": "any"}],
   "docs": null,
   "note": ""}
]}
```

`kind` is `any`, `fact`, `chunk` or `doc`; `docs` is `true` (there must be passages), `false` (there must be none) or `null` (either way). A bare list of queries is accepted too.

## Run
**Run** measures every query with the brain's current settings, running the same recall an agent gets (including what other brains lend, if any). It runs as a job (see [[Jobs]]) and the **Runs** table updates as it goes:
- **Parameters:** «current settings», or the simulated threshold.
- **Found:** expected texts found out of the total, and the percentage.
- **False positives:** texts that must not appear and did.
- **Documents wrong way round:** queries whose documents section came out the opposite of what they ask for.
- **Median:** the median recall time.
- **Against the previous one:** **better**, **worse** or **same**, with the difference in found and false positives and how many queries were compared.

**View** opens the detail of a run: what was found by type, and for every query what is **missing**, what is **extra** and whether its documents section was right. If the run is worse, it lists what **no longer appears** and every **new false positive**.

The last **20 runs** of each brain are kept.

## Simulate
Write one or more passage similarity thresholds in **Thresholds to simulate** (for example `0.68 0.70 0.72`, up to 6) and press **Simulate**: there is one run per threshold, **without changing the setting**. Compare them, and when you have chosen, set the value of *Minimum similarity of a passage* under Administration → Recall ([[Recall and ingestion]]).

## How runs are compared
- Each run is compared with the previous run on the **current settings**; simulations are never the baseline.
- Only what is in **both runs** counts: the same queries and the same texts. Adding, deleting or editing a query never shows up as worse.
- A run is **worse** if an expected text that appeared no longer does, a new false positive appears, or a query's documents section turns the wrong way round.

## During an embedding model change
When the embedding model is changed (Administration → Embeddings → **Reindex**, see [[AI providers]]), every brain with reference queries runs them on its own twice: when the new vectors start being computed, still with the previous model, as the baseline (marked «before the model change»), and when the switch finishes («after the model change»).

If the second run is worse, the **`refquery.regressed`** alert (warning) is raised with how many expected texts were lost and how many false positives are new. If there was no earlier run to compare with, the same alert says so as information, and that run becomes the baseline for the next change. Alerts show in the bell and go to the configured channels (see [Notifications](https://github.com/MimirSynth/mimirsynth/blob/main/docs/NOTIFICATIONS.md)).

After a model change it is a good moment to **Simulate** a few thresholds: the right passage threshold depends on the model.

More detail: «Reference queries» in [ARCHITECTURE.md](https://github.com/MimirSynth/mimirsynth/blob/main/docs/ARCHITECTURE.md).
