# Retrieval eval (#492)

How well the recall serves a brain, measured on its final context: per question class, at two budgets, with intervals, and B
against A with a verdict written before measuring (#491, Phase 0). `census/` holds the corpus census (#514),
`experiments/write_path/` the offline write-path experiment (#517), `errors/` the error analysis (#515), `clean/`
the virtual clean corpus (#516, `run --corpus clean`), and `adapters/` Cognee as an external baseline (#526, section 6).

Everything runs on the **frozen Phase 0 snapshot**, restored on an instance that is not production, from `api/` with that instance's
`MIMIRSYNTH_*` environment and `MIMIRSYNTH_EVAL_SNAPSHOT=1`. Set that variable only on the restored instance: `run`, `hookset` and
`drafts.py` refuse to touch a brain without it, since production is PostgreSQL too. Everything it writes goes to `eval/out/`, which
git ignores: questions, prompts and results hold the brain's own text.

Nothing here changes the brain, but it is not read-only either:
- the recall's embedding calls and the drafts' LLM calls are counted in the snapshot's `ai_usage` for the instance (brain 0),
  under the purpose `eval`, never for the brain: its monthly AI budget would count them, and reaching it sends an alert through
  the channels the snapshot copied from production;
- reading a federation grant stamps its last use;
- both refuse to run on anything but PostgreSQL;
- run it with the instance's notifications off all the same, so nothing else the snapshot copied can send anything.

## 1. Questions

The gold set is a JSONL file, one question per line, kept in `eval/out/` (never in the repository):

```json
{"id": "q001", "class": "temporal", "query": "¿dónde corre ahora X?", "answer_episodes": ["<uuid>"], "stale": ["<uuid>"], "validated": true}
```

| Field | |
|---|---|
| `class` | `point`, `entity` (the answer is spread over several notes), `temporal`, `ood` (out of domain: the answer is nothing), `volatile` (the three probes) |
| `answer_episodes` | the uuids of the episodes that contain the answer: an `entity` question needs at least two distinct ones, `ood` none |
| `answer_docs` | optional: document ids, when the answer is in a document |
| `stale` | `temporal` only: what must not appear as current. A fact uuid counts only when Graphiti failed to invalidate that fact, since an invalidated fact always shows as no longer true. An episode or document uuid counts when a fragment or passage from it shows with no warning |
| `validated` | `true` or `false`: the maintainer read the question and accepts it. `run` leaves out the rest unless given `--include-drafts` |
| `drafted_from` | where the draft came from: the census stratum of its episodes, `entities` or `replay sample`. Kept to measure the bias later |

`check_gold` refuses a set with any of these:
- a missing or repeated id;
- an unknown class;
- an id list that is not a list of strings;
- a `validated` that is not a boolean;
- an entity question with fewer than two distinct episodes.

**Drafts.** `drafts.py` writes drafts to `eval/out/drafts.jsonl`. It refuses to overwrite that file, since you edit it.

```bash
.venv/bin/python ../eval/drafts.py --brain SLUG
```

- **From episodes, through the instance's default LLM engine.** The episodes come from the census strata in `--strata`: by default
  `person`, `agent` and `capture`, so the gold set does not lean towards the clean arm of #516. Only text from episodes of those
  strata reaches the engine.
  - `point`: one episode.
  - `entity`: two to five episodes that mention the same entity.
  - `temporal`: a fact Graphiti invalidated and the fact that replaced it, both from those strata. `stale` gets the old fact and the
    episodes only the old fact came from.
  - `ood`: questions that sound like the brain but are not about it, drafted from the names of the entities those episodes mention,
    ten per call. Each call is told the ones already written, and repeats are dropped. A failed call keeps what the earlier ones
    gave.
- **From real prompts.** The replay sample's most recent queries (`--samples`, 40 by default), as they were asked. They are never
  sent to the engine, and they come with an empty `class` and no answer for you to fill in. A prompt asked twice is drafted once.
  The hook's own prompts are left out, since they are the hook set (below), split on their own.

Every draft has `validated: false`, a `draft_answer` and its `drafted_from`. To accept a draft:
1. Read it.
2. Fix its class, query, `answer_episodes` and `stale`.
3. Set `validated: true`.
4. Copy it to the gold set.

The script reports at the end how many pieces of material the engine gave nothing usable for. Volatile questions are not drafted.

## 2. Real prompts (hook set)

```bash
.venv/bin/python ../eval/run.py hookset --brain SLUG     # eval/out/hookset.jsonl
```

This writes the replay sample's prompts that came through the agents' hook: over HTTP, with `facts=6` and `chunks=3`.
- Put in `label` the uuid of the episode that should have been injected, or `nothing`.
- Unlabelled prompts are skipped.
- Running the command again adds the new prompts and keeps every label already written.

## 3. Split

```bash
.venv/bin/python ../eval/run.py split --gold ../eval/out/gold.jsonl --hookset ../eval/out/hookset.jsonl          # eval/out/split.json
.venv/bin/python ../eval/run.py split --gold ../eval/out/gold.jsonl --hookset ../eval/out/hookset.jsonl --add    # new ones only
```

- The split is `tune` / `holdout` at 50 / 50 within each class, fixed by id. The hook prompts are split the same way, separately.
- It refuses to be redone. With `--add`, everything already placed keeps its side, and new questions and prompts go to the smaller
  side of their class.
- `run` stops if a question or a labelled prompt is in neither side.

## 4. Run

```bash
.venv/bin/python ../eval/run.py run --brain SLUG --gold ../eval/out/gold.jsonl --hookset ../eval/out/hookset.jsonl \
    --split holdout --budget plugin --label baseline-0.17
```

| Budget | Facts | Fragments | Characters |
|---|--:|--:|--:|
| `2500` | 8 | 4 | 2,500 |
| `plugin` | 6 | 3 | 4,000 (the hook's real parameters) |

It calls the app's `recall()` in process, the way the hook's HTTP call makes it: with what other brains lend this one (federation),
in the instance's default language and with its default document passages. All three are recorded in the result's `meta`. It prints the table
and writes `eval/out/run-<label>-<budget>-<split>.json`. A recall that fails is recorded with its error and left out of the metrics,
and the run goes on. If every recall fails, the command exits with 1.

**What is scored.** Only the items that made it into the final `context`, in the order they appear there.
- Each item is matched by its own line: a fact by its `- <fact> (` line, and a fragment or passage by its text right under its
  `###` header.
- A text that is only quoted in another line (`[sustituye a «…»]`, a warning) does not count, and an item the budget cut out counts
  neither for nor against.
- `empty_ok` and hook silence look at the context itself, so a state card alone counts as something injected.
- `noise` is over the whole context. An item from the answer takes its whole entry: a fact's line, or a fragment's or passage's
  header, text and "may be superseded" lines (any other `> ` line is not part of it). No two items share a character: a `###`
  heading or a `- … (` line inside a passage's text is not taken as another item. Every other character is noise, whether it was parsed or not: section headers, state cards, items
  outside the answer, and any text in a format the parser does not know. So a variant that writes its context another way cannot
  look cleaner for it.
- Each record keeps `unparsed_chars`, the characters no item took, and the summary prints their total against the context's.
- If the recall returned items and none of them is found in a context that has text, the record is an error, `unparsed context`. It
  leaves the metrics and the pairing instead of scoring as an empty answer. This also happens if state cards take the whole budget.

| Metric | Classes | Definition |
|---|---|---|
| `top3` | point, temporal, volatile | an item from an answer episode (or answer document) is among the first three |
| `coverage` | entity | share of the answer episodes that some item comes from |
| `stale_as_current` | temporal | something in `stale` is shown as current (see `stale` above) |
| `empty_ok` | ood | the context is empty |
| `noise` | every class, and all together | share of the context's characters that are not part of an item from the answer: summed over the questions, over the sum of their context lengths |
| `hook_precision` | hook | of the prompts where something was injected, the share that injected the labelled note |
| `hook_silence` | hook | of the prompts labelled `nothing`, the share where nothing was injected |

Latency p50 and p95 come from the recall's own `ms.total`. Every rate has a 95 % bootstrap interval over the questions (2,000
resamples, fixed seed).

## 5. Compare

```bash
.venv/bin/python ../eval/run.py compare ../eval/out/run-a.json ../eval/out/run-b.json
```

- **Paired:** each resample draws the same questions for A and B, over the questions that ran without error in both. The counts are
  printed.
- **Refuses** two runs that differ in budget, split or whether drafts were included.
- **The table** gives B − A in points with its interval, and the change relative to A. A metric that A measured and B could not,
  such as hook precision when B injects nothing, stays in the table without a value.

**The verdict, written before measuring:**

- **Yes** needs all four:
  - at least one co-primary improves:
    - `noise` over all questions falls 30 % or more relative to A, or
    - `stale_as_current` on the temporal questions falls 50 % or more,

    and the interval of that change is wholly below zero;
  - neither co-primary rises (its interval is not wholly above zero);
  - every answer metric that A measured (`top3`, `coverage`, `empty_ok`, `hook_precision`, `hook_silence`) is measured in B too, and
    loses 3 points or fewer at the lower bound of its interval;
  - B fails on no more of the questions both runs have than A does. A failed recall or an unparsed context leaves the pairing, and
    B must not be judged only on the questions it got through.
- **Anything else, a tie included, is no.** A co-primary at 0 in A cannot fall. The command exits with 1 on a no.

How "improves" is read: the point estimate of the relative change reaches the minimum effect (−30 % or −50 %), and the interval of
the difference B − A is wholly below zero. The interval does not have to be wholly past the minimum effect: with about 50 questions
per class that would rarely be reached. Agreed in the review of #522.

## 6. Cognee as an external baseline (#526)

The same questions, budgets and scoring, on Cognee loaded with the snapshot's episodes, so that "v1 is better" means better than a
known alternative too. Cognee runs in **its own venv** (its dependencies pin other versions than the app's) and as **a separate
instance**, never production.

**Set up the separate instance.**

```bash
python3.11 -m venv ~/cognee-eval/.venv && ~/cognee-eval/.venv/bin/pip install -r ../eval/adapters/requirements-cognee.txt
mkdir -p ../eval/out/cognee && ~/cognee-eval/.venv/bin/pip freeze > ../eval/out/cognee/pip-freeze.txt               # keep it with the results
export MIMIRSYNTH_EVAL_SNAPSHOT=1
export MIMIRSYNTH_EVAL_COGNEE_ROOT=~/cognee-eval/instance      # an empty folder: Cognee keeps all its stores under it
export LLM_PROVIDER=... LLM_MODEL=... LLM_ENDPOINT=... LLM_API_KEY=...
export EMBEDDING_PROVIDER=... EMBEDDING_MODEL=... EMBEDDING_DIMENSIONS=...   # the same family as the snapshot's embeddings
export LLM_RATE_LIMIT_ENABLED=true LLM_RATE_LIMIT_REQUESTS=30 LLM_RATE_LIMIT_INTERVAL=60   # below the gateway's limit
```

- The scripts refuse to start without `MIMIRSYNTH_EVAL_COGNEE_ROOT`, or with any of `DB_HOST`, `DB_PROVIDER`, `VECTOR_DB_URL`,
  `VECTOR_DB_PROVIDER`, `GRAPH_DATABASE_URL` or `GRAPH_DATABASE_PROVIDER` set: those point Cognee at a database server, and
  production's Cognee keeps its vectors in PostgreSQL. With none of them, Cognee uses its embedded stores under the root.
- Importing Cognee loads a `.env` over the environment (the nearest one above the working directory or the package). So the
  scripts refuse a `COGNEE_ENV_FILE` already set, point it at an empty file under the root, and check the settings again after
  the import. Give every setting in the environment.
- Python 3.11 or later: the scripts load `eval/run.py`. Only `cognee` is pinned; the venv's packages are hashed into the meta
  (`packages_sha256`), and a venv that changed since the load is warned about.
- Cognee's documented defaults are kept: `add` + `cognify` (not `improve`), and `search` with `CHUNKS`. Note in #491 any setting you
  change.

**Load it.**

```bash
cd api && .venv/bin/python ../eval/adapters/cognee_load.py export --brain SLUG               # app venv: eval/out/cognee/SLUG.json
~/cognee-eval/.venv/bin/python ../eval/adapters/cognee_load.py load --brain SLUG             # Cognee venv: the trial, then the cost
~/cognee-eval/.venv/bin/python ../eval/adapters/cognee_load.py load --brain SLUG --yes       # the rest
```

- `export` takes every episode with text, like the 0.17 baseline. `--corpus clean` leaves out the episodes in `curated.json`
  (#516); each corpus goes to its own dataset. The file holds each episode's uuid, reference time and text, and is the brain's
  own text, so it stays in `eval/out/`.
- `load` adds the episodes oldest first, each with its reference time on its first line (Cognee has no reference time of its own)
  and its uuid as a node set.
  - **The trial**: it loads the first 10 episodes (`--trial`), counts the LLM calls `cognify` made through litellm, and prints the
    estimate for the rest: episodes × calls per episode. If the calls cannot be counted, read them on the gateway and give
    `--calls-per-episode`. Without `--yes` it stops there.
  - **Serially**: batches of 10 (`--batch`), each added and cognified before the next, and each call retried 3 times (`--retries`)
    after 5, 10 and 20 s. The episodes loaded are saved after each batch: run `load` again to resume.
  - The Cognee version, LLM and embedding, as Cognee's own configuration reads them, are recorded in the file. A brain loaded with one version is never loaded further or
    searched with another.

**Run the arm.**

```bash
~/cognee-eval/.venv/bin/python ../eval/adapters/cognee_arm.py search --brain SLUG --gold ../eval/out/gold.jsonl \
    --hookset ../eval/out/hookset.jsonl                                       # Cognee venv: eval/out/cognee/results-SLUG.jsonl
.venv/bin/python ../eval/run.py run --system cognee --brain SLUG --gold ../eval/out/gold.jsonl --hookset ../eval/out/hookset.jsonl \
    --split holdout --budget plugin --label cognee                            # app venv; --corpus as loaded
.venv/bin/python ../eval/run.py compare ../eval/out/run-baseline-0.17-plugin-holdout.json ../eval/out/run-cognee-plugin-holdout.json
```

- `search` asks Cognee for every question's chunks at both budgets and stores them as they came (`raw`), next to the flattened
  list. `run --system cognee` flattens `raw` again and scores it like any other system, and reads no brain. A dataset Cognee could
  not search comes back with an `error` instead of raising: that question's recall fails and is recorded, never scored as empty.
- **The budget:** Cognee gets as many results as the app's recall may show (8 + 4 at `2500`, 6 + 3 at `plugin`), and its context is
  written by the app's own `build_context` within the same characters. Its chunks are longer than 0.17's 900-character fragments,
  so the first one that does not fit whole is cut, at a space, to what is left (at least 200 characters); nothing comes after it.
- **Back to episodes:** a chunk is mapped to the episode whose loaded text contains it, whitespace aside. A chunk found in no
  episode counts as noise, never as a match. A chunk found in several episodes maps to all of them only when they were loaded with
  the same whole text (`duplicates`); found in different episodes, it says nothing about where it came from (`Gracias.`), so it is
  `ambiguous` and counts as noise too. The counts (`results`, `unmapped`, `ambiguous`, `duplicates`, `cut`) are in the result's
  `meta.results`: many unmapped or ambiguous chunks mean the mapping failed, not that Cognee is noisy, so look at them before
  posting.
- The result's `meta` also has `system: cognee`, the Cognee version, LLM, embedding and dataset. The latency is Cognee's search
  alone, timed by `search`.
